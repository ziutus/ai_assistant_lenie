package main

import (
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

// Event is one journal entry served to the Lenie adapter. Message content lives
// here only until the adapter acknowledges it; the bridge never logs it.
type Event struct {
	Seq          int64      `json:"seq"`
	Kind         string     `json:"kind"` // message | edit | revoke
	ChatJID      string     `json:"chat_jid"`
	IsGroup      bool       `json:"is_group"`
	WAID         string     `json:"wa_message_id"`
	SenderJID    string     `json:"sender_jid"`
	SenderAlt    string     `json:"sender_alt_jid,omitempty"`
	SenderPN     string     `json:"sender_pn,omitempty"` // phone-number JID when known (resolved from a LID)
	SenderName   string     `json:"sender_name,omitempty"`
	IsFromMe     bool       `json:"is_from_me"`
	Timestamp    int64      `json:"timestamp"`
	MessageType  string     `json:"message_type"`
	Text         string     `json:"text,omitempty"`
	Media        *MediaInfo `json:"media,omitempty"`
	Source       string     `json:"source"` // live | history
	DedupVariant int64      `json:"-"`
}

// MediaInfo describes an attachment without its bytes.
type MediaInfo struct {
	Mime     string `json:"mime,omitempty"`
	Filename string `json:"filename,omitempty"`
	Size     int64  `json:"size"`
}

// Chat is a conversation the account has seen (selected or not).
type Chat struct {
	JID      string `json:"jid"`
	Name     string `json:"name"`
	IsGroup  bool   `json:"is_group"`
	LastTS   int64  `json:"last_message_ts"`
	Buffered int64  `json:"buffered_events"`
	Allowed  bool   `json:"allowed"`
}

type Journal struct {
	db *sql.DB
}

const journalSchema = `
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_jid TEXT NOT NULL,
  kind TEXT NOT NULL,
  wa_id TEXT NOT NULL,
  variant INTEGER NOT NULL DEFAULT 0,
  payload TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  UNIQUE (chat_jid, kind, wa_id, variant)
);
CREATE INDEX IF NOT EXISTS idx_events_chat_seq ON events (chat_jid, seq);
CREATE TABLE IF NOT EXISTS chats (
  jid TEXT PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  is_group INTEGER NOT NULL DEFAULT 0,
  last_ts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS allowlist (jid TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS media (
  chat_jid TEXT NOT NULL,
  wa_id TEXT NOT NULL,
  raw BLOB NOT NULL,
  size INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (chat_jid, wa_id)
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
`

func OpenJournal(path string) (*Journal, error) {
	db, err := sql.Open("sqlite", "file:"+path+"?_pragma=busy_timeout(10000)&_pragma=journal_mode(WAL)&_pragma=synchronous(FULL)")
	if err != nil {
		return nil, err
	}
	// One writer at a time keeps SQLite simple; reads are tiny.
	db.SetMaxOpenConns(1)
	if _, err := db.Exec(journalSchema); err != nil {
		_ = db.Close()
		return nil, err
	}
	j := &Journal{db: db}
	// The epoch identifies this journal file. If the volume is ever recreated the
	// sequence restarts, and the adapter uses a changed epoch to reset its cursors.
	if j.Meta("epoch") == "" {
		buf := make([]byte, 12)
		if _, err := rand.Read(buf); err != nil {
			_ = db.Close()
			return nil, err
		}
		if err := j.SetMeta("epoch", hex.EncodeToString(buf)); err != nil {
			_ = db.Close()
			return nil, err
		}
	}
	return j, nil
}

func (j *Journal) Epoch() string { return j.Meta("epoch") }

func (j *Journal) Close() error { return j.db.Close() }

// Append stores an event once. Redelivery of the same message (live + history,
// reconnects) hits the unique key and is ignored. rawMedia is kept so the bytes
// can be fetched later, independently of the message itself.
func (j *Journal) Append(ev Event, rawMedia []byte) (inserted bool, err error) {
	payload, err := json.Marshal(ev)
	if err != nil {
		return false, err
	}
	tx, err := j.db.Begin()
	if err != nil {
		return false, err
	}
	defer func() { _ = tx.Rollback() }()
	res, err := tx.Exec(
		`INSERT OR IGNORE INTO events (chat_jid, kind, wa_id, variant, payload, created_at) VALUES (?,?,?,?,?,?)`,
		ev.ChatJID, ev.Kind, ev.WAID, ev.DedupVariant, string(payload), time.Now().Unix(),
	)
	if err != nil {
		return false, err
	}
	n, _ := res.RowsAffected()
	inserted = n > 0
	if inserted && len(rawMedia) > 0 && ev.Media != nil {
		if _, err = tx.Exec(
			`INSERT OR IGNORE INTO media (chat_jid, wa_id, raw, size, created_at) VALUES (?,?,?,?,?)`,
			ev.ChatJID, ev.WAID, rawMedia, ev.Media.Size, time.Now().Unix(),
		); err != nil {
			return false, err
		}
	}
	if _, err = tx.Exec(
		`INSERT INTO chats (jid, is_group, last_ts) VALUES (?,?,?)
		 ON CONFLICT(jid) DO UPDATE SET is_group = excluded.is_group, last_ts = MAX(chats.last_ts, excluded.last_ts)`,
		ev.ChatJID, boolInt(ev.IsGroup), ev.Timestamp,
	); err != nil {
		return false, err
	}
	return inserted, tx.Commit()
}

func boolInt(b bool) int {
	if b {
		return 1
	}
	return 0
}

// SetChatName records a display name; an empty name never overwrites a known one.
func (j *Journal) SetChatName(jid, name string, isGroup bool) error {
	if strings.TrimSpace(name) == "" {
		return nil
	}
	_, err := j.db.Exec(
		`INSERT INTO chats (jid, name, is_group) VALUES (?,?,?)
		 ON CONFLICT(jid) DO UPDATE SET name = excluded.name`, jid, name, boolInt(isGroup))
	return err
}

func (j *Journal) ChatName(jid string) string {
	var name string
	_ = j.db.QueryRow(`SELECT name FROM chats WHERE jid = ?`, jid).Scan(&name)
	return name
}

// Events returns events of one chat after the given sequence, oldest first.
func (j *Journal) Events(chatJID string, after int64, limit int) ([]Event, error) {
	if limit <= 0 || limit > 500 {
		limit = 200
	}
	rows, err := j.db.Query(
		`SELECT seq, payload FROM events WHERE chat_jid = ? AND seq > ? ORDER BY seq LIMIT ?`, chatJID, after, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Event{}
	for rows.Next() {
		var seq int64
		var payload string
		if err := rows.Scan(&seq, &payload); err != nil {
			return nil, err
		}
		var ev Event
		if err := json.Unmarshal([]byte(payload), &ev); err != nil {
			return nil, err
		}
		ev.Seq = seq
		out = append(out, ev)
	}
	return out, rows.Err()
}

// Ack drops events of a chat up to and including seq: the adapter has stored them.
func (j *Journal) Ack(chatJID string, upto int64) (int64, error) {
	res, err := j.db.Exec(`DELETE FROM events WHERE chat_jid = ? AND seq <= ?`, chatJID, upto)
	if err != nil {
		return 0, err
	}
	return res.RowsAffected()
}

func (j *Journal) SetAllowlist(jids []string) error {
	tx, err := j.db.Begin()
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.Exec(`DELETE FROM allowlist`); err != nil {
		return err
	}
	for _, jid := range jids {
		if jid = strings.TrimSpace(jid); jid != "" {
			if _, err := tx.Exec(`INSERT OR IGNORE INTO allowlist (jid) VALUES (?)`, jid); err != nil {
				return err
			}
		}
	}
	return tx.Commit()
}

func (j *Journal) Allowlist() ([]string, error) {
	rows, err := j.db.Query(`SELECT jid FROM allowlist ORDER BY jid`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []string{}
	for rows.Next() {
		var jid string
		if err := rows.Scan(&jid); err != nil {
			return nil, err
		}
		out = append(out, jid)
	}
	return out, rows.Err()
}

func (j *Journal) Chats() ([]Chat, error) {
	rows, err := j.db.Query(`
		SELECT c.jid, c.name, c.is_group, c.last_ts,
		       (SELECT COUNT(*) FROM events e WHERE e.chat_jid = c.jid),
		       EXISTS (SELECT 1 FROM allowlist a WHERE a.jid = c.jid)
		FROM chats c ORDER BY c.last_ts DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Chat{}
	for rows.Next() {
		var c Chat
		var grp, allowed int
		if err := rows.Scan(&c.JID, &c.Name, &grp, &c.LastTS, &c.Buffered, &allowed); err != nil {
			return nil, err
		}
		c.IsGroup, c.Allowed = grp == 1, allowed == 1
		out = append(out, c)
	}
	return out, rows.Err()
}

// Prune removes buffered events of chats that are not selected once they are
// older than retention, so private chats nobody asked for do not pile up.
// A retention of zero or less removes them immediately.
func (j *Journal) Prune(retention time.Duration, mediaRetention time.Duration) error {
	cutoff := time.Now().Add(-retention).Unix()
	if _, err := j.db.Exec(
		`DELETE FROM events WHERE created_at <= ? AND chat_jid NOT IN (SELECT jid FROM allowlist)`, cutoff); err != nil {
		return err
	}
	_, err := j.db.Exec(`DELETE FROM media WHERE created_at <= ?`, time.Now().Add(-mediaRetention).Unix())
	return err
}

func (j *Journal) Media(chatJID, waID string) ([]byte, int64, error) {
	var raw []byte
	var size int64
	err := j.db.QueryRow(`SELECT raw, size FROM media WHERE chat_jid = ? AND wa_id = ?`, chatJID, waID).Scan(&raw, &size)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, 0, ErrNotFound
	}
	return raw, size, err
}

func (j *Journal) DeleteMedia(chatJID, waID string) error {
	_, err := j.db.Exec(`DELETE FROM media WHERE chat_jid = ? AND wa_id = ?`, chatJID, waID)
	return err
}

func (j *Journal) MaxSeq() int64 {
	var seq sql.NullInt64
	_ = j.db.QueryRow(`SELECT MAX(seq) FROM events`).Scan(&seq)
	return seq.Int64
}

func (j *Journal) SetMeta(key, value string) error {
	_, err := j.db.Exec(`INSERT INTO meta (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value = excluded.value`, key, value)
	return err
}

func (j *Journal) Meta(key string) string {
	var v string
	_ = j.db.QueryRow(`SELECT value FROM meta WHERE key = ?`, key).Scan(&v)
	return v
}

var ErrNotFound = fmt.Errorf("not found")
