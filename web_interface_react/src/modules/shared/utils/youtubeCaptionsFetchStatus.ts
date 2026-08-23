// The captions retry endpoint is a single synchronous HTTP request with no
// persisted "in progress" DB state for its duration (see
// backend/library/youtube_processing.py) — processing_status only flips once
// the fetch has already finished. If it's triggered from /list and the user
// immediately navigates to /youtube/:id, the edit page's own fetch-in-flight
// state (useManageLLM's isLoading) knows nothing about it, since it's a
// separate hook instance. sessionStorage bridges that gap: it survives
// client-side route changes within the same tab, so the flag set on /list
// is still visible when /youtube/:id mounts moments later.
const KEY_PREFIX = "lenie_youtube_captions_fetching_";

export const markCaptionsFetching = (documentId: string | number, fetching: boolean): void => {
  try {
    if (fetching) {
      sessionStorage.setItem(`${KEY_PREFIX}${documentId}`, "1");
    } else {
      sessionStorage.removeItem(`${KEY_PREFIX}${documentId}`);
    }
  } catch {
    // sessionStorage unavailable (private browsing, etc.) — the indicator
    // is a convenience, not a source of truth, so just skip it.
  }
};

export const isCaptionsFetching = (documentId: string | number): boolean => {
  try {
    return sessionStorage.getItem(`${KEY_PREFIX}${documentId}`) === "1";
  } catch {
    return false;
  }
};
