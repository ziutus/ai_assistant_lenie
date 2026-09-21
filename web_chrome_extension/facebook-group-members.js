// Only group-profile anchors identify members. Row descriptions can mention
// mutual friends who are not members and must never become separate entries.
function parseFacebookGroupMembers(groupId, root = document) {
  if (!/^\d+$/.test(String(groupId))) return [];
  const byId = new Map();
  const baseUrl = (root.ownerDocument || root).location?.href || root.baseURI;
  for (const link of root.querySelectorAll(`a[href*="/groups/${groupId}/user/"]`)) {
    let url;
    try {
      url = new URL(link.getAttribute('href'), baseUrl);
    } catch (_) {
      continue;
    }
    const match = url.pathname.match(/^\/groups\/(\d+)\/user\/(\d+)(?:\/|$)/);
    if (!/^https?:$/.test(url.protocol) || !/(^|\.)facebook\.com$/.test(url.hostname)
      || !match || match[1] !== String(groupId) || byId.has(match[2])) continue;
    const holder = link.querySelector('span[aria-hidden="true"]') || link;
    const name = (holder.textContent || '').replace(/\s+/g, ' ').trim()
      .replace(/\s*[•·|]\s*(?:Administrator(?:ka)?|Admin|Moderator(?:ka)?|Autor|Author|Obserwuj|Follow)\b.*$/i, '').trim();
    // Avatar links are often empty; let the following name link supply the row.
    if (!name) continue;
    byId.set(match[2], {
      name,
      fb_id: match[2],
      profile_url: `${url.origin}${url.pathname}`.replace(/\/$/, ''),
    });
  }
  return [...byId.values()];
}

// popup.js first injects this file into Chrome's isolated world, so the sibling
// parser is available when Chrome serializes and invokes this driver via func.
async function collectFacebookGroupMembers() {
  const groupId = location.pathname.match(/^\/groups\/(\d+)\/members\/?/)?.[1];
  if (!/(^|\.)facebook\.com$/.test(location.hostname) || !groupId) {
    throw new Error('Otwórz stronę członków grupy na Facebooku (adres facebook.com/groups/<id>/members/).');
  }

  const byId = new Map();
  function collectVisible() {
    for (const member of parseFacebookGroupMembers(groupId)) {
      if (!byId.has(member.fb_id)) byId.set(member.fb_id, member);
    }
  }
  async function reportProgress() {
    try {
      await chrome.runtime.sendMessage({ type: 'fb_group_members_progress', count: byId.size });
    } catch (_) {
      // The popup may have closed, or runtime messaging may be unavailable.
    }
  }
  const scrollHeight = () => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  collectVisible();
  await reportProgress();
  let previousHeight = scrollHeight();
  let previousCount = byId.size;
  let noGrowthSteps = 0;
  let bottomSteps = 0;
  let stoppedReason;
  while (!stoppedReason) {
    // Small in-page steps mimic real scrolling and give Facebook's lazy loader
    // time to fire; a single scrollTo jump can miss its virtualized list updates.
    window.scrollBy(0, window.innerHeight);
    await new Promise(resolve => setTimeout(resolve, 750));
    collectVisible();
    await reportProgress();
    const height = scrollHeight();
    const noGrowth = height <= previousHeight && byId.size === previousCount;
    noGrowthSteps = noGrowth ? noGrowthSteps + 1 : 0;
    const atBottom = window.scrollY + window.innerHeight >= height;
    bottomSteps = atBottom && noGrowth ? bottomSteps + 1 : 0;
    if (bottomSteps >= 2) stoppedReason = 'bottom-reached';
    else if (noGrowthSteps >= 5) stoppedReason = 'no-growth';
    previousHeight = height;
    previousCount = byId.size;
  }
  return { members: [...byId.values()], count: byId.size, stoppedReason };
}

if (typeof module !== 'undefined') module.exports = { parseFacebookGroupMembers, collectFacebookGroupMembers };
