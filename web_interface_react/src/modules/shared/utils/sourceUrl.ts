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

export const toOpenableSourceUrl = (url: string, originalUrl?: string): string => {
  const messageId = gmailMessageId(url);
  if (!messageId) return url;

  // canonicalize_url lower-cases a gmail:// URL.  Its ID is case-sensitive,
  // so prefer the original document URL whenever it is available.
  const originalMessageId = gmailMessageId(originalUrl);
  const id = originalMessageId ?? messageId;

  return `https://mail.google.com/mail/u/0/#all/${encodeURIComponent(id)}`;
};
