package main

import (
	"context"
	"net/http"
	"sync"
	"time"

	"go.mau.fi/whatsmeow/types"
)

type groupsResponse struct {
	Groups    []groupResponse `json:"groups"`
	FetchedAt string          `json:"fetched_at"`
}

type groupResponse struct {
	JID              string                     `json:"jid"`
	Name             string                     `json:"name"`
	IsCommunity      bool                       `json:"is_community"`
	ParentJID        string                     `json:"parent_jid"`
	IsAnnounce       bool                       `json:"is_announce"`
	IsDefaultSub     bool                       `json:"is_default_sub"`
	ParticipantCount int                        `json:"participant_count"`
	Participants     []groupParticipantResponse `json:"participants"`
}

type groupParticipantResponse struct {
	JID          string `json:"jid"`
	LID          string `json:"lid"`
	Phone        string `json:"phone"`
	IsAdmin      bool   `json:"is_admin"`
	IsSuperAdmin bool   `json:"is_super_admin"`
	DisplayName  string `json:"display_name"`
}

// mapGroups converts a WhatsApp snapshot. names (may be nil) resolves a participant's human name
// from the account's contact store; GroupInfo itself only carries a masked placeholder (or nothing).
func mapGroups(groups []*types.GroupInfo, fetchedAt time.Time, names func(...types.JID) string) groupsResponse {
	out := groupsResponse{Groups: make([]groupResponse, 0, len(groups)), FetchedAt: fetchedAt.UTC().Format(time.RFC3339)}
	for _, group := range groups {
		if group == nil {
			continue
		}
		mapped := groupResponse{
			JID: group.JID.String(), Name: group.Name, IsCommunity: group.IsParent,
			IsAnnounce: group.IsAnnounce, IsDefaultSub: group.IsDefaultSubGroup,
			ParticipantCount: group.ParticipantCount,
			Participants:     make([]groupParticipantResponse, 0, len(group.Participants)),
		}
		if !group.LinkedParentJID.IsEmpty() {
			mapped.ParentJID = group.LinkedParentJID.String()
		}
		if mapped.ParticipantCount == 0 {
			mapped.ParticipantCount = len(group.Participants)
		}
		for _, participant := range group.Participants {
			p := groupParticipantResponse{
				JID: participant.JID.String(), IsAdmin: participant.IsAdmin,
				IsSuperAdmin: participant.IsSuperAdmin, DisplayName: participant.DisplayName,
			}
			if names != nil {
				if name := names(participant.JID, participant.LID, participant.PhoneNumber); name != "" {
					p.DisplayName = name
				}
			}
			if !participant.LID.IsEmpty() {
				p.LID = participant.LID.String()
			}
			if !participant.PhoneNumber.IsEmpty() {
				p.Phone = participant.PhoneNumber.User
			} else if participant.JID.Server == types.DefaultUserServer {
				p.Phone = participant.JID.User
			}
			mapped.Participants = append(mapped.Participants, p)
		}
		out.Groups = append(out.Groups, mapped)
	}
	return out
}

type groupsSource interface {
	IsLoggedIn() bool
	GetJoinedGroups(context.Context) ([]*types.GroupInfo, error)
}

type groupsCache struct {
	names     func(context.Context, ...types.JID) string // contact-store lookup; nil in tests
	mu        sync.Mutex
	source    groupsSource
	response  groupsResponse
	fetchedAt time.Time
}

func (b *Bridge) handleGroups(w http.ResponseWriter, r *http.Request) {
	b.mu.Lock()
	client := b.client
	connected := b.state == StateConnected
	b.mu.Unlock()
	var source groupsSource
	if client != nil && connected {
		source = client
	}
	b.groups.serve(w, r, source)
}

func (cache *groupsCache) serve(w http.ResponseWriter, r *http.Request, source groupsSource) {
	// Serialize refreshes so concurrent requests share a single WhatsApp query.
	cache.mu.Lock()
	defer cache.mu.Unlock()
	if source == nil || !source.IsLoggedIn() {
		cache.source = nil
		cache.response = groupsResponse{}
		cache.fetchedAt = time.Time{}
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "not_connected"})
		return
	}
	if cache.source == source && time.Since(cache.fetchedAt) < 60*time.Second {
		writeJSON(w, http.StatusOK, cache.response)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	groups, err := source.GetJoinedGroups(ctx)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": "groups_fetch_failed"})
		return
	}
	cache.fetchedAt = time.Now()
	var resolve func(...types.JID) string
	if cache.names != nil {
		resolve = func(jids ...types.JID) string { return cache.names(ctx, jids...) }
	}
	cache.response = mapGroups(groups, cache.fetchedAt, resolve)
	cache.source = source
	writeJSON(w, http.StatusOK, cache.response)
}
