# ADR-013: Custom LLM Provider Abstraction — Keep Own Interface, Evaluate LiteLLM for Future

**Date:** 2026-03 (Sprint 6)
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

The project uses a custom abstraction layer for LLM API calls:
- `backend/library/ai.py` — `ai_ask()` routes requests to the correct provider based on model name
- `backend/library/embedding.py` — `get_embedding()` routes to the correct embedding provider
- Per-provider integrations: OpenAI SDK (`openai`), AWS Bedrock (`boto3`), Google Vertex AI (`vertexai`), CloudFerro Sherlock (OpenAI-compatible), ArkLabs (OpenAI-compatible)

The question arose whether to replace this custom layer with a framework like **LangChain** or a lightweight proxy like **LiteLLM**.

### Alternatives Considered

**1. LangChain**
- Zunifikowany interfejs dla wszystkich providerów (`langchain_openai`, `langchain_aws`, `langchain_google_vertexai`)
- Bogaty ekosystem: agenty, chainy, RAG pipeline, integracja z pgvector
- Natywna integracja z LangSmith i Langfuse (callback handler)
- **Odrzucony, ponieważ:**
  - Ciężka zależność — duża biblioteka z częstymi breaking changes między wersjami
  - Projekt nie buduje agentów, chainów ani złożonych pipeline'ów — wzorzec użycia to proste zapytanie→odpowiedź
  - Dodaje warstwę abstrakcji i "magii" utrudniającą debugowanie
  - Overhead niewspółmierny do aktualnych potrzeb (5 providerów, prosty routing)

**2. LiteLLM**
- Lekka biblioteka — jeden interfejs (kompatybilny z OpenAI) dla 100+ providerów
- `litellm.completion(model="bedrock/amazon.nova-pro", messages=[...])` — zero konfiguracji per-provider
- Wbudowana integracja z Langfuse
- Nie narzuca frameworka — zastępuje tylko warstwę transportową
- **Rozważany jako przyszła opcja** — sensowny gdy liczba providerów wzrośnie lub gdy utrzymanie własnego kodu stanie się kosztowne

**3. Pozostanie przy własnej implementacji (wybrane)**
- Obecna warstwa jest prosta, działa i pokrywa wszystkie 5 providerów
- Zero zewnętrznych zależności na warstwie routingu
- Pełna kontrola nad zachowaniem — brak "magii"
- Debugowanie proste — bezpośrednie wywołania SDK

### Decision

1. **Pozostać przy własnej warstwie abstrakcji** (`ai.py`, `embedding.py`) jako primary interface dla LLM calls.
2. **Nie wprowadzać LangChain** — projekt nie wymaga agentów, chainów ani złożonych pipeline'ów.
3. **Rozważyć migrację do LiteLLM** gdy:
   - Liczba obsługiwanych providerów wzrośnie powyżej 7-8
   - Pojawi się potrzeba obsługi nowych API (np. streaming, function calling) wymagającej znacznych zmian w każdym providerze
   - Koszt utrzymania per-provider integrations stanie się istotny
4. **Aktywować Langfuse** jako narzędzie observability dla LLM calls (osobna decyzja — patrz `docs/observability.md`, sekcja "LLM Observability").

### Rationale

- **YAGNI** — obecny wzorzec użycia (prompt→odpowiedź, 5 providerów) nie uzasadnia wprowadzenia frameworka
- **Koszt utrzymania jest niski** — dodanie nowego providera to ~50 linii kodu w osobnym pliku + 5 linii routingu w `ai.py`
- **LiteLLM jako ewolucja, nie rewolucja** — gdyby migracja była potrzebna, LiteLLM jest drop-in replacement dla `ai_ask()` z minimalnym ryzykiem. Interfejs jest kompatybilny z OpenAI SDK, więc integracja z Langfuse nie zmienia się.
- **LangChain opłaca się dopiero przy złożonych workflow** — agenty z narzędziami, pamięcią, wielokrokowymi chainami, zaawansowany RAG. Żaden z tych wzorców nie jest aktualnie potrzebny.

### Consequences

- **Positive:** Brak dodatkowej zależności — mniej ryzyka breaking changes, mniejszy rozmiar deploymentu
- **Positive:** Pełna kontrola nad retry logic, error handling, token counting per provider
- **Positive:** Jasna ścieżka migracji do LiteLLM gdy zajdzie potrzeba
- **Negative:** Każdy nowy provider wymaga ręcznej integracji (~50 LOC)
- **Negative:** Brak gotowych abstrakcji na streaming, function calling — trzeba implementować samodzielnie per provider gdy będą potrzebne

### Related Artifacts

- `backend/library/ai.py` — LLM routing layer (`ai_ask()`)
- `backend/library/embedding.py` — Embedding routing layer (`get_embedding()`)
- `backend/library/api/openai/openai_my.py` — OpenAI integration
- `backend/library/api/aws/bedrock_ask.py` — AWS Bedrock integration
- `backend/library/api/google/google_vertexai.py` — Google Vertex AI integration
- `backend/library/api/cloudferro/sherlock/sherlock.py` — CloudFerro Bielik integration
- `backend/library/api/arklabs/arklabs_embedding.py` — ArkLabs embedding integration
- `docs/observability.md` — LLM observability strategy (Langfuse)
- `docs/technology-choices.md` — Multi-provider abstraction rationale
