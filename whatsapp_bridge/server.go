package main

import (
	"context"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"

	qrcode "github.com/skip2/go-qrcode"
	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"google.golang.org/protobuf/proto"
)

// Routes exposes the read-only API. Everything but /healthz needs the bearer
// token; there is deliberately no endpoint that sends, replies or marks read.
func (b *Bridge) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	mux.HandleFunc("GET /status", b.auth(b.handleStatus))
	mux.HandleFunc("GET /chats", b.auth(b.handleChats))
	mux.HandleFunc("GET /allowlist", b.auth(b.handleGetAllowlist))
	mux.HandleFunc("PUT /allowlist", b.auth(b.handlePutAllowlist))
	mux.HandleFunc("GET /events", b.auth(b.handleEvents))
	mux.HandleFunc("POST /ack", b.auth(b.handleAck))
	mux.HandleFunc("GET /media", b.auth(b.handleMedia))
	mux.HandleFunc("DELETE /media", b.auth(b.handleDeleteMedia))
	mux.HandleFunc("GET /pairing/qr", b.auth(b.handleQR))
	mux.HandleFunc("GET /pairing/qr.png", b.auth(b.handleQRPNG))
	mux.HandleFunc("POST /pairing/reset", b.auth(b.handleReset))
	return mux
}

func (b *Bridge) auth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		got := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
		if subtle.ConstantTimeCompare([]byte(got), []byte(b.cfg.Token)) != 1 {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
			return
		}
		next(w, r)
	}
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func (b *Bridge) handleStatus(w http.ResponseWriter, r *http.Request) {
	b.mu.Lock()
	defer b.mu.Unlock()
	out := map[string]any{
		"state":         b.state,
		"account_jid":   b.accountJID,
		"needs_pairing": b.state == StateNeedsPairing || b.state == StateLoggedOut,
		"qr_available":  b.qrCode != "",
		"last_error":    b.lastError,
		"max_seq":       b.journal.MaxSeq(),
		"epoch":         b.journal.Epoch(),
	}
	if !b.lastConnected.IsZero() {
		out["last_connected_at"] = b.lastConnected.UTC().Format(time.RFC3339)
	}
	if !b.lastEvent.IsZero() {
		out["last_event_at"] = b.lastEvent.UTC().Format(time.RFC3339)
	}
	writeJSON(w, http.StatusOK, out)
}

func (b *Bridge) handleChats(w http.ResponseWriter, r *http.Request) {
	chats, err := b.journal.Chats()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "journal"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"chats": chats})
}

func (b *Bridge) handleGetAllowlist(w http.ResponseWriter, r *http.Request) {
	jids, err := b.journal.Allowlist()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "journal"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"jids": jids})
}

func (b *Bridge) handlePutAllowlist(w http.ResponseWriter, r *http.Request) {
	var body struct {
		JIDs []string `json:"jids"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&body); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON"})
		return
	}
	if err := b.journal.SetAllowlist(body.JIDs); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "journal"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"count": len(body.JIDs)})
}

func (b *Bridge) handleEvents(w http.ResponseWriter, r *http.Request) {
	chat := r.URL.Query().Get("chat")
	if chat == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "chat is required"})
		return
	}
	after, _ := strconv.ParseInt(r.URL.Query().Get("after"), 10, 64)
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	evs, err := b.journal.Events(chat, after, limit)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "journal"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"events": evs})
}

func (b *Bridge) handleAck(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Chat string `json:"chat"`
		Upto int64  `json:"upto"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<16)).Decode(&body); err != nil || body.Chat == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "chat and upto are required"})
		return
	}
	n, err := b.journal.Ack(body.Chat, body.Upto)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "journal"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"removed": n})
}

// handleMedia streams one attachment. The declared size is checked before any
// download, and at most MediaConcurrency downloads run at once.
func (b *Bridge) handleMedia(w http.ResponseWriter, r *http.Request) {
	chat, id := r.URL.Query().Get("chat"), r.URL.Query().Get("id")
	raw, size, err := b.journal.Media(chat, id)
	if errors.Is(err, ErrNotFound) {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "media not available"})
		return
	}
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "journal"})
		return
	}
	if size > b.cfg.MaxMediaBytes {
		writeJSON(w, http.StatusRequestEntityTooLarge, map[string]string{"error": "file exceeds the size limit"})
		return
	}
	select {
	case b.mediaSem <- struct{}{}:
		defer func() { <-b.mediaSem }()
	case <-r.Context().Done():
		return
	case <-time.After(30 * time.Second):
		writeJSON(w, http.StatusTooManyRequests, map[string]string{"error": "busy"})
		return
	}
	b.mu.Lock()
	client := b.client
	connected := b.state == StateConnected
	b.mu.Unlock()
	if client == nil || !connected {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "bridge not connected"})
		return
	}
	var msg waE2E.Message
	if err := proto.Unmarshal(raw, &msg); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "stored media descriptor is corrupt"})
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Minute)
	defer cancel()
	data, err := client.DownloadAny(ctx, &msg)
	switch {
	case err == nil:
	case errors.Is(err, whatsmeow.ErrMediaDownloadFailedWith404),
		errors.Is(err, whatsmeow.ErrMediaDownloadFailedWith410),
		errors.Is(err, whatsmeow.ErrNoURLPresent):
		writeJSON(w, http.StatusGone, map[string]string{"error": "media no longer available on WhatsApp servers"})
		return
	default:
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": "download failed"})
		return
	}
	if int64(len(data)) > b.cfg.MaxMediaBytes {
		writeJSON(w, http.StatusRequestEntityTooLarge, map[string]string{"error": "file exceeds the size limit"})
		return
	}
	w.Header().Set("Content-Type", "application/octet-stream")
	w.Header().Set("Content-Length", strconv.Itoa(len(data)))
	_, _ = w.Write(data)
}

func (b *Bridge) handleDeleteMedia(w http.ResponseWriter, r *http.Request) {
	if err := b.journal.DeleteMedia(r.URL.Query().Get("chat"), r.URL.Query().Get("id")); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "journal"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "deleted"})
}

func (b *Bridge) currentQR() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.qrCode
}

func (b *Bridge) handleQR(w http.ResponseWriter, r *http.Request) {
	code := b.currentQR()
	if code == "" {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "no pairing in progress"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"code": code})
}

func (b *Bridge) handleQRPNG(w http.ResponseWriter, r *http.Request) {
	code := b.currentQR()
	if code == "" {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "no pairing in progress"})
		return
	}
	png, err := qrcode.Encode(code, qrcode.Medium, 384)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "qr"})
		return
	}
	w.Header().Set("Content-Type", "image/png")
	w.Header().Set("Cache-Control", "no-store")
	_, _ = w.Write(png)
}

func (b *Bridge) handleReset(w http.ResponseWriter, r *http.Request) {
	// Detached context: the pairing channel must outlive this request.
	if err := b.ResetSession(context.Background()); err != nil {
		b.setError("reset: " + err.Error())
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "reset failed"})
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"status": "pairing restarted"})
}
