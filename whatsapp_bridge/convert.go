package main

import (
	"strings"

	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/types"
	"google.golang.org/protobuf/proto"
)

// convertMessage turns a decoded WhatsApp message into a journal event.
// ok is false for content that is not a chat message (reactions, polls, key
// distribution, other protocol traffic): those must never reach Lenie as text.
// rawMedia holds the serialized message when it carries a downloadable file.
func convertMessage(info types.MessageInfo, m *waE2E.Message, isEdit bool, source string,
	resolvePN func(types.JID) string) (ev Event, rawMedia []byte, ok bool) {
	if m == nil {
		return Event{}, nil, false
	}
	ev = Event{
		ChatJID:    info.Chat.String(),
		IsGroup:    info.IsGroup,
		WAID:       info.ID,
		SenderJID:  info.Sender.String(),
		SenderName: info.PushName,
		IsFromMe:   info.IsFromMe,
		Timestamp:  info.Timestamp.Unix(),
		Source:     source,
		Kind:       "message",
	}
	if !info.SenderAlt.IsEmpty() {
		ev.SenderAlt = info.SenderAlt.String()
	}
	ev.SenderPN = senderPN(info, resolvePN)

	if pm := m.GetProtocolMessage(); pm != nil {
		switch pm.GetType() {
		case waE2E.ProtocolMessage_REVOKE:
			ev.Kind, ev.WAID, ev.MessageType = "revoke", pm.GetKey().GetID(), "deleted"
			return ev, nil, ev.WAID != ""
		case waE2E.ProtocolMessage_MESSAGE_EDIT:
			inner := pm.GetEditedMessage()
			ev.Kind, ev.WAID, ev.DedupVariant = "edit", pm.GetKey().GetID(), info.Timestamp.UnixNano()
			ev.MessageType, ev.Text = "text", textOf(inner)
			if ev.WAID == "" || ev.Text == "" {
				return Event{}, nil, false
			}
			return ev, nil, true
		default:
			return Event{}, nil, false
		}
	}
	if isEdit {
		ev.Kind, ev.DedupVariant = "edit", info.Timestamp.UnixNano()
	}

	mtype, text, media, hasFile := classify(m)
	if mtype == "" {
		return Event{}, nil, false
	}
	ev.MessageType, ev.Text, ev.Media = mtype, text, media
	if hasFile {
		raw, err := proto.Marshal(m)
		if err == nil {
			rawMedia = raw
		}
	}
	return ev, rawMedia, true
}

// senderPN returns the phone-number JID of the sender when it is known, so a
// LID-addressed participant can still be matched to a contact by number.
func senderPN(info types.MessageInfo, resolvePN func(types.JID) string) string {
	if info.Sender.Server == types.DefaultUserServer {
		return info.Sender.ToNonAD().String()
	}
	if info.SenderAlt.Server == types.DefaultUserServer {
		return info.SenderAlt.ToNonAD().String()
	}
	if info.Sender.Server == types.HiddenUserServer && resolvePN != nil {
		return resolvePN(info.Sender)
	}
	return ""
}

func textOf(m *waE2E.Message) string {
	if m == nil {
		return ""
	}
	if t := m.GetConversation(); t != "" {
		return t
	}
	if t := m.GetExtendedTextMessage().GetText(); t != "" {
		return t
	}
	return ""
}

// classify returns the Lenie message type, text/caption, attachment metadata
// and whether the message has a downloadable file. An empty type means "skip".
func classify(m *waE2E.Message) (mtype, text string, media *MediaInfo, hasFile bool) {
	switch {
	case m.GetReactionMessage() != nil, m.GetPollCreationMessage() != nil, m.GetPollUpdateMessage() != nil,
		m.GetSenderKeyDistributionMessage() != nil && textOf(m) == "":
		return "", "", nil, false
	case m.GetImageMessage() != nil:
		i := m.GetImageMessage()
		return "image", i.GetCaption(), &MediaInfo{Mime: i.GetMimetype(), Size: int64(i.GetFileLength())}, true
	case m.GetVideoMessage() != nil:
		v := m.GetVideoMessage()
		return "video", v.GetCaption(), &MediaInfo{Mime: v.GetMimetype(), Size: int64(v.GetFileLength())}, true
	case m.GetAudioMessage() != nil:
		a := m.GetAudioMessage()
		return "audio", "", &MediaInfo{Mime: a.GetMimetype(), Size: int64(a.GetFileLength())}, true
	case m.GetDocumentMessage() != nil:
		d := m.GetDocumentMessage()
		return "document", d.GetCaption(),
			&MediaInfo{Mime: d.GetMimetype(), Filename: d.GetFileName(), Size: int64(d.GetFileLength())}, true
	case m.GetStickerMessage() != nil:
		s := m.GetStickerMessage()
		return "sticker", "", &MediaInfo{Mime: s.GetMimetype(), Size: int64(s.GetFileLength())}, true
	case m.GetContactMessage() != nil:
		return "contact_card", strings.TrimSpace(m.GetContactMessage().GetDisplayName()), nil, false
	case m.GetContactsArrayMessage() != nil:
		return "contact_card", strings.TrimSpace(m.GetContactsArrayMessage().GetDisplayName()), nil, false
	}
	if t := textOf(m); t != "" {
		return "text", t, nil, false
	}
	return "", "", nil, false
}
