package main

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"
	"time"

	"go.mau.fi/whatsmeow/types"
)

func TestMapGroups(t *testing.T) {
	lid := types.NewJID("1234", types.HiddenUserServer)
	pn := types.NewJID("48123456789", types.DefaultUserServer)
	parent := types.NewJID("1203000", types.GroupServer)
	group := &types.GroupInfo{
		JID:               types.NewJID("1203630", types.GroupServer),
		GroupName:         types.GroupName{Name: "Group"},
		GroupLinkedParent: types.GroupLinkedParent{LinkedParentJID: parent},
		GroupAnnounce:     types.GroupAnnounce{IsAnnounce: true},
		GroupIsDefaultSub: types.GroupIsDefaultSub{IsDefaultSubGroup: true},
		Participants: []types.GroupParticipant{
			{JID: lid, LID: lid, DisplayName: "48***89"},
			{JID: lid, LID: lid, PhoneNumber: pn, IsAdmin: true, IsSuperAdmin: true},
			{JID: pn},
		},
	}
	community := &types.GroupInfo{JID: parent, GroupParent: types.GroupParent{IsParent: true}, ParticipantCount: 42}
	out := mapGroups([]*types.GroupInfo{group, community}, time.Date(2026, 10, 30, 13, 0, 0, 0, time.FixedZone("CET", 3600)), nil)
	if out.FetchedAt != "2026-10-30T12:00:00Z" || len(out.Groups) != 2 {
		t.Fatalf("unexpected snapshot: %+v", out)
	}
	g := out.Groups[0]
	if g.JID != group.JID.String() || g.Name != "Group" || g.ParentJID != parent.String() || g.IsCommunity || !g.IsAnnounce || !g.IsDefaultSub || g.ParticipantCount != 3 {
		t.Fatalf("unexpected subgroup: %+v", g)
	}
	want := []groupParticipantResponse{
		{JID: lid.String(), LID: lid.String(), DisplayName: "48***89"},
		{JID: lid.String(), LID: lid.String(), Phone: pn.User, IsAdmin: true, IsSuperAdmin: true},
		{JID: pn.String(), Phone: pn.User},
	}
	if !reflect.DeepEqual(g.Participants, want) {
		t.Fatalf("participants: got %+v, want %+v", g.Participants, want)
	}
	c := out.Groups[1]
	if !c.IsCommunity || c.ParentJID != "" || c.ParticipantCount != 42 || c.Participants == nil {
		t.Fatalf("unexpected community: %+v", c)
	}
	data, err := json.Marshal(mapGroups(nil, time.Now(), nil))
	if err != nil {
		t.Fatal(err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatal(err)
	}
	if groups, ok := decoded["groups"].([]any); !ok || len(groups) != 0 {
		t.Fatalf("empty groups must be an array: %s", data)
	}
}

type fakeGroupsSource struct {
	loggedIn bool
	calls    int
	err      error
	t        *testing.T
}

func (s *fakeGroupsSource) IsLoggedIn() bool { return s.loggedIn }
func (s *fakeGroupsSource) GetJoinedGroups(ctx context.Context) ([]*types.GroupInfo, error) {
	s.calls++
	deadline, ok := ctx.Deadline()
	if !ok || time.Until(deadline) > 30*time.Second || time.Until(deadline) <= 0 {
		s.t.Error("expected 30-second request timeout")
	}
	return nil, s.err
}

func TestGroupsCache(t *testing.T) {
	cache := &groupsCache{}
	source := &fakeGroupsSource{loggedIn: true, t: t}
	request := func() *httptest.ResponseRecorder {
		w := httptest.NewRecorder()
		cache.serve(w, httptest.NewRequest(http.MethodGet, "/groups", nil), source)
		return w
	}
	first, second := request(), request()
	if first.Code != http.StatusOK || second.Code != http.StatusOK || source.calls != 1 || first.Body.String() != second.Body.String() {
		t.Fatal("second request must reuse the snapshot")
	}
	cache.fetchedAt = time.Now().Add(-61 * time.Second)
	if request().Code != http.StatusOK || source.calls != 2 {
		t.Fatal("expired snapshot must refresh")
	}
	source.loggedIn = false
	if w := request(); w.Code != http.StatusServiceUnavailable || w.Body.String() != "{\"error\":\"not_connected\"}\n" {
		t.Fatalf("cached snapshot served while logged out: %s", w.Body)
	}
	source.loggedIn = true
	source.err = errors.New("private upstream details")
	if w := request(); w.Code != http.StatusBadGateway || w.Body.String() != "{\"error\":\"groups_fetch_failed\"}\n" {
		t.Fatalf("unexpected failure response: %s", w.Body)
	}
	source.err = nil
	if request().Code != http.StatusOK || source.calls != 4 {
		t.Fatal("failed fetch must not be cached")
	}
	replacement := &fakeGroupsSource{loggedIn: true, t: t}
	w := httptest.NewRecorder()
	cache.serve(w, httptest.NewRequest(http.MethodGet, "/groups", nil), replacement)
	if w.Code != http.StatusOK || replacement.calls != 1 {
		t.Fatal("new client must not reuse old snapshot")
	}
}

func TestGroupsRouteAuthAndMissingClient(t *testing.T) {
	b := &Bridge{cfg: Config{Token: "test-token"}}
	for _, token := range []string{"", "test-token"} {
		r := httptest.NewRequest(http.MethodGet, "/groups", nil)
		if token != "" {
			r.Header.Set("Authorization", "Bearer "+token)
		}
		w := httptest.NewRecorder()
		b.Routes().ServeHTTP(w, r)
		if token == "" {
			if w.Code != http.StatusUnauthorized {
				t.Fatalf("want 401, got %d", w.Code)
			}
		} else if w.Code != http.StatusServiceUnavailable || w.Body.String() != "{\"error\":\"not_connected\"}\n" {
			t.Fatalf("missing client: got %d %s", w.Code, w.Body)
		}
	}
}

func TestMapGroupsUsesContactStoreNames(t *testing.T) {
	lid := types.NewJID("1234", types.HiddenUserServer)
	pn := types.NewJID("48123456789", types.DefaultUserServer)
	group := &types.GroupInfo{JID: types.NewJID("1203630", types.GroupServer), Participants: []types.GroupParticipant{
		{JID: pn, DisplayName: "48***89"},
		{JID: lid, LID: lid, PhoneNumber: pn},
		{JID: types.NewJID("48999", types.DefaultUserServer), DisplayName: "48***99"},
	}}
	names := func(jids ...types.JID) string {
		for _, jid := range jids {
			if jid == pn || jid == lid {
				return "Anna"
			}
		}
		return ""
	}
	got := mapGroups([]*types.GroupInfo{group}, time.Now(), names).Groups[0].Participants
	if got[0].DisplayName != "Anna" || got[1].DisplayName != "Anna" || got[2].DisplayName != "48***99" {
		t.Fatalf("unexpected names: %+v", got)
	}
}
