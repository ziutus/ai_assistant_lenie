import { buildObsidianNoteUrl } from "./obsidian";

/**
 * Converts internal source identifiers to locations a browser can open.
 * Email imports retain the gmail:// scheme in the database as a stable,
 * provider-specific identity; Gmail itself exposes these message IDs through
 * its web UI fragment.
 */
const gmailMessageId = (url: string | undefined): string | null => {
  const match = /^gmail:\/\/([^/?#]+)\/?$/i.exec(url?.trim() ?? "");
  return match?.[1] ?? null;
};

// obsidian_note documents store obsidian://<vault-relative-path> as a stable
// dedup identity (_note_url() in obsidian_reimport_service.py) -- it is NOT
// a real Obsidian URI (that's "obsidian://open?vault=...&file=..."), so
// opening it directly shows Obsidian's "nieznana akcja" (unknown action):
// Obsidian reads the first path segment after "obsidian://" as the action
// name. Extract the relative path and hand it to buildObsidianNoteUrl(),
// same as the note-path links already built elsewhere in the app.
const obsidianNoteRelativePath = (url: string | undefined): string | null => {
  const match = /^obsidian:\/\/(?!open(?:\?|$))(.+)$/i.exec(url?.trim() ?? "");
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
};

export const toOpenableSourceUrl = (url: string, originalUrl?: string): string => {
  const messageId = gmailMessageId(url);
  if (messageId) {
    // canonicalize_url lower-cases a gmail:// URL.  Its ID is case-sensitive,
    // so prefer the original document URL whenever it is available.
    const originalMessageId = gmailMessageId(originalUrl);
    const id = originalMessageId ?? messageId;
    return `https://mail.google.com/mail/u/0/#all/${encodeURIComponent(id)}`;
  }

  const notePath = obsidianNoteRelativePath(url);
  if (notePath) return buildObsidianNoteUrl(notePath);

  return url;
};
