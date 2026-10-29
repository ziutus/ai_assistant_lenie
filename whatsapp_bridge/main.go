// Command whatsapp_bridge is a receive-only WhatsApp companion device for Lenie.
//
// It links to one account as an additional device (QR pairing), journals the
// messages it receives into a durable SQLite file and serves them to the Lenie
// adapter over an authenticated REST API. It has no code path that sends
// messages, replies or marks anything as read, and it never logs message text.
package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"syscall"
	"time"
)

type Config struct {
	Token             string
	DataDir           string
	Addr              string
	MaxMediaBytes     int64
	MediaConcurrency  int
	UnselectedKeep    time.Duration
	MediaKeep         time.Duration
	DeviceName        string
	TrustedProxyHosts string
}

func envInt(key string, def int64) int64 {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.ParseInt(v, 10, 64); err == nil {
			return n
		}
	}
	return def
}

func loadConfig() (Config, error) {
	cfg := Config{
		Token:            os.Getenv("WA_BRIDGE_TOKEN"),
		DataDir:          envOr("WA_BRIDGE_DATA_DIR", "/data"),
		Addr:             envOr("WA_BRIDGE_ADDR", ":8095"),
		MaxMediaBytes:    envInt("WA_BRIDGE_MAX_MEDIA_BYTES", 50<<20),
		MediaConcurrency: int(envInt("WA_BRIDGE_MEDIA_CONCURRENCY", 2)),
		UnselectedKeep:   time.Duration(envInt("WA_BRIDGE_UNSELECTED_RETENTION_HOURS", 168)) * time.Hour,
		MediaKeep:        time.Duration(envInt("WA_BRIDGE_MEDIA_RETENTION_DAYS", 30)) * 24 * time.Hour,
		DeviceName:       envOr("WA_BRIDGE_DEVICE_NAME", "Lenie archive"),
	}
	if len(cfg.Token) < 16 {
		return cfg, errConfig("WA_BRIDGE_TOKEN must be set to a secret of at least 16 characters")
	}
	if cfg.MediaConcurrency < 1 {
		cfg.MediaConcurrency = 1
	}
	return cfg, nil
}

type errConfig string

func (e errConfig) Error() string { return string(e) }

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func main() {
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelInfo}))
	cfg, err := loadConfig()
	if err != nil {
		logger.Error("configuration", "error", err.Error())
		os.Exit(2)
	}
	if err := os.MkdirAll(cfg.DataDir, 0o700); err != nil {
		logger.Error("data dir", "error", err.Error())
		os.Exit(2)
	}
	journal, err := OpenJournal(filepath.Join(cfg.DataDir, "journal.db"))
	if err != nil {
		logger.Error("journal", "error", err.Error())
		os.Exit(2)
	}
	defer journal.Close()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	bridge := NewBridge(cfg, journal, logger)
	go bridge.Run(ctx)
	go bridge.pruneLoop(ctx)

	srv := &http.Server{Addr: cfg.Addr, Handler: bridge.Routes(), ReadHeaderTimeout: 10 * time.Second}
	go func() {
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutdown)
	}()
	logger.Info("listening", "addr", cfg.Addr)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		logger.Error("server", "error", err.Error())
		os.Exit(1)
	}
	bridge.Close()
}
