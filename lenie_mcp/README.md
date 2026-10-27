# lenie_mcp — lokalny serwer MCP (stdio)

Tworzenie notatek Obsidian z dokumentów Lenie z poziomu Claude Code desktop (i ChatGPT Desktop jako wtyczka
osobista). Projekt i decyzje: [ADR-030](../docs/adr/adr-030-mcp-server-notes-from-documents.md).

Serwer działa **na Twoim komputerze**, woła REST backendu na NAS (`x-api-key`) i zapisuje do vaulta z dysku.
Nie łączy się z bazą i niczego nie wystawia do internetu.

## Instalacja

```powershell
cd lenie_mcp
uv sync          # własne środowisko, jak pozostałe podprojekty
uv run pytest    # 28 testów, bez sieci
```

## Zmienne środowiskowe (poza repozytorium)

| Zmienna | Znaczenie |
|---|---|
| `LENIE_API_KEY` | klucz serwisowy (`kind=service`) — ten sam co dla skilla `/lenie-obsidian-note` |
| `LENIE_API_URL` | domyślnie `http://192.168.200.7:5055` |
| `LENIE_OBSIDIAN_VAULT` | katalog vaulta na tym komputerze (tryb `local`) |
| `LENIE_VAULT_MODE` | `local` (dysk) lub `remote` (kopia vaulta na NAS przez bramkę `/vault/*`, ADR-030 Etap A2). Domyślnie `local`, gdy ustawiono `LENIE_OBSIDIAN_VAULT`, w przeciwnym razie `remote` |

**Tryb `remote`** nie wymaga lokalnego vaulta: serwer czyta i zapisuje notatki przez backend na NAS
(`GET /vault/note`, `GET /vault/find`, `POST /vault/apply`, tylko klucz `service`), a kontener
`obsidian-headless-sync` rozsyła zmiany na Twoje urządzenia przez Obsidian Sync. Zapis jest wąski:
tylko `02-wiedza/`, tylko nowe pliki, dopisek wyłącznie do `_index.md` z kontrolą hasha.

## Rejestracja w Claude Code

Plik `.mcp.json` (projektowy) albo konfiguracja użytkownika — wartości kluczy **nie** są wpisywane, tylko
rozwijane ze zmiennych środowiskowych:

```json
{
  "mcpServers": {
    "lenie": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "<ścieżka do repo>/lenie_mcp", "lenie-mcp"],
      "env": {
        "LENIE_API_KEY": "${LENIE_API_KEY}",
        "LENIE_OBSIDIAN_VAULT": "${LENIE_OBSIDIAN_VAULT}"
      }
    }
  }
}
```

**Nie dodawaj `obsidian_commit_package` do listy auto-allow** — to jedyne narzędzie, które zapisuje pliki.

## Narzędzia

Odczyt: `lenie_get_document`, `lenie_list_analysis_runs`, `lenie_get_chunks`, `lenie_get_document_text`,
`obsidian_read_index`, `obsidian_read_note`, `obsidian_find_notes`.
Zapis (dwa kroki): `obsidian_propose_package` (nic nie zapisuje, zwraca podgląd i `proposal_id`) →
`obsidian_commit_package` (po jawnej zgodzie; zapis plików, potem `POST /document/<id>/obsidian_notes`).
Ponowne wywołanie `commit` z tym samym `proposal_id` po błędzie bazy powtarza tylko synchronizację.

Zapis wymaga wdrożonych na NAS endpointów `POST /document/<id>/obsidian_notes` oraz (tryb `remote`) `/vault/*`
(backend, ten sam PR).
