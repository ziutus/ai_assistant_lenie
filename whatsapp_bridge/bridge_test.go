package main

import (
	"path/filepath"
	"testing"
	"time"

	"go.mau.fi/whatsmeow/proto/waCommon"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/types"
	"google.golang.org/protobuf/proto"
)

func testJournal(t *testing.T) *Journal {
	t.Helper()
	j, err := OpenJournal(filepath.Join(t.TempDir(), "journal.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = j.Close() })
	return j
}

func info(chat, sender string, fromMe bool, id string, ts time.Time) types.MessageInfo {
	c, _ := types.ParseJID(chat)
	s, _ := types.ParseJID(sender)
	return types.MessageInfo{
		MessageSource: types.MessageSource{Chat: c, Sender: s, IsFromMe: fromMe, IsGroup: c.Server == types.GroupServer},
		ID:            id, Timestamp: ts, PushName: "Ala",
	}
}

func text(s string) *waE2E.Message { return &waE2E.Message{Conversation: proto.String(s)} }

func TestRedeliveryDoesNotDuplicate(t *testing.T) {
	j := testJournal(t)
	ev, _, ok := convertMessage(info("48500@s.whatsapp.net", "48500@s.whatsapp.net", false, "A1", time.Unix(1000, 0)), text("hej"), false, "live", nil)
	if !ok {
		t.Fatal("text message must convert")
	}
	for i := 0; i < 3; i++ {
		if _, err := j.Append(ev, nil); err != nil {
			t.Fatal(err)
		}
	}
	evs, _ := j.Events("48500@s.whatsapp.net", 0, 10)
	if len(evs) != 1 {
		t.Fatalf("want 1 event after redelivery, got %d", len(evs))
	}
}

func TestOwnMessageAndLIDSender(t *testing.T) {
	lid := types.NewJID("123456789", types.HiddenUserServer)
	in := info("120363@g.us", lid.String(), false, "G1", time.Unix(2000, 0))
	pn := types.NewJID("48600600600", types.DefaultUserServer)
	in.SenderAlt = pn
	ev, _, ok := convertMessage(in, text("w grupie"), false, "history", nil)
	if !ok || ev.SenderJID != lid.String() || ev.SenderPN != pn.String() || !ev.IsGroup {
		t.Fatalf("LID sender must keep both identifiers: %+v", ev)
	}
	// A LID sender with no alt resolves through the store callback, or stays empty.
	in.SenderAlt = types.EmptyJID
	ev, _, _ = convertMessage(in, text("x"), false, "live", func(types.JID) string { return pn.String() })
	if ev.SenderPN != pn.String() {
		t.Fatalf("resolver not used: %+v", ev)
	}
	ev, _, _ = convertMessage(in, text("x"), false, "live", nil)
	if ev.SenderPN != "" {
		t.Fatalf("unknown LID must not be guessed: %+v", ev)
	}
	own, _, _ := convertMessage(info("48500@s.whatsapp.net", "48111@s.whatsapp.net", true, "O1", time.Unix(3, 0)), text("ja"), false, "live", nil)
	if !own.IsFromMe {
		t.Fatal("own message must be flagged")
	}
}

func TestEditAndRevokeAreSeparateEvents(t *testing.T) {
	in := info("48500@s.whatsapp.net", "48500@s.whatsapp.net", false, "E-ENV", time.Unix(4000, 0))
	edit := &waE2E.Message{ProtocolMessage: &waE2E.ProtocolMessage{
		Type:          waE2E.ProtocolMessage_MESSAGE_EDIT.Enum(),
		Key:           &waCommon.MessageKey{ID: proto.String("A1")},
		EditedMessage: text("poprawione"),
	}}
	ev, _, ok := convertMessage(in, edit, true, "live", nil)
	if !ok || ev.Kind != "edit" || ev.WAID != "A1" || ev.Text != "poprawione" {
		t.Fatalf("edit must target the original id: %+v", ev)
	}
	revoke := &waE2E.Message{ProtocolMessage: &waE2E.ProtocolMessage{
		Type: waE2E.ProtocolMessage_REVOKE.Enum(), Key: &waCommon.MessageKey{ID: proto.String("A1")},
	}}
	ev, _, ok = convertMessage(in, revoke, false, "live", nil)
	if !ok || ev.Kind != "revoke" || ev.WAID != "A1" || ev.Text != "" {
		t.Fatalf("revoke must carry no text: %+v", ev)
	}
}

func TestReactionsAndProtocolNoiseAreSkipped(t *testing.T) {
	in := info("48500@s.whatsapp.net", "48500@s.whatsapp.net", false, "R1", time.Unix(5, 0))
	for name, m := range map[string]*waE2E.Message{
		"reaction": {ReactionMessage: &waE2E.ReactionMessage{Text: proto.String("👍")}},
		"empty":    {},
		"history":  {ProtocolMessage: &waE2E.ProtocolMessage{Type: waE2E.ProtocolMessage_HISTORY_SYNC_NOTIFICATION.Enum()}},
	} {
		if _, _, ok := convertMessage(in, m, false, "live", nil); ok {
			t.Errorf("%s must not become a chat message", name)
		}
	}
}

func TestMediaDescriptorKeptAndAckedEventsDropped(t *testing.T) {
	j := testJournal(t)
	img := &waE2E.Message{ImageMessage: &waE2E.ImageMessage{
		Caption: proto.String("podpis"), Mimetype: proto.String("image/jpeg"), FileLength: proto.Uint64(1234),
	}}
	ev, raw, ok := convertMessage(info("48500@s.whatsapp.net", "48500@s.whatsapp.net", false, "M1", time.Unix(6, 0)), img, false, "live", nil)
	if !ok || ev.MessageType != "image" || ev.Text != "podpis" || ev.Media.Size != 1234 || len(raw) == 0 {
		t.Fatalf("image conversion: %+v", ev)
	}
	if _, err := j.Append(ev, raw); err != nil {
		t.Fatal(err)
	}
	evs, _ := j.Events(ev.ChatJID, 0, 10)
	if _, err := j.Ack(ev.ChatJID, evs[0].Seq); err != nil {
		t.Fatal(err)
	}
	if left, _ := j.Events(ev.ChatJID, 0, 10); len(left) != 0 {
		t.Fatal("acked events must be removed")
	}
	// The attachment stays fetchable after the message was acknowledged.
	if _, size, err := j.Media(ev.ChatJID, "M1"); err != nil || size != 1234 {
		t.Fatalf("media descriptor lost: %v", err)
	}
	if err := j.DeleteMedia(ev.ChatJID, "M1"); err != nil {
		t.Fatal(err)
	}
	if _, _, err := j.Media(ev.ChatJID, "M1"); err == nil {
		t.Fatal("media must be gone after delete")
	}
}

func TestPruneKeepsSelectedChatsOnly(t *testing.T) {
	j := testJournal(t)
	for _, chat := range []string{"1@s.whatsapp.net", "2@s.whatsapp.net"} {
		ev, _, _ := convertMessage(info(chat, chat, false, "X", time.Unix(7, 0)), text("t"), false, "live", nil)
		if _, err := j.Append(ev, nil); err != nil {
			t.Fatal(err)
		}
	}
	if err := j.SetAllowlist([]string{"1@s.whatsapp.net"}); err != nil {
		t.Fatal(err)
	}
	time.Sleep(1100 * time.Millisecond)
	if err := j.Prune(0, time.Hour); err != nil {
		t.Fatal(err)
	}
	if a, _ := j.Events("1@s.whatsapp.net", 0, 10); len(a) != 1 {
		t.Fatal("selected chat must be kept")
	}
	if b, _ := j.Events("2@s.whatsapp.net", 0, 10); len(b) != 0 {
		t.Fatal("unselected chat must be dropped")
	}
}
