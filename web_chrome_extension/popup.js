document.addEventListener('DOMContentLoaded', function () {
  // Tabs setup
  const tabLinks = document.querySelectorAll('.nav-link[data-tab]');
  const tabPanes = {
    add: document.getElementById('tab-add'),
    settings: document.getElementById('tab-settings'),
    debug: document.getElementById('tab-debug')
  };
  tabLinks.forEach(link => {
    link.addEventListener('click', () => {
      tabLinks.forEach(l => l.classList.remove('active'));
      link.classList.add('active');
      const target = link.getAttribute('data-tab');
      Object.keys(tabPanes).forEach(key => {
        tabPanes[key].classList.toggle('active', key === target);
      });
    });
  });

  // Elements
  const nasApiKeyInput = document.getElementById('nasApiKey');
  const awsApiKeyInput = document.getElementById('awsApiKey');
  const localServerUrlInput = document.getElementById('localServerUrl');
  const serverUrlInput = document.getElementById('serverUrl');
  const noteInput = document.getElementById('note');
  const sendButton = document.getElementById('sendButton');
  const paywallInputs = document.getElementsByName('paywall');
  const requiresLoginInput = document.getElementById('requiresLogin');
  const typeSelect = document.getElementById('type');
  const sourceSelect = document.getElementById('source');
  const chapter_list = document.getElementById('chapter_list');
  const chapterListContainer = document.getElementById('chapterListContainer');
  const pageLanguageSelect = document.getElementById('pageLanguageSelect');
  const pageLanguageOther = document.getElementById('pageLanguageOther');
  const pageDescriptionInput = document.getElementById('pageDescription');
  const pageTitleInput = document.getElementById('pageTitle');
  const facebookPostContainer = document.getElementById('facebookPostContainer');
  const facebookPostTextInput = document.getElementById('facebookPostText');
  const toggleNasApiKeyVisibilityBtn = document.getElementById('toggleNasApiKeyVisibility');
  const toggleAwsApiKeyVisibilityBtn = document.getElementById('toggleAwsApiKeyVisibility');
  const nasApiKeyEye = document.getElementById('nasApiKeyEye');
  const awsApiKeyEye = document.getElementById('awsApiKeyEye');
  const newSourceContainer = document.getElementById('newSourceContainer');
  const newSourceNameInput = document.getElementById('newSourceName');
  const addSourceButton = document.getElementById('addSourceButton');
  const refreshExisting = document.getElementById('refreshExisting');
  const debugContainer = document.getElementById('debugContainer');
  const debugOutput = document.getElementById('debugOutput');
  const copyDebugButton = document.getElementById('copyDebugButton');

  const ADD_NEW_SOURCE = '__add_new__';
  let previousSourceValue = sourceSelect.value;
  let detectedSocialAuthor = '';
  let detectedSocialPlatform = '';
  const debugState = { version: '1.0.43' };

  const DEFAULT_LOCAL_SERVER_URL = 'http://192.168.200.7:5055/url_add';
  const DEFAULT_AWS_SERVER_URL = 'https://1bkc3kz7c9.execute-api.us-east-1.amazonaws.com/v1/url_add';
  const PROBE_TIMEOUT_MS = 1500;
  const REQUEST_TIMEOUT_MS = 30000;

  function setLanguageValue(value) {
    const normalized = (value || '').trim().toLowerCase();
    if (normalized === 'pl' || normalized.startsWith('pl-')) {
      pageLanguageSelect.value = 'pl';
      pageLanguageOther.value = '';
    } else if (normalized === 'en' || normalized.startsWith('en-')) {
      pageLanguageSelect.value = 'en';
      pageLanguageOther.value = '';
    } else {
      pageLanguageSelect.value = 'other';
      pageLanguageOther.value = normalized;
    }
    pageLanguageOther.style.display = pageLanguageSelect.value === 'other' ? 'block' : 'none';
  }

  function getLanguageValue() {
    return pageLanguageSelect.value === 'other'
      ? pageLanguageOther.value.trim()
      : pageLanguageSelect.value;
  }

  pageLanguageSelect.addEventListener('change', () => {
    pageLanguageOther.style.display = pageLanguageSelect.value === 'other' ? 'block' : 'none';
    if (pageLanguageSelect.value !== 'other') pageLanguageOther.value = '';
  });

  function updateDebug(patch) {
    Object.assign(debugState, patch);
    if (debugOutput) debugOutput.value = JSON.stringify(debugState, null, 2);
  }

  copyDebugButton?.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(debugOutput.value);
      copyDebugButton.textContent = 'Skopiowano';
      setTimeout(() => { copyDebugButton.textContent = 'Kopiuj diagnostykę'; }, 1500);
    } catch (error) {
      debugOutput.select();
      document.execCommand('copy');
      updateDebug({ copy_error: String(error) });
    }
  });

  // serverUrl stores the FULL /url_add endpoint URL (backward compatible with
  // existing installs) — derive the API base for the /sources endpoints.
  function apiBaseFrom(serverUrl) {
    return serverUrl.trim().replace(/\/url_add\/?$/, '');
  }

  function endpointConfigs() {
    return [
      { url: localServerUrlInput.value.trim(), apiKey: nasApiKeyInput.value.trim(), role: 'nas' },
      { url: serverUrlInput.value.trim(), apiKey: awsApiKeyInput.value.trim(), role: 'aws' }
    ].filter((config, index, all) => config.url && config.apiKey
      && all.findIndex(item => item.url === config.url) === index);
  }

  async function fetchWithTimeout(url, options, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, { ...options, signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  }

  function createExternalUuid() {
    if (crypto.randomUUID) return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map(byte => byte.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  async function probeEndpoint(endpoint, apiKey) {
    try {
      const response = await fetchWithTimeout(endpoint, {
        method: 'OPTIONS',
        headers: { 'x-api-key': apiKey }
      }, PROBE_TIMEOUT_MS);
      return { ok: response.ok, status: response.status };
    } catch (_) {
      return { ok: false, status: 0 };
    }
  }

  async function preferredEndpoint() {
    for (const config of endpointConfigs()) {
      if ((await probeEndpoint(config.url, config.apiKey)).ok) return config;
    }
    return null;
  }

  function rebuildSourceOptions(names, selected) {
    sourceSelect.innerHTML = '';
    names.forEach(name => {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      sourceSelect.appendChild(option);
    });
    const addNew = document.createElement('option');
    addNew.value = ADD_NEW_SOURCE;
    addNew.textContent = '+ Dodaj nowe źródło…';
    sourceSelect.appendChild(addNew);
    if (selected && names.includes(selected)) {
      sourceSelect.value = selected;
    } else if (names.includes('own')) {
      sourceSelect.value = 'own';
    }
    previousSourceValue = sourceSelect.value;
  }

  // Rebuild the source dropdown from the backend (active sources only).
  // Offline / AWS Gateway URL (no /sources route) → cached list from
  // chrome.storage.local; without a cache the hardcoded HTML options stay.
  // Never blocks the popup.
  function loadSources() {
    chrome.storage.sync.get(['lastSource'], (sync) => {
      const lastSource = sync.lastSource;
      preferredEndpoint().then(config => {
        if (!config) throw new Error('Brak dostępnego endpointu');
        return fetchWithTimeout(apiBaseFrom(config.url) + '/sources?active=1', {
          headers: { 'x-api-key': config.apiKey }
        }, PROBE_TIMEOUT_MS);
      })
        .then(response => {
          if (!response.ok) throw new Error(`${response.status}`);
          return response.json();
        })
        .then(data => {
          const names = (data.sources || []).map(s => s.name || s.source).filter(Boolean);
          if (!names.length) return;
          chrome.storage.local.set({ sourcesCache: names });
          rebuildSourceOptions(names, lastSource);
        })
        .catch(() => {
          chrome.storage.local.get(['sourcesCache'], (local) => {
            if (local.sourcesCache && local.sourcesCache.length) {
              rebuildSourceOptions(local.sourcesCache, lastSource);
            } else if (lastSource && [...sourceSelect.options].some(o => o.value === lastSource)) {
              sourceSelect.value = lastSource;
              previousSourceValue = lastSource;
            }
          });
        });
    });
  }

  sourceSelect.addEventListener('change', function () {
    if (sourceSelect.value === ADD_NEW_SOURCE) {
      newSourceContainer.style.display = 'block';
      newSourceNameInput.focus();
      return;
    }
    newSourceContainer.style.display = 'none';
    previousSourceValue = sourceSelect.value;
    chrome.storage.sync.set({ lastSource: sourceSelect.value });
  });

  addSourceButton.addEventListener('click', function () {
    const name = newSourceNameInput.value.trim();
    const endpoints = endpointConfigs();
    if (!name) {
      alert('Podaj nazwę nowego źródła');
      return;
    }
    if (!endpoints.length) {
      alert('Uzupełnij co najmniej jeden adres serwera i odpowiadający mu klucz API');
      return;
    }
    addSourceButton.disabled = true;
    preferredEndpoint().then(config => {
      if (!config) throw new Error('NAS i AWS są niedostępne');
      return fetchWithTimeout(apiBaseFrom(config.url) + '/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': config.apiKey },
      body: JSON.stringify({ name: name })
      }, REQUEST_TIMEOUT_MS);
    })
      .then(response => {
        // 409 = source already exists — just select it.
        if (!response.ok && response.status !== 409) {
          throw new Error(`${response.status} - ${response.statusText}`);
        }
      })
      .then(() => {
        if (![...sourceSelect.options].some(o => o.value === name)) {
          const option = document.createElement('option');
          option.value = name;
          option.textContent = name;
          const addNewOption = [...sourceSelect.options].find(o => o.value === ADD_NEW_SOURCE);
          sourceSelect.insertBefore(option, addNewOption || null);
        }
        sourceSelect.value = name;
        previousSourceValue = name;
        chrome.storage.sync.set({ lastSource: name });
        chrome.storage.local.get(['sourcesCache'], (local) => {
          const cache = local.sourcesCache || [];
          if (!cache.includes(name)) {
            chrome.storage.local.set({ sourcesCache: cache.concat([name]) });
          }
        });
        newSourceContainer.style.display = 'none';
        newSourceNameInput.value = '';
      })
      .catch(error => {
        alert(`Nie udało się dodać źródła: ${error.message}`);
        sourceSelect.value = previousSourceValue;
        newSourceContainer.style.display = 'none';
      })
      .finally(() => {
        addSourceButton.disabled = false;
      });
  });

  function toggleChapterListVisibility() {
    chapterListContainer.style.display = (typeSelect.value === 'youtube') ? 'block' : 'none';
  }

  function toggleFacebookPostVisibility() {
    const isFacebookPost = typeSelect.value === 'social_media_post';
    facebookPostContainer.style.display = isFacebookPost ? 'block' : 'none';
    refreshExisting.disabled = isFacebookPost;
    if (isFacebookPost) refreshExisting.checked = false;
    requiresLoginInput.checked = isFacebookPost;
  }

  toggleChapterListVisibility();
  toggleFacebookPostVisibility();
  typeSelect.addEventListener('change', () => {
    toggleChapterListVisibility();
    toggleFacebookPostVisibility();
  });

  // Load settings
  chrome.storage.sync.get(['apiKey', 'nasApiKey', 'awsApiKey', 'serverUrl', 'localServerUrl'], function (data) {
    const legacyApiKey = data.apiKey || '';
    if (data.nasApiKey || legacyApiKey) nasApiKeyInput.value = data.nasApiKey || legacyApiKey;
    if (data.awsApiKey || legacyApiKey) awsApiKeyInput.value = data.awsApiKey || legacyApiKey;
    if (data.localServerUrl) localServerUrlInput.value = data.localServerUrl;
    if (data.serverUrl) serverUrlInput.value = data.serverUrl;
    if (data.nasApiKey || data.awsApiKey || legacyApiKey) loadSources();
  });

  // Toggle API key visibility
  function bindVisibilityToggle(button, input, eye) {
    button?.addEventListener('click', function () {
      if (!input) return;
      const isPassword = input.type === 'password';
      input.type = isPassword ? 'text' : 'password';
      if (eye) eye.textContent = isPassword ? '🙈' : '👁️';
    });
  }
  bindVisibilityToggle(toggleNasApiKeyVisibilityBtn, nasApiKeyInput, nasApiKeyEye);
  bindVisibilityToggle(toggleAwsApiKeyVisibilityBtn, awsApiKeyInput, awsApiKeyEye);

  // Persist settings
  nasApiKeyInput?.addEventListener('change', function () {
    chrome.storage.sync.set({ nasApiKey: nasApiKeyInput.value });
  });
  awsApiKeyInput?.addEventListener('change', function () {
    chrome.storage.sync.set({ awsApiKey: awsApiKeyInput.value });
  });
  serverUrlInput?.addEventListener('change', function () {
    chrome.storage.sync.set({ serverUrl: serverUrlInput.value });
  });
  localServerUrlInput?.addEventListener('change', function () {
    chrome.storage.sync.set({ localServerUrl: localServerUrlInput.value });
  });

  function socialPlatformForUrl(url) {
    try {
      const hostname = new URL(url).hostname.toLowerCase();
      if (hostname === 'facebook.com' || hostname.endsWith('.facebook.com')) return 'facebook';
      if (hostname === 'linkedin.com' || hostname.endsWith('.linkedin.com')) return 'linkedin';
    } catch (_) {}
    return '';
  }

  function isSocialPostUrl(url) {
    const platform = socialPlatformForUrl(url);
    if (platform === 'facebook') {
      return /\/(posts|pfbid)/i.test(url) || /\/permalink\.php\?.*story_fbid=pfbid/i.test(url);
    }
    if (platform === 'linkedin') {
      return /\/posts\//i.test(url)
        || /\/feed\/update\/urn(?:%3A|:)li(?:%3A|:)(?:activity|share)(?:%3A|:)/i.test(url);
    }
    return false;
  }

  // Auto set type for YouTube/social posts and fetch metadata.
  chrome.tabs.query({ currentWindow: true, active: true }, function (tabs) {
    const pageUrl = tabs[0]?.url || '';
    if (pageUrl.startsWith('https://www.youtube.com/watch') || pageUrl.startsWith('http://www.youtube.com/watch')) {
      typeSelect.value = 'youtube';
      chapterListContainer.style.display = 'block';
    }
    const isSocialPost = isSocialPostUrl(pageUrl);
    updateDebug({
      page_url: pageUrl,
      page_hostname: (() => { try { return new URL(pageUrl).hostname; } catch (_) { return ''; } })(),
      detected_platform_from_url: socialPlatformForUrl(pageUrl),
      is_social_post_url: isSocialPost,
      type_before_detection: typeSelect.value
    });
    if (isSocialPost) {
      typeSelect.value = 'social_media_post';
      toggleFacebookPostVisibility();
    }

    chrome.scripting.executeScript(
      {
        target: { tabId: tabs[0].id },
        func: async () => {
          const clean = value => (value || '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
          // Facebook/LinkedIn render the post body and the reaction bar +
          // comment thread inside the same container the extraction selectors
          // grab (class names for the "noise" parts drift often enough that
          // removing them by selector -- see the copy.querySelectorAll(...).remove()
          // fallbacks below -- regularly misses). Cutting the extracted text at
          // the first clear "post ends, engagement UI begins" line is more
          // robust than chasing selector renames, and is applied to every
          // extraction path (not just the body-text fallback) as a final pass.
          const ENGAGEMENT_STOP_LINES = new Set([
            'Like', 'Comment', 'Repost', 'Send', 'Show more', 'See translation', 'Translate',
            'Most relevant', 'All comments', 'Top comments', 'Follow', 'Connect',
            'Lubi\u0119 to!', 'Lubi\u0119 to', 'Skomentuj', 'Komentarz', 'Udost\u0119pnij', 'Wy\u015blij',
            'Najtrafniejsze', 'Wszystkie komentarze', 'Zobacz t\u0142umaczenie', 'Przet\u0142umacz', 'Obserwuj'
          ]);
          const ENGAGEMENT_COUNT_RE = /^\d+\s+(?:reactions?|comments?|reposts?|shares?|repost(?:y|\u00f3w)?|komentarz(?:e|y)?|reakcj[ei]|udost\u0119pnie(?:\u0144|nia)?)$/i;
          const trimAtEngagementBoundary = value => {
            const lines = (value || '').split(/\r?\n/);
            let stopIndex = -1;
            let numericRun = 0;
            let numericRunStart = -1;
            for (let i = 0; i < lines.length; i++) {
              const line = lines[i].trim();
              if (!line) continue;
              if (/^(?:\u2026|\.\.\.)\s*more$/i.test(line) || ENGAGEMENT_STOP_LINES.has(line) || ENGAGEMENT_COUNT_RE.test(line)) {
                stopIndex = i;
                break;
              }
              // LinkedIn/Facebook often render the reaction/comment/share
              // counters as bare numbers with no label once the post is
              // scraped as plain innerText -- two in a row is not something
              // real post prose produces.
              if (/^\d{1,4}$/.test(line)) {
                if (numericRun === 0) numericRunStart = i;
                numericRun++;
                if (numericRun >= 2) {
                  stopIndex = numericRunStart;
                  break;
                }
              } else {
                numericRun = 0;
              }
            }
            return (stopIndex >= 0 ? lines.slice(0, stopIndex) : lines).join('\n').trim();
          };
          const hostname = location.hostname.toLowerCase();
          const isFacebook = hostname === 'facebook.com' || hostname.endsWith('.facebook.com');
          const isLinkedIn = hostname === 'linkedin.com' || hostname.endsWith('.linkedin.com');
          const isVisible = element => {
            if (!element) return false;
            const style = getComputedStyle(element);
            return style.display !== 'none' && style.visibility !== 'hidden' && element.innerText?.trim();
          };
          let postText = '';
          let author = '';
          let platform = '';
          let pageDebug = {};
          let fallbackExtraction = '';
          if (isFacebook) {
            platform = 'facebook';
            // Facebook often hydrates the post after the popup opens. Give
            // the page a short moment before inspecting its DOM.
            await new Promise(resolve => setTimeout(resolve, 1200));
            const postLink = [...document.querySelectorAll('a[href]')].find(a => {
              const href = a.getAttribute('href') || '';
              return /\/(posts|pfbid)/i.test(href) || /\/permalink\.php\?.*story_fbid=pfbid/i.test(href);
            });
            // Never fall back to the first feed article: it may be a
            // different post and would silently import the wrong content.
            const root = postLink?.closest('[role="article"], article');
            const message = root?.querySelector('[data-ad-preview="message"], [data-ad-comet-preview="message"]')
              || [...document.querySelectorAll('[data-ad-preview="message"], [data-ad-comet-preview="message"]')]
                .filter(isVisible)
                .sort((left, right) => (right.innerText?.length || 0) - (left.innerText?.length || 0))[0];
            if (message) {
              postText = clean(message.innerText);
            } else if (root) {
              const copy = root.cloneNode(true);
              copy.querySelectorAll('[role="article"] [role="article"], [role="button"], [aria-label*="comment" i], [aria-label*="komentarz" i]').forEach(el => el.remove());
              postText = clean(copy.innerText);
            }
            const authorLink = root?.querySelector('h2 a, h3 a, strong a');
            author = clean(authorLink?.innerText || '');
          } else if (isLinkedIn) {
            platform = 'linkedin';
            await new Promise(resolve => setTimeout(resolve, 1000));
            const rootSelectors = [
              '[data-urn^="urn:li:activity"]', '[data-urn^="urn:li:share"]',
              '[data-id^="urn:li:activity"]', '[data-id^="urn:li:share"]',
              '.feed-shared-update-v2', '.occludable-update',
              '.feed-shared-update-v2__content', 'article'
            ];
            const messageSelectors = [
              '.feed-shared-update-v2__description', '.update-components-text',
              '.feed-shared-text', '.feed-shared-inline-show-more-text',
              '.feed-shared-update-v2__commentary',
              '[data-test-id="main-feed-activity-card__commentary"]',
              '[data-testid="main-feed-activity-card__commentary"]',
              '[dir="ltr"]'
            ];
            const root = rootSelectors.map(selector => document.querySelector(selector)).find(Boolean);
            const messageCandidates = root
              ? messageSelectors.flatMap(selector => [...root.querySelectorAll(selector)]).filter(isVisible)
              : [];
            const message = messageCandidates.sort((left, right) => (right.innerText?.length || 0) - (left.innerText?.length || 0))[0];
            if (message) {
              postText = clean(message.innerText);
            } else if (root) {
              const copy = root.cloneNode(true);
              copy.querySelectorAll('.social-details-social-activity, .comments-comments-list, .feed-shared-social-action-bar, [aria-label*="comment" i], [aria-label*="komentarz" i], button, [role="button"]').forEach(el => el.remove());
              postText = clean(copy.innerText);
            }
            const authorNode = root?.querySelector('.update-components-actor__name, .feed-shared-actor__name, .update-components-actor__title, a[href*="/in/"] span[aria-hidden="true"], a[href*="/company/"] span[aria-hidden="true"]');
            author = clean(authorNode?.innerText || '');
            if (!postText) {
              postText = clean(document.querySelector('meta[property="og:description"]')?.content || document.querySelector('meta[name="description"]')?.content || '');
            }
            if (!postText) {
              // LinkedIn sometimes renders a post as plain body text without
              // the usual feed container classes (notably on /feed/update/).
              const lines = (document.body?.innerText || '').split(/\r?\n/).map(line => line.trim());
              const feedIndex = lines.findIndex(line => /^Feed post$/i.test(line));
              const engagementIndex = feedIndex >= 0
                ? lines.findIndex((line, index) => index > feedIndex && /^(?:Follow|Connect)$/i.test(line))
                : -1;
              const actionLines = new Set(['Like', 'Comment', 'Repost', 'Send', 'Show more', 'See translation', 'Translate']);
              if (engagementIndex >= 0) {
                const authorLine = lines.slice(feedIndex + 1, engagementIndex).find(Boolean);
                const contentLines = [];
                for (const line of lines.slice(engagementIndex + 1)) {
                  if (/^(?:…|\.\.\.)\s*more$/i.test(line)
                    || actionLines.has(line)
                    || /^\d+\s+reactions?$/i.test(line)) break;
                  if (line) contentLines.push(line);
                }
                postText = clean(contentLines.join('\n'));
                author = author || clean(authorLine || '');
                fallbackExtraction = 'body_text_feed_post_engagement';
              }
            }
            pageDebug = {
              body_text_length: (document.body?.innerText || '').length,
              body_text_preview: (document.body?.innerText || '').slice(0, 1000),
              root_selector_matches: Object.fromEntries(rootSelectors.map(selector => [selector, document.querySelectorAll(selector).length])),
              message_selector_matches: Object.fromEntries(messageSelectors.map(selector => [selector, root ? root.querySelectorAll(selector).length : 0])),
              root_found: Boolean(root),
              visible_message_candidates: messageCandidates.length,
              meta_description: document.querySelector('meta[name="description"]')?.content || '',
              meta_og_description: document.querySelector('meta[property="og:description"]')?.content || '',
              fallback_extraction: fallbackExtraction
            };
          }
          if (isFacebook || isLinkedIn) {
            postText = trimAtEngagementBoundary(postText);
          }
          return {
            title: document.title,
            description: document.querySelector('meta[name="description"]')?.content || '',
            language: document.documentElement.lang || navigator.language,
            postText,
            author,
            platform,
            pageDebug
          };
        }
      },
        (results) => {
        if (!results || !results[0] || chrome.runtime.lastError) {
          console.error('Error in executeScript:', chrome.runtime.lastError);
          updateDebug({
            execute_script_error: chrome.runtime.lastError?.message || 'empty result',
            result_present: Boolean(results && results[0])
          });
          pageTitleInput.value = 'Nie udało się pobrać tytułu';
          setLanguageValue('');
        } else {
          updateDebug({
            page_title: results[0].result.title || '',
            detected_platform_from_page: results[0].result.platform || '',
            detected_author: results[0].result.author || '',
            extracted_text_length: (results[0].result.postText || '').length,
            extracted_text_preview: (results[0].result.postText || '').slice(0, 500)
            ,page_dom_debug: results[0].result.pageDebug || {}
          });
          pageTitleInput.value = results[0].result.title || '';
          // For social posts, the page language is often the LinkedIn/Facebook
          // UI language rather than the language of the post itself. Keep the
          // user's selected value instead of copying document.documentElement.lang.
          if (typeSelect.value !== 'social_media_post') {
            setLanguageValue(results[0].result.language || '');
          }
          pageDescriptionInput.value = results[0].result.description || '';
          if (typeSelect.value === 'social_media_post') {
            facebookPostTextInput.value = results[0].result.postText || '';
            detectedSocialAuthor = results[0].result.author || '';
            detectedSocialPlatform = results[0].result.platform || '';
            if (results[0].result.author) {
              pageDescriptionInput.value = `Autor: ${results[0].result.author}`;
            }
          }
        }
      }
    );
  });

  // Send
  sendButton.addEventListener('click', function () {
    const endpoints = endpointConfigs();
    const note = noteInput.value;
    const type = typeSelect.value;
    const title = pageTitleInput.value;
    const language = getLanguageValue();

    if (!endpoints.length) {
      alert('Podaj adres i klucz API NAS albo AWS');
      return;
    }
    if (!endpoints.length) {
      alert('Podaj adres NAS albo AWS');
      return;
    }
    if (pageLanguageSelect.value === 'other' && !language) {
      alert('Podaj język albo wybierz pl/en');
      pageLanguageOther.focus();
      return;
    }
    if (sourceSelect.value === '__add_new__') {
      alert('Dokończ dodawanie nowego źródła albo wybierz istniejące');
      return;
    }

    let paywall = false;
    for (const input of paywallInputs) {
      if (input.checked) {
        paywall = input.value === 'true';
        break;
      }
    }

    sendButton.style.backgroundColor = 'gray';
    sendButton.disabled = true;
    sendButton.textContent = 'Wysyłam...';

    chrome.tabs.query({ currentWindow: true, active: true }, function (tabs) {
      const pageUrl = tabs[0]?.url || '';
      chrome.scripting.executeScript({
        target: { tabId: tabs[0].id },
        func: () => ({
          text: document.documentElement.innerText,
          html: document.documentElement.outerHTML,
        })
      })
        .then(result => {
          const { text, html } = result[0].result;
          const isSocialPost = type === 'social_media_post';
          const data = {
            note: note,
            url: pageUrl,
            type: type,
            text: isSocialPost ? facebookPostTextInput.value.trim() : text,
            html: isSocialPost ? '' : html,
            title: title,
            language: language,
            paywall: paywall,
            requires_login: requiresLoginInput.checked,
            social_platform: isSocialPost ? detectedSocialPlatform || socialPlatformForUrl(pageUrl) : '',
            source: sourceSelect.value,
            chapter_list: chapter_list.value,
            byline: isSocialPost ? detectedSocialAuthor : ''
          };
          data.external_uuid = createExternalUuid();
          updateDebug({
            send_attempt: true,
            payload_type: data.type,
            payload_social_platform: data.social_platform,
            payload_text_length: data.text.length,
            payload_requires_login: data.requires_login
          });
          if (isSocialPost && !data.text) {
            throw new Error('Nie znaleziono treści posta. Wklej ją do pola Treść posta.');
          }
          if (refreshExisting.checked) {
            data.operation = 'fill_missing_html';
          }

          return (async () => {
            const configs = endpointConfigs();
            const localConfig = configs.find(config => config.role === 'nas');
            const awsConfig = configs.find(config => config.role === 'aws');
            const localProbe = localConfig ? await probeEndpoint(localConfig.url, localConfig.apiKey) : null;
            if (localProbe && [401, 403].includes(localProbe.status)) {
              updateDebug({ selected_endpoint: localConfig.url, endpoint_role: 'nas', auth_probe_status: localProbe.status });
              throw new Error(`NAS odrzucił autoryzację (HTTP ${localProbe.status}). Sprawdź Klucz API NAS.`);
            }
            const localAvailable = Boolean(localProbe?.ok);
            const config = localAvailable ? localConfig : awsConfig;
            if (!config) throw new Error('NAS i AWS są niedostępne');
            updateDebug({
              selected_endpoint: config.url,
              endpoint_role: config.role,
              fallback_reason: localAvailable ? '' : 'nas_unavailable_before_post'
            });
            // Do not retry an uncertain POST against the other backend: NAS
            // and AWS have separate databases, so that could create two docs.
            return fetchWithTimeout(config.url, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                    'x-api-key': config.apiKey
              },
              body: JSON.stringify(data)
            }, REQUEST_TIMEOUT_MS);
          })();
        })
        .then(async response => {
          const result = await response.json().catch(() => ({}));
          if (response.status === 409 && result.status === 'already_exists') {
            const suffix = result.missing_raw_html
              ? ' Brakuje mu surowego HTML — możesz użyć opcji jego uzupełnienia.'
              : '';
            throw new Error(`Dokument jest już w bazie (ID: ${result.document_id}).${suffix}`);
          }
          if (!response.ok) {
            const serverLabel = debugState.endpoint_role === 'nas' ? 'NAS' : 'AWS';
            if ([401, 403].includes(response.status)) {
              throw new Error(`${serverLabel} odrzucił autoryzację (HTTP ${response.status}). Sprawdź Klucz API ${serverLabel}.`);
            }
            throw new Error(`${serverLabel}: ${result.message || `serwer zwrócił błąd: ${response.status} - ${response.statusText}`}`);
          }
          return result;
        })
        .then(result => {
          alert(result.status === 'queued' ? 'Zgłoszenie zostało przekazane do importu.' : 'Strona została dodana pomyślnie!');
          noteInput.value = '';
          setTimeout(() => window.close(), 500);
        })
        .catch(error => {
          updateDebug({ send_error: error.message });
          alert(`Błąd podczas wysyłania strony: ${error.message}`);
          console.error('Error:', error);
        })
        .finally(() => {
          sendButton.style.backgroundColor = '';
          sendButton.disabled = false;
          sendButton.textContent = 'Wyślij';
        });
    });
  });
});
