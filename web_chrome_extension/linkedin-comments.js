// Self-contained: Chrome serializes this function into the active page, so it
// must not reference anything outside its own body.
//
// LinkedIn's post permalink page is a server-driven UI: comment nodes carry no
// semantic class names, only a `componentkey` that embeds the comment URN, e.g.
//   CommentComponentReference_urn:li:comment:(urn:li:activity:<ACT>,<COMMENT_ID>)
// The activity id inside that key is what scopes the capture to the open post
// and keeps a recommended / embedded post's comments out of it. Replies are not
// nested in the DOM — they sit as siblings of top-level comments in one
// virtualised list and are told apart only by the avatar's horizontal indent.
// A legacy branch keeps the older `.comments-comment-item` DOM working if a
// user still gets served it.
function extractLinkedInComments() {
  const activity = decodeURIComponent(location.href).match(/urn:li:activity:(\d+)/)?.[1]
    || location.href.match(/activity[:-](\d+)/)?.[1];
  if (!/(^|\.)linkedin\.com$/.test(location.hostname) || !activity) {
    throw new Error('Otwórz pojedynczy wpis LinkedIn (adres zawierający urn:li:activity).');
  }

  const NAME_SUFFIX = /\s*[•·|]\s*(?:1st|2nd|3rd\+?|Following|Follow|Author|Autor|Obserwuj(?:esz)?)\s*$/i;
  // A short "meta" line such as "3d", "(edited) 2w", "Edited • 5 mo".
  const REL_TIME = /(?:^|[\s•·])(\d+\s?(?:s|m|min|h|d|w|mo|y|yr|sek|godz|dni|tyg|mies|lata?))\s*$/i;

  function cleanName(link) {
    if (!link) return '';
    const holder = link.querySelector('p') || link;
    const aria = holder.querySelector('span[aria-hidden="true"]');
    let raw;
    if (aria) {
      const copy = aria.cloneNode(true);
      copy.querySelectorAll('*').forEach((el) => el.remove());
      raw = copy.textContent.trim();
    } else {
      raw = (holder.textContent || '').trim().split('\n')[0];
    }
    raw = raw.replace(NAME_SUFFIX, '').replace(/\s+/g, ' ').trim();
    // LinkedIn often renders the name twice ("AnnaAnna"): collapse the doubling.
    const half = raw.slice(0, Math.floor(raw.length / 2)).trim();
    if (half && raw === (half + half).replace(/\s+/g, ' ')) raw = half;
    return raw;
  }

  function canonicalUrl(href) {
    try {
      const url = new URL(href, location.href);
      if (!/^https?:$/.test(url.protocol)) return '';
      if (/(^|\.)linkedin\.com$/.test(url.hostname) && /^\/(safety\/go|redir)\b/.test(url.pathname)) {
        const target = url.searchParams.get('url') || url.searchParams.get('redirect');
        if (target) return canonicalUrl(target);
      }
      return `${url.origin}${url.pathname}`.replace(/\/$/, '');
    } catch (_) {
      return '';
    }
  }

  // A LinkedIn member / company / school / hashtag mention: the visible text
  // (a name or #tag) already carries the meaning, so its URL is left out — only
  // real content links get their href spelled out next to the label.
  function isMentionHref(href) {
    try {
      const url = new URL(href, location.href);
      return /(^|\.)linkedin\.com$/.test(url.hostname)
        && /^\/(in|company|school|pub|newsletters|feed\/hashtag)\//.test(url.pathname);
    } catch (_) {
      return false;
    }
  }

  function bodyText(box) {
    if (!box) return '';
    const copy = box.cloneNode(true);
    copy.querySelectorAll('button, [role="button"], [aria-hidden="true"]').forEach((el) => el.remove());
    copy.querySelectorAll('a[href]').forEach((link) => {
      const href = link.getAttribute('href');
      if (isMentionHref(href)) return;
      const url = canonicalUrl(href);
      const label = link.textContent.trim();
      const bare = url.replace(/^https?:\/\//i, '').toLowerCase();
      if (url && label && label.replace(/\/+$/, '').toLowerCase() !== bare) {
        link.append(document.createTextNode(` (${url})`));
      }
    });
    copy.querySelectorAll('br').forEach((br) => br.replaceWith(document.createTextNode('\n')));
    return copy.textContent
      .replace(/ /g, ' ')
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  function profileLink(root) {
    return [...root.querySelectorAll(
      'a[href*="/in/"], a[href*="/company/"], a[href*="/school/"], a[href*="/newsletters/"]'
    )].find((a) => a.textContent.trim() && !a.closest('[data-testid="expandable-text-box"]')) || null;
  }

  function timestampIn(root) {
    for (const el of root.querySelectorAll('time, p span, span')) {
      const text = el.textContent.trim();
      if (text.length > 24) continue;
      const match = text.match(REL_TIME);
      if (match) return match[1].replace(/\s+/g, '');
    }
    return '';
  }

  function declaredCommentTotal() {
    const button = [...document.querySelectorAll('button, [role="button"]')]
      .find((b) => /^(?:comment|komentarz|skomentuj)/i.test((b.getAttribute('aria-label') || '').trim()));
    const digits = (button?.textContent || '').replace(/[^\d]/g, '');
    return digits ? Number(digits) : null;
  }

  function sortLabel() {
    const button = [...document.querySelectorAll('button, [role="button"]')]
      .find((b) => /^(?:most relevant|most recent|top comments|newest|najbardziej trafne|najnowsze|najtrafniejsze)/i
        .test(b.textContent.trim()));
    return button ? button.textContent.trim().split('\n')[0] : '';
  }

  function summarise(comments, declaredTotal, sort, extraWarnings) {
    const replies = comments.filter((c) => c.isReply).length;
    const topLevel = comments.length - replies;
    const warnings = [...extraWarnings];
    if (!comments.length) {
      warnings.push('Rozpoznano wątek komentarzy, ale żaden nie miał czytelnej treści. Rozwiń komentarze na stronie i spróbuj ponownie.');
    }
    if (declaredTotal && topLevel < declaredTotal) {
      warnings.push(`Wpis ma ${declaredTotal} komentarzy, a załadowano ${topLevel} wątków głównych. Przewiń komentarze na stronie, aby doładować więcej, i pobierz ponownie — to jest tylko fragment dyskusji.`);
    }
    return {
      comments,
      captured: comments.length,
      topLevel,
      replies,
      declaredTotal,
      sort,
      warning: warnings.join(' '),
    };
  }

  // ---- Primary path: server-driven UI --------------------------------------
  const sduiRefs = [...document.querySelectorAll(
    `[componentkey^="CommentComponentReference_urn:li:comment:(urn:li:activity:${activity},"]`
  )];

  if (sduiRefs.length) {
    const byId = new Map();
    for (const ref of sduiRefs) {
      const id = (ref.getAttribute('componentkey').match(/,(\d+)\)$/) || [])[1];
      if (!id || byId.has(id) || !ref.getClientRects().length) continue;
      byId.set(id, ref);
    }

    const raw = [...byId.entries()].map(([id, ref]) => {
      const avatar = ref.querySelector('figure, img');
      const rect = avatar && avatar.getBoundingClientRect();
      const indent = rect && rect.width ? Math.round(rect.left) : null;
      const link = profileLink(ref);
      const box = ref.querySelector('[data-testid="expandable-text-box"]');
      const mention = box && box.querySelector('a[href*="/in/"], a[href*="/company/"]');
      const text = bodyText(box);
      const mentionName = mention ? mention.textContent.trim().replace(NAME_SUFFIX, '').trim() : '';
      const leadMention = mentionName && text.startsWith(mentionName) ? mentionName : '';
      return {
        id,
        indent,
        author: cleanName(link) || 'Autor nieodczytany',
        authorUrl: link ? canonicalUrl(link.getAttribute('href')) : '',
        text,
        timestamp: timestampIn(ref),
        leadMention,
      };
    }).filter((c) => c.text);

    const knownIndents = raw.map((c) => c.indent).filter((n) => n != null);
    const baseIndent = knownIndents.length ? Math.min(...knownIndents) : 0;
    let lastTopAuthor = '';
    const comments = raw.map((c) => {
      const isReply = c.indent != null && c.indent > baseIndent + 16;
      if (!isReply) lastTopAuthor = c.author;
      let text = c.text;
      let replyTo = '';
      if (isReply) {
        replyTo = c.leadMention || lastTopAuthor || '';
        // Drop the leading "@Name" echo when it only repeats replyTo.
        if (c.leadMention && c.leadMention === replyTo) {
          text = text.slice(c.leadMention.length).replace(/^[\s,:–—-]+/, '').trim() || text;
        }
      }
      return {
        id: c.id,
        author: c.author,
        authorUrl: c.authorUrl,
        text,
        timestamp: c.timestamp,
        isReply,
        replyTo,
      };
    });

    return summarise(comments, declaredCommentTotal(), sortLabel(), []);
  }

  // ---- Legacy path: older comment DOM -------------------------------------
  const roots = [...document.querySelectorAll('[data-urn], [data-id]')].filter((node) =>
    ['data-urn', 'data-id'].some((attr) => node.getAttribute(attr) === `urn:li:activity:${activity}`));
  const legacySelector = '.comments-comment-item, .comments-comment-entity';
  const root = roots.find((node) => node.querySelector(legacySelector));
  if (!root) {
    return summarise([], declaredCommentTotal(), '', [
      'Nie znaleziono komentarzy tego wpisu w drzewie strony. Rozwiń komentarze i odpowiedzi na stronie, a potem otwórz wtyczkę ponownie. Jeśli komentarze są widoczne, LinkedIn zmienił układ strony i ekstraktor wymaga aktualizacji.',
    ]);
  }

  const nodes = [...root.querySelectorAll(legacySelector)].filter((node) => node.getClientRects().length);
  const comments = [];
  const seen = new Set();
  for (const node of nodes) {
    const owningPost = node.closest('[data-urn^="urn:li:activity:"], [data-id^="urn:li:activity:"]');
    if (owningPost && !roots.includes(owningPost)) continue;
    const owned = (sel) => [...node.querySelectorAll(sel)].find((child) => child.closest(legacySelector) === node);
    const body = owned('.comments-comment-item__main-content, .comments-comment-entity__content, .comments-comment-item-content-body');
    if (!body) continue;
    const copy = body.cloneNode(true);
    copy.querySelectorAll(`${legacySelector}, button, [role="button"]`).forEach((child) => child.remove());
    copy.querySelectorAll('a[href]').forEach((link) => {
      const href = link.getAttribute('href');
      if (isMentionHref(href)) return;
      const url = canonicalUrl(href);
      if (url && link.textContent.trim().replace(/\/+$/, '').toLowerCase() !== url.replace(/^https?:\/\//i, '').toLowerCase()) {
        link.append(document.createTextNode(` (${url})`));
      }
    });
    copy.querySelectorAll('br').forEach((br) => br.replaceWith(document.createTextNode('\n')));
    copy.querySelectorAll('p, div').forEach((block) => block.append(document.createTextNode('\n')));
    const text = copy.textContent.replace(/ /g, ' ').replace(/\n{3,}/g, '\n\n').trim();
    if (!text) continue;
    const author = owned('.comments-post-meta__name-text, .comments-comment-meta__description-title, .comments-comment-item__author, .comments-comment-entity__author')?.textContent.trim() || 'Autor nieodczytany';
    const id = node.getAttribute('data-id') || node.getAttribute('data-urn') || `${author}\n${text}`;
    if (seen.has(id)) continue;
    seen.add(id);
    const parent = node.parentElement?.closest(legacySelector);
    const parentAuthor = parent?.querySelector('.comments-post-meta__name-text, .comments-comment-meta__description-title')?.textContent.trim();
    const isReply = Boolean(parent);
    const authorLink = owned('a[href*="/in/"], a[href*="/company/"]');
    comments.push({
      id: String(id),
      author,
      authorUrl: authorLink ? canonicalUrl(authorLink.getAttribute('href')) : '',
      text,
      timestamp: timestampIn(node),
      isReply,
      replyTo: isReply ? (parentAuthor || 'komentarz nadrzędny') : '',
    });
  }
  return summarise(comments, declaredCommentTotal(), sortLabel(), []);
}

if (typeof module !== 'undefined') module.exports = { extractLinkedInComments };
