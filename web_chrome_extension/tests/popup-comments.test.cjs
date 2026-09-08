const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('../../web_interface_react/node_modules/jsdom');
const tick = () => new Promise(resolve => setImmediate(resolve));

async function popup({ nasAvailable = true } = {}) {
  const dom = new JSDOM(fs.readFileSync(path.join(__dirname, '../popup.html'), 'utf8'), {
    url: 'https://extension.test/', runScripts: 'outside-only',
  });
  const w = dom.window;
  const requests = [];
  const alerts = [];
  const tab = { id: 1, url: 'https://www.linkedin.com/feed/update/urn:li:activity:123/' };
  w.alert = message => alerts.push(message);
  w.console.error = () => {};
  w.chrome = {
    runtime: {},
    storage: { sync: { get: (_, cb) => cb({}), set: (_, cb) => cb?.() }, local: { get: (_, cb) => cb({}), set: () => {} } },
    tabs: { query: (_, cb) => cb ? cb([tab]) : Promise.resolve([tab]) },
    scripting: { executeScript: (options, cb) => {
      if (cb) return cb([{ result: { title: 'Post', postText: 'Original post', platform: 'linkedin', author: 'Author' } }]);
      return Promise.resolve([{ result: options.func.name === 'extractLinkedInComments'
        ? {
          comments: [
            { author: 'Reader', authorUrl: '', text: 'Useful comment', timestamp: '2d', isReply: false, replyTo: '' },
            { author: 'Second', authorUrl: '', text: 'agreed', timestamp: '1d', isReply: true, replyTo: 'Reader' },
          ],
          captured: 2, topLevel: 1, replies: 1, declaredTotal: 40, sort: 'Most relevant',
          warning: 'Wpis ma 40 komentarzy, a załadowano 1 wątków głównych. Przewiń komentarze na stronie, aby doładować więcej, i pobierz ponownie — to jest tylko fragment dyskusji.',
        }
        : { text: 'Page UI', html: '<html>Page UI</html>' } }]);
    } },
  };
  w.fetch = async (url, options) => {
    if (options.method === 'POST') {
      requests.push({ url, body: JSON.parse(options.body) });
      return { ok: true, status: 200, json: async () => ({ status: 'updated', document_id: 42 }) };
    }
    return { ok: nasAvailable, status: nasAvailable ? 200 : 503 };
  };
  w.eval(fs.readFileSync(path.join(__dirname, '../linkedin-comments.js'), 'utf8'));
  w.eval(fs.readFileSync(path.join(__dirname, '../popup.js'), 'utf8'));
  await tick();
  const el = id => w.document.getElementById(id);
  el('nasApiKey').value = 'test-nas';
  el('awsApiKey').value = 'test-aws';
  const include = async () => {
    el('includeLinkedinComments').checked = true;
    el('includeLinkedinComments').dispatchEvent(new w.Event('change'));
    await tick();
  };
  const send = async () => { el('sendButton').click(); await tick(); await tick(); };
  return { dom, el, include, send, requests, alerts, w };
}

test('opt-in preview is editable and explicit replacement sends comments to NAS', async () => {
  const p = await popup();
  try {
    assert.equal(p.el('linkedinCommentsContainer').style.display, 'block');
    await p.include();
    const preview = p.el('linkedinCommentsText').value;
    assert.match(preview, /Reader \(2d\)\nUseful comment/);
    // a reply is indented and labelled with the person it answers
    assert.match(preview, /\n {2}↳ odpowiedź do: Reader — Second \(1d\)\n {4}agreed/);
    // the partial-capture warning reaches the user
    assert.match(p.el('linkedinCommentsStatus').textContent, /tylko fragment dyskusji/);
    p.el('linkedinCommentsText').value = 'Selected comment';
    p.el('replaceSocialPost').checked = true;
    await p.send();
    assert.equal(p.requests.length, 1);
    assert.equal(p.requests[0].body.operation, 'replace_social_post');
    assert.equal(p.requests[0].body.html, '');
    assert.match(p.requests[0].body.text, /^Original post\n\n## Komentarze/);
    assert.match(p.requests[0].body.text, /Selected comment$/);
    assert.match(p.alerts[0], /zaktualizowana/);
  } finally { p.dom.window.close(); }
});

test('unchecked comments are never sent, even if preview contains text', async () => {
  const p = await popup();
  try {
    await p.include();
    p.el('includeLinkedinComments').checked = false;
    p.el('includeLinkedinComments').dispatchEvent(new p.w.Event('change'));
    await p.send();
    assert.equal(p.requests[0].body.text, 'Original post');
    assert.equal(p.requests[0].body.operation, undefined);
  } finally { p.dom.window.close(); }
});

test('replacement cannot fall back to AWS', async () => {
  const p = await popup({ nasAvailable: false });
  try {
    await p.include();
    p.el('replaceSocialPost').checked = true;
    await p.send();
    assert.equal(p.requests.length, 0);
    assert.match(p.alerts[0], /wymaga dostępnego NAS/);
  } finally { p.dom.window.close(); }
});

test('new capture with comments can fall back to AWS', async () => {
  const p = await popup({ nasAvailable: false });
  try {
    await p.include();
    await p.send();
    assert.equal(p.requests.length, 1);
    assert.match(p.requests[0].url, /amazonaws/);
    assert.match(p.requests[0].body.text, /Useful comment/);
    assert.equal(p.requests[0].body.operation, undefined);
  } finally { p.dom.window.close(); }
});

test('empty post or empty selected comments block submission', async () => {
  const p = await popup();
  try {
    await p.include();
    p.el('capturedContentText').value = '';
    await p.send();
    assert.equal(p.requests.length, 0);
    p.el('capturedContentText').value = 'Post';
    p.el('linkedinCommentsText').value = '';
    await p.send();
    assert.equal(p.requests.length, 0);
    assert.match(p.alerts[1], /Brak komentarzy/);
  } finally { p.dom.window.close(); }
});
