const { test } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('../../web_interface_react/node_modules/jsdom');
const { extractLinkedInComments } = require('../linkedin-comments');

const ACT = '7501263103955980288';
const POST_URL = `https://www.linkedin.com/feed/update/urn:li:activity:${ACT}/`;

function run(html, url = POST_URL) {
  const dom = new JSDOM(html, { url, runScripts: 'outside-only' });
  const { window } = dom;
  window.HTMLElement.prototype.getClientRects = function () {
    return this.hidden || this.closest('[hidden]') ? [] : [{}];
  };
  // jsdom has no layout: derive the avatar indent from a data-x attribute so the
  // reply/top-level split (which on the real page is only visual indentation)
  // is testable.
  window.Element.prototype.getBoundingClientRect = function () {
    const x = Number(this.getAttribute('data-x'));
    return { left: Number.isFinite(x) ? x : 0, top: 0, width: this.tagName === 'FIGURE' ? 32 : 0, height: 0 };
  };
  return JSON.parse(JSON.stringify(window.eval(`(${extractLinkedInComments.toString()})()`)));
}

// One logical comment as LinkedIn's server-driven UI renders it: a componentkey
// carrying the comment URN, an avatar <figure>, an author profile link with the
// name inside an aria-hidden span, a relative timestamp and the body in
// [data-testid="expandable-text-box"].
function sduiComment({ id, author = 'Anna Nowak', slug = 'anna-nowak', x = 640, time = '2d', body = 'Treść', moreToggle = false, activity = ACT }) {
  const key = `urn:li:comment:(urn:li:activity:${activity},${id})`;
  return `<div componentkey="replaceableComment_${key}">
    <div componentkey="CommentComponentReference_${key}">
      <a href="https://www.linkedin.com/in/${slug}/"><figure data-x="${x}"></figure></a>
      <a href="https://www.linkedin.com/in/${slug}/"><p><span aria-hidden="true">${author}<span> • 2nd</span></span></p></a>
      <div><p><span>${time}</span></p></div>
      <span data-testid="expandable-text-box">${body}${moreToggle ? '<button>… more</button>' : ''}</span>
      <button aria-label="Reply">Reply</button>
    </div>
  </div>`;
}

const commentsButton = (n) => `<button aria-label="Comment">${n}</button>`;

test('SDUI: comments are scoped to the open post by the activity id in the componentkey', () => {
  const result = run(`<div>
    ${sduiComment({ id: '1', body: 'ten wpis' })}
    ${sduiComment({ id: '2', body: 'inny wpis', activity: '999' })}
  </div>`);
  assert.equal(result.comments.length, 1);
  assert.equal(result.comments[0].text, 'ten wpis');
});

test('SDUI: the same comment rendered several times collapses to one', () => {
  const one = sduiComment({ id: '5', body: 'raz' });
  const result = run(`<div>${one}${one}${one}</div>`);
  assert.equal(result.comments.length, 1);
  assert.equal(result.captured, 1);
});

test('SDUI: body comes from expandable-text-box with UI controls stripped', () => {
  const result = run(`<div>${sduiComment({
    id: '6',
    body: 'Zdanie<br>Drugie <a href="https://przyklad.pl/tekst">źródło</a><button>Reply</button>',
  })}</div>`);
  assert.equal(result.comments[0].text, 'Zdanie\nDrugie źródło (https://przyklad.pl/tekst)');
});

test('SDUI: a member mention keeps its name but not its profile URL', () => {
  const result = run(`<div>${sduiComment({
    id: '7',
    body: '<a href="https://www.linkedin.com/in/jan-kowalski-9b8c/">Jan Kowalski</a> zgoda',
  })}</div>`);
  assert.equal(result.comments[0].text, 'Jan Kowalski zgoda');
});

test('SDUI: a link whose text already is the URL is not doubled', () => {
  const result = run(`<div>${sduiComment({
    id: '8',
    body: '<a href="https://github.com/x/y">github.com/x/y</a>',
  })}</div>`);
  assert.equal(result.comments[0].text, 'github.com/x/y');
});

test('SDUI: replies are told apart by avatar indent and carry the mentioned parent', () => {
  const result = run(`<div>
    ${sduiComment({ id: '10', x: 640, author: 'Michał Kolasa', body: 'wątek główny' })}
    ${sduiComment({ id: '11', x: 680, author: 'Katarzyna Drąg', body: '<a href="https://www.linkedin.com/in/michal-kolasa/">Michał Kolasa</a> zgadzam się' })}
  </div>${commentsButton(2)}`);
  assert.deepEqual(
    result.comments.map((c) => ({ author: c.author, isReply: c.isReply, replyTo: c.replyTo, text: c.text })),
    [
      { author: 'Michał Kolasa', isReply: false, replyTo: '', text: 'wątek główny' },
      { author: 'Katarzyna Drąg', isReply: true, replyTo: 'Michał Kolasa', text: 'zgadzam się' },
    ],
  );
});

