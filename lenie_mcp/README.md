# lenie_mcp — lokalny serwer MCP (stdio)

Tworzenie notatek Obsidian z dokumentów Lenie z poziomu Claude Code desktop (i ChatGPT Desktop jako wtyczka
osobista). Projekt i decyzje: [ADR-030](../docs/adr/adr-030-mcp-server-notes-from-documents.md).

Proces serwera działa **na Twoim komputerze** (stdio), ale nie łączy się z bazą i niczego nie wystawia do
internetu. Woła REST backendu na NAS (`x-api-key`), a vault czyta i zapisuje na jeden z dwóch sposobów:

- **`remote` (zalecany):** przez bramkę `/vault/*` w backendzie, na kopii vaulta na NAS. Kontener
  `obsidian-headless-sync` rozsyła zmiany na Twoje urządzenia przez Obsidian Sync. Nie wymaga lokalnej ścieżki.
- **`local`:** bezpośrednio na dysku tego komputera (`LENIE_OBSIDIAN_VAULT`).

## Instalacja

```powershell
cd lenie_mcp
uv sync          # własne środowisko, jak pozostałe podprojekty
uv run pytest    # 34 testy, bez sieci
```

## Zmienne środowiskowe (poza repozytorium)

| Zmienna | Znaczenie |
|---|---|
| `LENIE_API_KEY` | klucz serwisowy (`kind=service`) — ten sam co dla skilla `/lenie-obsidian-note` |
| `LENIE_API_URL` | domyślnie `http://192.168.200.7:5055` |
| `LENIE_VAULT_MODE` | `remote` (NAS) lub `local` (dysk). Bez tej zmiennej: `local`, gdy ustawiono `LENIE_OBSIDIAN_VAULT`, w przeciwnym razie `remote` |
| `LENIE_OBSIDIAN_VAULT` | katalog vaulta na tym komputerze — **tylko dla trybu `local`**, w `remote` pomiń |

Bramka `remote` (`GET /vault/note`, `GET /vault/find`, `POST /vault/apply`, tylko klucz `service`) jest wąska:
tylko `02-wiedza/`, tylko nowe pliki (bez nadpisywania), dopisek wyłącznie do `_index.md` z kontrolą hasha.

## Rejestracja w Claude Code

Plik `.mcp.json` (projektowy) albo konfiguracja użytkownika — wartości kluczy **nie** są wpisywane, tylko
rozwijane ze zmiennych środowiskowych. Tryb `remote`:

```json
{
  "mcpServers": {
    "lenie": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "<ścieżka do repo>/lenie_mcp", "lenie-mcp"],
      "env": {
        "LENIE_API_KEY": "${LENIE_API_KEY}",
        "LENIE_VAULT_MODE": "remote"
      }
    }
  }
}
```

Dla trybu `local` zamień `LENIE_VAULT_MODE` na `"local"` i dodaj
`"LENIE_OBSIDIAN_VAULT": "${LENIE_OBSIDIAN_VAULT}"`.

**Nie dodawaj `obsidian_commit_package` do listy auto-allow** — to jedyne narzędzie, które zapisuje pliki.

## Narzędzia

Odczyt: `lenie_get_document`, `lenie_list_analysis_runs`, `lenie_get_chunks`, `lenie_get_document_text`,
`obsidian_read_index`, `obsidian_read_note`, `obsidian_find_notes`.
Zapis (dwa kroki): `obsidian_propose_package` (nic nie zapisuje, zwraca podgląd i `proposal_id`) →
`obsidian_commit_package` (po jawnej zgodzie; zapis plików, potem `POST /document/<id>/obsidian_notes`).
Ponowne wywołanie `commit` z tym samym `proposal_id` po błędzie bazy powtarza tylko synchronizację.

Zapis wymaga wdrożonych na NAS endpointów `POST /document/<id>/obsidian_notes` oraz (tryb `remote`) `/vault/*`
(backend, ten sam PR).
