package main

import (
	"context"
	"database/sql"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"time"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/proto/waCompanionReg"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/store"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	waLog "go.mau.fi/whatsmeow/util/log"
	"google.golang.org/protobuf/proto"
)

// Connection states reported by /status.
const (
	StateStarting     = "starting"
	StateNeedsPairing = "needs_pairing"
	StateConnecting   = "connecting"
	StateConnected    = "connected"
	StateDisconnected = "disconnected"
	StateLoggedOut    = "logged_out"
)

type Bridge struct {
	cfg     Config
	journal *Journal
	log     *slog.Logger

	mu            sync.Mutex
	client        *whatsmeow.Client
	container     *sqlstore.Container
	state         string
	accountJID    string
	lastConnected time.Time
	lastEvent     time.Time
	lastError     string
	qrCode        string
	qrAt          time.Time
	resolving     map[string]bool

	mediaSem chan struct{}
}

func NewBridge(cfg Config, j *Journal, log *slog.Logger) *Bridge {
	return &Bridge{
		cfg: cfg, journal: j, log: log, state: StateStarting,
		resolving: map[string]bool{}, mediaSem: make(chan struct{}, cfg.MediaConcurrency),
	}
}

func (b *Bridge) setState(state string) {
	b.mu.Lock()
	b.state = state
	b.mu.Unlock()
}

func (b *Bridge) setError(msg string) {
	b.mu.Lock()
	b.lastError = msg
	b.mu.Unlock()
}

// Run opens the session store and keeps the connection alive until ctx ends.
// A failed start is retried with a growing delay; whatsmeow itself reconnects
// after dropped connections.
func (b *Bridge) Run(ctx context.Context) {
	delay := 5 * time.Second
	for ctx.Err() == nil {
		if err := b.start(ctx); err != nil {
			b.setError("start: " + err.Error())
			b.log.Error("start failed", "error", err.Error())
			select {
			case <-ctx.Done():
				return
			case <-time.After(delay):
			}
			if delay < 5*time.Minute {
				delay *= 2
			}
			continue
		}
		<-ctx.Done()
	}
}

func (b *Bridge) start(ctx context.Context) error {
	if b.container == nil {
		db, err := sql.Open("sqlite", "file:"+filepath.Join(b.cfg.DataDir, "session.db")+
			"?_pragma=foreign_keys(1)&_pragma=busy_timeout(10000)&_pragma=journal_mode(WAL)&_pragma=synchronous(FULL)")
		if err != nil {
			return err
		}
		db.SetMaxOpenConns(1)
		container := sqlstore.NewWithDB(db, "sqlite3", waLog.Noop)
		if err := container.Upgrade(ctx); err != nil {
			return fmt.Errorf("session store: %w", err)
		}
		b.container = container
	}
	store.DeviceProps.Os = proto.String(b.cfg.DeviceName)
	store.DeviceProps.PlatformType = waCompanionReg.DeviceProps_DESKTOP.Enum()
	// Ask for as much history as the phone is willing to send at pairing time.
	store.DeviceProps.RequireFullSync = proto.Bool(true)

	device, err := b.container.GetFirstDevice(ctx)
	if err != nil {
		return err
	}
	clientLog := waLog.Noop
	if os.Getenv("WA_BRIDGE_DEBUG") != "" {
		// Protocol-level diagnostics for pairing problems; off by default (noisy).
		clientLog = waLog.Stdout("whatsmeow", "DEBUG", false)
	}
	client := whatsmeow.NewClient(device, clientLog)
	client.AddEventHandler(b.handle)
	b.mu.Lock()
	b.client = client
	b.mu.Unlock()

	if client.Store.ID == nil {
		b.setState(StateNeedsPairing)
		qr, err := client.GetQRChannel(ctx)
		if err != nil {
			return err
		}
		go b.watchQR(qr)
		return client.Connect()
	}
	b.setState(StateConnecting)
	b.mu.Lock()
	b.accountJID = client.Store.ID.String()
	b.mu.Unlock()
	return client.Connect()
}

func (b *Bridge) watchQR(ch <-chan whatsmeow.QRChannelItem) {
	for item := range ch {
		b.mu.Lock()
		switch item.Event {
		case whatsmeow.QRChannelEventCode:
			b.qrCode, b.qrAt, b.state = item.Code, time.Now(), StateNeedsPairing
		case whatsmeow.QRChannelSuccess.Event:
			b.qrCode = ""
		case whatsmeow.QRChannelTimeout.Event:
			b.qrCode, b.lastError = "", "QR code expired; restart pairing"
		case whatsmeow.QRChannelEventError:
			b.qrCode = ""
			if item.Error != nil {
				b.lastError = "pairing: " + item.Error.Error()
			}
		}
		b.mu.Unlock()
	}
}