test('SDUI: an indented reply without a leading mention falls back to the preceding top-level author', () => {
  const result = run(`<div>
    ${sduiComment({ id: '20', x: 640, author: 'Ola', body: 'pytanie' })}
    ${sduiComment({ id: '21', x: 680, author: 'Wit', body: 'odpowiedź bez oznaczenia' })}
  </div>`);
  assert.equal(result.comments[1].isReply, true);
  assert.equal(result.comments[1].replyTo, 'Ola');
});

test('SDUI: a top-level comment that opens with a mention is not misread as a reply', () => {
  const result = run(`<div>${sduiComment({
    id: '30', x: 640, author: 'Maciej',
    body: '<a href="https://www.linkedin.com/in/michal-kolasa/">Michał Kolasa</a> i od razu widać',
  })}</div>`);
  assert.equal(result.comments[0].isReply, false);
  assert.equal(result.comments[0].replyTo, '');
  assert.equal(result.comments[0].text, 'Michał Kolasa i od razu widać');
});

test('SDUI: the "…more" clamp toggle is dropped but the full body is kept', () => {
  const result = run(`<div>${sduiComment({
    id: '40', x: 640, body: 'Długa wypowiedź która na stronie jest zwinięta', moreToggle: true,
  })}</div>`);
  assert.equal(result.comments[0].text, 'Długa wypowiedź która na stronie jest zwinięta');
});

test('SDUI: a partial capture is never reported as the whole discussion', () => {
  const result = run(`<div>
    ${sduiComment({ id: '41', x: 640, body: 'jeden' })}
    ${sduiComment({ id: '42', x: 640, body: 'dwa' })}
  </div>${commentsButton(115)}`);
  assert.equal(result.declaredTotal, 115);
  assert.equal(result.topLevel, 2);
  assert.match(result.warning, /fragment dyskusji/);
  assert.match(result.warning, /115/);
});

test('SDUI: hidden comment nodes are excluded', () => {
  const result = run(`<div>
    ${sduiComment({ id: '50', body: 'widoczny' })}
    <div hidden>${sduiComment({ id: '51', body: 'ukryty' })}</div>
  </div>`);
  assert.equal(result.comments.length, 1);
  assert.equal(result.comments[0].text, 'widoczny');
});

test('SDUI: the author name loses the connection-degree suffix', () => {
  const result = run(`<div>${sduiComment({ id: '60', author: 'Marta Idczak' })}</div>`);
  assert.equal(result.comments[0].author, 'Marta Idczak');
  assert.equal(result.comments[0].authorUrl, 'https://www.linkedin.com/in/anna-nowak');
});

// ---- Legacy DOM (older LinkedIn web UI) ---------------------------------------

const legacyComment = (text, author = 'Anna', extra = '') => `<div class="comments-comment-item" ${extra}>
  <span class="comments-post-meta__name-text">${author}</span>
  <div class="comments-comment-item__main-content">${text}</div>
  <button>Like</button></div>`;

test('legacy: only the requested post contributes comments', () => {
  const result = run(`<article data-urn="urn:li:activity:999">${legacyComment('wrong')}</article>
    <article data-urn="urn:li:activity:${ACT}">${legacyComment('correct')}</article>`);
  assert.equal(result.comments.length, 1);
  assert.equal(result.comments[0].text, 'correct');
});

test('legacy: nested replies stay separate and keep the parent author', () => {
  const result = run(`<article data-urn="urn:li:activity:${ACT}"><div class="comments-comment-item">
    <span class="comments-post-meta__name-text">Parent</span>
    <div class="comments-comment-item__main-content">Original</div>
    ${legacyComment('Answer', 'Reply author')}</div></article>`);
  assert.deepEqual(
    result.comments.map((c) => ({ author: c.author, text: c.text, replyTo: c.replyTo })),
    [
      { author: 'Parent', text: 'Original', replyTo: '' },
      { author: 'Reply author', text: 'Answer', replyTo: 'Parent' },
    ],
  );
});

test('an unrecognized comment DOM fails closed with a warning', () => {
  const result = run('<main><div class="something">a comment maybe</div></main>');
  assert.equal(result.comments.length, 0);
  assert.ok(result.warning);
});

test('non-LinkedIn URLs are rejected', () => {
  assert.throws(() => run('', `https://example.org/urn:li:activity:${ACT}/`), /urn:li:activity|LinkedIn/);
});
