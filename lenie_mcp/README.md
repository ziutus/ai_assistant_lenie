# lenie_mcp — serwer MCP (stdio lub HTTP na NAS)

Tworzenie notatek Obsidian z dokumentów Lenie z poziomu Claude Code desktop (i ChatGPT Desktop jako wtyczka
osobista). Projekt i decyzje: [ADR-030](../docs/adr/adr-030-mcp-server-notes-from-documents.md).

Serwer może działać na dwa sposoby:

- **HTTP w kontenerze `lenie-mcp` na NAS** (`http://192.168.200.7:8765/mcp`, token Bearer) — jedna instancja dla
  wszystkich Twoich urządzeń, nic nie instalujesz lokalnie. Zob. [Tryb HTTP](#tryb-http-kontener-na-nas).
- **stdio, proces uruchamiany lokalnie przez klienta** — dalej opisany niżej.

Serwer nie łączy się z bazą i niczego nie wystawia do internetu. Woła REST backendu na NAS (`x-api-key`), a vault
czyta i zapisuje na jeden z dwóch sposobów:

- **`remote` (zalecany):** przez bramkę `/vault/*` w backendzie, na kopii vaulta na NAS. Kontener
  `obsidian-headless-sync` rozsyła zmiany na Twoje urządzenia przez Obsidian Sync. Nie wymaga lokalnej ścieżki.
- **`local`:** bezpośrednio na dysku tego komputera (`LENIE_OBSIDIAN_VAULT`).

## Instalacja

```powershell
cd lenie_mcp
uv sync          # własne środowisko, jak pozostałe podprojekty
uv run pytest    # 41 testów, bez sieci
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

## Tryb HTTP (kontener na NAS)

Kontener `lenie-mcp` (`infra/docker/compose.nas.yaml`, port **8765**) działa w trybie `remote`, woła backend po
sieci Dockera (`lenie-ai-server:5000`) i przyjmuje wyłącznie żądania z nagłówkiem
`Authorization: Bearer <token>`; jedyny publiczny adres to `GET /healthz`. Sprawdzany jest też nagłówek `Host`
(`LENIE_MCP_ALLOWED_HOSTS`), a żądania z `Origin` przeglądarki są odrzucane.

**Sekrety** są w `/share/Container/lenie-env/lenie_mcp.env` na NAS (wzór: `infra/docker/lenie_mcp.env.example`):
`LENIE_API_KEY` — dedykowany klucz `service` (`lenie-mcp-nas`, można go odwołać niezależnie od klucza skilla) i
`LENIE_MCP_TOKEN` — token klienta.

**Wdrożenie** (tylko z domowej sieci LAN): `bash ./infra/docker/nas-deploy.sh lenie-mcp`.

**Rejestracja w Claude Code** — `.mcp.json` (token jest rozwijany ze zmiennej środowiskowej, nie wpisujemy go):

```json
{
  "mcpServers": {
    "lenie": {
      "type": "http",
      "url": "http://192.168.200.7:8765/mcp",
      "headers": { "Authorization": "Bearer ${LENIE_MCP_TOKEN}" }
    }
  }
}
```

Token pobierz z NAS do zmiennej użytkownika, bez wypisywania go na ekran (PowerShell):

```powershell
$t = (ssh admin@192.168.200.7 "grep '^LENIE_MCP_TOKEN=' /share/Container/lenie-env/lenie_mcp.env").Split('=',2)[1]
[Environment]::SetEnvironmentVariable('LENIE_MCP_TOKEN', $t, 'User')   # po zmianie uruchom Claude Code od nowa
```

Rotacja tokenu: zmień wartość w pliku env na NAS i `docker restart lenie-mcp`, potem zaktualizuj zmienną u klientów.
Ruch jest zwykłym HTTP w sieci domowej (token idzie otwartym tekstem po LAN) — poza domem nie wystawiaj portu
8765 do internetu bez tunelu/TLS (Etap B2 w ADR-030).

## Rejestracja w Claude Code (stdio, lokalnie)

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
