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

  function toggleChapterListVisibility() {
    chapterListContainer.style.display = (typeSelect.value === 'youtube') ? 'block' : 'none';
  }

  toggleChapterListVisibility();
  typeSelect.addEventListener('change', toggleChapterListVisibility);

  // Load settings
  chrome.storage.sync.get(['apiKey', 'serverUrl'], function (data) {
    if (data.apiKey) apiKeyInput.value = data.apiKey;
    if (data.serverUrl) serverUrlInput.value = data.serverUrl;
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

          return fetch(serverUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'x-api-key': apiKey
            },
            body: JSON.stringify(data)
          });
        })
        .then(response => {
          if (!response.ok) {
            throw new Error(`Serwer zwrócił błąd: ${response.status} - ${response.statusText}`);
          }
          return response.json();
        })
        .then(() => {
          alert('Strona została dodana pomyślnie!');
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