func (b *Bridge) handle(raw any) {
	b.mu.Lock()
	b.lastEvent = time.Now()
	b.mu.Unlock()
	switch v := raw.(type) {
	case *events.Message:
		b.ingest(v.Info, v.Message, v.IsEdit, "live")
	case *events.HistorySync:
		b.ingestHistory(v)
	case *events.PairSuccess:
		b.mu.Lock()
		b.accountJID, b.qrCode, b.lastError = v.ID.String(), "", ""
		b.mu.Unlock()
	case *events.PairError:
		b.setError(fmt.Sprintf("pairing failed: %v", v.Error))
	case *events.Connected:
		b.mu.Lock()
		b.state, b.lastConnected, b.lastError = StateConnected, time.Now(), ""
		b.mu.Unlock()
	case *events.Disconnected:
		b.setState(StateDisconnected)
	case *events.StreamReplaced:
		b.setError("session replaced by another client with the same keys")
	case *events.ClientOutdated:
		b.setError("WhatsApp rejected the client version; update the bridge image")
	case *events.ConnectFailure:
		b.setError(fmt.Sprintf("connect failure (reason %d)", int(v.Reason)))
	case *events.LoggedOut:
		b.mu.Lock()
		b.state, b.lastError = StateLoggedOut, "logged out from the phone; pairing is required again"
		b.mu.Unlock()
	}
}

func (b *Bridge) ingestHistory(h *events.HistorySync) {
	b.mu.Lock()
	client := b.client
	b.mu.Unlock()
	if client == nil || h.Data == nil {
		return
	}
	for _, conv := range h.Data.GetConversations() {
		chat, err := types.ParseJID(conv.GetID())
		if err != nil {
			continue
		}
		name := conv.GetName()
		if name == "" {
			name = conv.GetDisplayName()
		}
		_ = b.journal.SetChatName(chat.String(), name, chat.Server == types.GroupServer)
		for _, hm := range conv.GetMessages() {
			evt, err := client.ParseWebMessage(chat, hm.GetMessage())
			if err != nil {
				continue
			}
			b.ingest(evt.Info, evt.Message, evt.IsEdit, "history")
		}
	}
}

func (b *Bridge) ingest(info types.MessageInfo, msg *waE2E.Message, isEdit bool, source string) {
	ev, rawMedia, ok := convertMessage(info, msg, isEdit, source, b.resolvePN)
	if !ok {
		return
	}
	if _, err := b.journal.Append(ev, rawMedia); err != nil {
		// Failing to journal must be visible: the adapter would otherwise never see it.
		b.setError("journal write failed: " + err.Error())
		b.log.Error("journal append failed", "error", err.Error())
		return
	}
	if b.journal.ChatName(ev.ChatJID) == "" {
		b.nameAsync(info.Chat)
	}
}

func (b *Bridge) resolvePN(lid types.JID) string {
	b.mu.Lock()
	client := b.client
	b.mu.Unlock()
	if client == nil || client.Store == nil || client.Store.LIDs == nil {
		return ""
	}
	pn, err := client.Store.LIDs.GetPNForLID(context.Background(), lid)
	if err != nil || pn.IsEmpty() {
		return ""
	}
	return pn.ToNonAD().String()
}

// nameAsync fills in a chat title (group subject or saved contact name) off the
// event path, once per chat.
func (b *Bridge) nameAsync(chat types.JID) {
	key := chat.String()
	b.mu.Lock()
	client := b.client
	if client == nil || b.resolving[key] {
		b.mu.Unlock()
		return
	}
	b.resolving[key] = true
	b.mu.Unlock()
	go func() {
		defer func() {
			b.mu.Lock()
			delete(b.resolving, key)
			b.mu.Unlock()
		}()
		ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		name := ""
		if chat.Server == types.GroupServer {
			if info, err := client.GetGroupInfo(ctx, chat); err == nil {
				name = info.Name
			}
		} else if client.Store != nil && client.Store.Contacts != nil {
			if c, err := client.Store.Contacts.GetContact(ctx, chat); err == nil {
				name = c.FullName
				if name == "" {
					name = c.PushName
				}
			}
		}
		_ = b.journal.SetChatName(key, name, chat.Server == types.GroupServer)
	}()
}

// ResetSession unlinks this device (best effort) and starts a fresh pairing.
func (b *Bridge) ResetSession(ctx context.Context) error {
	b.mu.Lock()
	client := b.client
	b.mu.Unlock()
	if client != nil {
		if client.IsLoggedIn() {
			_ = client.Logout(ctx)
		}
		client.Disconnect()
		if client.Store != nil && client.Store.ID != nil {
			_ = client.Store.Delete(ctx)
		}
	}
	b.mu.Lock()
	b.state, b.accountJID, b.qrCode, b.lastError = StateStarting, "", "", ""
	b.mu.Unlock()
	return b.start(ctx)
}

func (b *Bridge) pruneLoop(ctx context.Context) {
	ticker := time.NewTicker(time.Hour)
	defer ticker.Stop()
	for {
		if err := b.journal.Prune(b.cfg.UnselectedKeep, b.cfg.MediaKeep); err != nil {
			b.log.Error("prune failed", "error", err.Error())
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (b *Bridge) Close() {
	b.mu.Lock()
	client := b.client
	b.mu.Unlock()
	if client != nil {
		client.Disconnect()
	}
}
