document.addEventListener('DOMContentLoaded', function () {
  // Tabs setup
  const tabLinks = document.querySelectorAll('.nav-link[data-tab]');
  const tabPanes = {
    add: document.getElementById('tab-add'),
    settings: document.getElementById('tab-settings')
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
  const apiKeyInput = document.getElementById('apiKey');
  const serverUrlInput = document.getElementById('serverUrl');
  const noteInput = document.getElementById('note');
  const sendButton = document.getElementById('sendButton');
  const paywallInputs = document.getElementsByName('paywall');
  const typeSelect = document.getElementById('type');
  const sourceSelect = document.getElementById('source');
  const chapter_list = document.getElementById('chapter_list');
  const chapterListContainer = document.getElementById('chapterListContainer');
  const pageLanguageInput = document.getElementById('pageLanguage');
  const pageDescriptionInput = document.getElementById('pageDescription');
  const pageTitleInput = document.getElementById('pageTitle');
  const toggleApiKeyVisibilityBtn = document.getElementById('toggleApiKeyVisibility');
  const apiKeyEye = document.getElementById('apiKeyEye');
  const newSourceContainer = document.getElementById('newSourceContainer');
  const newSourceNameInput = document.getElementById('newSourceName');
  const addSourceButton = document.getElementById('addSourceButton');
  const refreshExisting = document.getElementById('refreshExisting');

  const ADD_NEW_SOURCE = '__add_new__';
  let previousSourceValue = sourceSelect.value;

  // serverUrl stores the FULL /url_add endpoint URL (backward compatible with
  // existing installs) — derive the API base for the /sources endpoints.
  function apiBaseFrom(serverUrl) {
    return serverUrl.trim().replace(/\/url_add\/?$/, '');
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
  function loadSources(apiKey, serverUrl) {
    chrome.storage.sync.get(['lastSource'], (sync) => {
      const lastSource = sync.lastSource;
      fetch(apiBaseFrom(serverUrl) + '/sources?active=1', { headers: { 'x-api-key': apiKey } })
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
    const apiKey = apiKeyInput.value.trim();
    const serverUrl = serverUrlInput.value.trim();
    if (!name) {
      alert('Podaj nazwę nowego źródła');
      return;
    }
    if (!apiKey || !serverUrl) {
      alert('Uzupełnij ustawienia (klucz API i adres serwera)');
      return;
    }
    addSourceButton.disabled = true;
    fetch(apiBaseFrom(serverUrl) + '/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey },
      body: JSON.stringify({ name: name })
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

  toggleChapterListVisibility();
  typeSelect.addEventListener('change', toggleChapterListVisibility);

  // Load settings
  chrome.storage.sync.get(['apiKey', 'serverUrl'], function (data) {
    if (data.apiKey) apiKeyInput.value = data.apiKey;
    if (data.serverUrl) serverUrlInput.value = data.serverUrl;
    if (data.apiKey && data.serverUrl) {
      loadSources(data.apiKey, data.serverUrl);
    }
  });

  // Toggle API key visibility
  toggleApiKeyVisibilityBtn?.addEventListener('click', function () {
    if (!apiKeyInput) return;
    const isPassword = apiKeyInput.type === 'password';
    apiKeyInput.type = isPassword ? 'text' : 'password';
    // Optional: change icon/text
    if (apiKeyEye) {
      apiKeyEye.textContent = isPassword ? '🙈' : '👁️';
    }
  });

  // Persist settings
  apiKeyInput?.addEventListener('change', function () {
    chrome.storage.sync.set({ apiKey: apiKeyInput.value });
  });
  serverUrlInput?.addEventListener('change', function () {
    chrome.storage.sync.set({ serverUrl: serverUrlInput.value });
  });

  // Auto set type for YouTube and fetch metadata
  chrome.tabs.query({ currentWindow: true, active: true }, function (tabs) {
    const pageUrl = tabs[0]?.url || '';
    if (pageUrl.startsWith('https://www.youtube.com/watch') || pageUrl.startsWith('http://www.youtube.com/watch')) {
      typeSelect.value = 'youtube';
      chapterListContainer.style.display = 'block';
    }

    chrome.scripting.executeScript(
      {
        target: { tabId: tabs[0].id },
        func: () => ({
          title: document.title,
          description: document.querySelector('meta[name="description"]')?.content || '',
          language: document.documentElement.lang || navigator.language
        })
      },
      (results) => {
        if (!results || !results[0] || chrome.runtime.lastError) {
          console.error('Error in executeScript:', chrome.runtime.lastError);
          pageTitleInput.value = 'Nie udało się pobrać tytułu';
          pageLanguageInput.value = '';
        } else {
          pageTitleInput.value = results[0].result.title || '';
          pageLanguageInput.value = results[0].result.language || '';
          pageDescriptionInput.value = results[0].result.description || '';
        }
      }
    );
  });

  // Send
  sendButton.addEventListener('click', function () {
    const apiKey = apiKeyInput.value.trim();
    const serverUrl = serverUrlInput.value.trim();
    const note = noteInput.value;
    const type = typeSelect.value;
    const title = pageTitleInput.value;
    const language = pageLanguageInput.value; // prefer UI value

    if (!apiKey) {
      alert('Podaj API KEY');
      return;
    }
    if (!serverUrl) {
      alert('Podaj adres serwera');
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
          const data = {
            note: note,
            url: pageUrl,
            type: type,
            text: text,
            html: html,
            title: title,
            language: language,
            paywall: paywall,
            source: sourceSelect.value,
            chapter_list: chapter_list.value
          };
          if (refreshExisting.checked) {
            data.operation = 'fill_missing_html';
          }

          return fetch(serverUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'x-api-key': apiKey
            },
            body: JSON.stringify(data)
          });
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
            throw new Error(result.message || `Serwer zwrócił błąd: ${response.status} - ${response.statusText}`);
          }
          return result;
        })
        .then(result => {
          alert(result.status === 'queued' ? 'Zgłoszenie zostało przekazane do importu.' : 'Strona została dodana pomyślnie!');
          noteInput.value = '';
          setTimeout(() => window.close(), 500);
        })
        .catch(error => {
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
