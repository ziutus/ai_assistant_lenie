const { test } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('../../web_interface_react/node_modules/jsdom');
const { parseFacebookGroupMembers } = require('../facebook-group-members');

const GROUP = '123';
const MEMBERS_URL = `https://www.facebook.com/groups/${GROUP}/members/`;

function run(html) {
  const dom = new JSDOM(html, { url: MEMBERS_URL, runScripts: 'outside-only' });
  try {
    return parseFacebookGroupMembers(GROUP, dom.window.document);
  } finally {
    dom.window.close();
  }
}

// Facebook repeats the group-profile link for the avatar and the visible name;
// mutual-friend descriptions belong to the row but do not identify its member.
function memberRow({ id, name = 'Anna Nowak', group = GROUP, href = `/groups/${group}/user/${id}/`, description = '', aria = true }) {
  return `<div role="listitem">
    <a href="${href}" aria-label="Zdjęcie profilowe"><img alt="" src="avatar.jpg"></a>
    <div>
      <a href="${href}">${aria ? `<span aria-hidden="true">${name}</span>` : name}</a>
      <div class="description">${description}</div>
    </div>
  </div>`;
}

test('a member row supplies its numeric ID, visible name and absolute profile URL', () => {
  const result = run(memberRow({ id: '456789', name: '  Anna   Nowak  ' }));
  assert.deepEqual(result, [{
    name: 'Anna Nowak',
    fb_id: '456789',
    profile_url: 'https://www.facebook.com/groups/123/user/456789',
  }]);
});

test('avatar/name links and repeated sections collapse by ID, keeping the first name and URL', () => {
  const result = run(`<section><h2>Administratorzy</h2>
    ${memberRow({ id: '456789', name: 'Anna Nowak' })}
  </section><section><h2>Znajomi</h2>
    ${memberRow({ id: '456789', name: 'Anna Inna', href: '/groups/123/user/456789/about/?source=friends' })}
  </section>`);
  assert.deepEqual(result, [{
    name: 'Anna Nowak',
    fb_id: '456789',
    profile_url: 'https://www.facebook.com/groups/123/user/456789',
  }]);
});

test('a mutual friend mentioned in another member row is not collected as a member', () => {
  const result = run(`<section><h2>Członkowie, których coś łączy</h2>
    ${memberRow({
      id: '456789', name: 'Anna Nowak',
      description: 'Wspólny znajomy: Piotr Kowalski. <a href="/friends/998877/">Piotr Kowalski</a> zna również Annę.',
    })}
  </section>`);
  assert.equal(result.length, 1);
  assert.equal(result[0].name, 'Anna Nowak');
  assert.equal(result[0].fb_id, '456789');
  assert.ok(!result.some(member => member.name === 'Piotr Kowalski'));
});

test('member rows from a different group are excluded', () => {
  const result = run(memberRow({ id: '456789' }) + memberRow({ id: '987654', group: '999' }));
  assert.deepEqual(result.map(member => member.fb_id), ['456789']);
});

test('query strings and extra path segments never become part of the numeric ID', () => {
  for (const suffix of ['/?source=list', '/about/?source=list#details', '?source=list']) {
    const result = run(memberRow({ id: '456789', href: `/groups/123/user/456789${suffix}` }));
    assert.equal(result[0].fb_id, '456789');
    assert.ok(!/[?#]/.test(result[0].profile_url));
  }
});

test('names prefer aria-hidden text, remove trailing badges and fall back to link text', () => {
  const result = run(`<a href="/groups/123/user/111/">
    <span aria-hidden="true">Anna Nowak<span> · Administrator</span></span>
    <span class="screen-reader">Anna Nowak</span>
  </a>${memberRow({ id: '222', name: 'Jan Kowalski', aria: false })}`);
  assert.deepEqual(result.map(member => member.name), ['Anna Nowak', 'Jan Kowalski']);
});

test('non-numeric IDs and group paths embedded in an unrelated URL are excluded', () => {
  const result = run(memberRow({ id: '456abc' })
    + memberRow({ id: '456', href: '/friends/?next=/groups/123/user/456/' })
    + memberRow({ id: '789', href: 'https://example.org/groups/123/user/789/' }));
  assert.deepEqual(result, []);
});
