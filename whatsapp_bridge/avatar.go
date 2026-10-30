package main

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/types"
)

const maxAvatarBytes = 5 * 1024 * 1024

// contactName is the best human name the account's store knows for one user: the name the
// person chose for themselves (push name), else the one saved in the owner's address book.
func (b *Bridge) contactName(ctx context.Context, jids ...types.JID) (name, source string) {
	b.mu.Lock()
	client := b.client
	b.mu.Unlock()
	if client == nil || client.Store == nil || client.Store.Contacts == nil {
		return "", ""
	}
	for _, jid := range jids {
		if jid.IsEmpty() {
			continue
		}
		c, err := client.Store.Contacts.GetContact(ctx, jid.ToNonAD())
		if err != nil {
			continue
		}
		if c.PushName != "" {
			return c.PushName, "push_name"
		}
		if c.FullName != "" {
			return c.FullName, "address_book"
		}
	}
	return "", ""
}

// handleContact answers with the name the bridge knows for a user (either id of the same person
// may be passed: the phone-number JID and the LID).
func (b *Bridge) handleContact(w http.ResponseWriter, r *http.Request) {
	var jids []types.JID
	for _, raw := range r.URL.Query()["jid"] {
		if jid, err := types.ParseJID(raw); err == nil && !jid.IsEmpty() && jid.Server != types.GroupServer {
			jids = append(jids, jid)
		}
	}
	if len(jids) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "a user jid is required"})
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
	defer cancel()
	name, source := b.contactName(ctx, jids...)
	writeJSON(w, http.StatusOK, map[string]string{"name": name, "source": source})
}

// avatarHostAllowed limits the download to WhatsApp's own picture CDN: the URL comes
// from a server response, so it must never lead the bridge to an arbitrary host.
func avatarHostAllowed(raw string) bool {
	u, err := url.Parse(raw)
	if err != nil || u.Scheme != "https" {
		return false
	}
	host := strings.ToLower(u.Hostname())
	return strings.HasSuffix(host, ".whatsapp.net") || strings.HasSuffix(host, ".fbcdn.net")
}

// handleAvatar returns the profile picture of one user (read-only; nothing is sent to
// the contact). 404 when the user has none or hides it from this account.
func (b *Bridge) handleAvatar(w http.ResponseWriter, r *http.Request) {
	jid, err := types.ParseJID(r.URL.Query().Get("jid"))
	if err != nil || jid.IsEmpty() || jid.Server == types.GroupServer {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "a user jid is required"})
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
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	info, err := client.GetProfilePictureInfo(ctx, jid.ToNonAD(), &whatsmeow.GetProfilePictureParams{})
	if errors.Is(err, whatsmeow.ErrProfilePictureNotSet) || errors.Is(err, whatsmeow.ErrProfilePictureUnauthorized) ||
		(err == nil && (info == nil || info.URL == "")) {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "no profile picture"})
		return
	}
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": "whatsapp lookup failed"})
		return
	}
	if !avatarHostAllowed(info.URL) {
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": "unexpected picture host"})
		return
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, info.URL, nil)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": "bad picture url"})
		return
	}
	resp, err := (&http.Client{Timeout: 30 * time.Second}).Do(req)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": "picture download failed"})
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "no profile picture"})
		return
	}
	data, err := io.ReadAll(io.LimitReader(resp.Body, maxAvatarBytes+1))
	if err != nil || len(data) > maxAvatarBytes {
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": "picture unreadable or too large"})
		return
	}
	w.Header().Set("Content-Type", http.DetectContentType(data))
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(data)
}
