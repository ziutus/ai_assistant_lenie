# Eksperyment myślowy: komercyjne wdrożenie on-premise

Status: eksperyment myślowy, niski priorytet — nauka architektury w wolnym czasie, horyzont 1+ rok  
Powiązane: [../README.md](../README.md) · [../commercial-multi-tenant-scaling-experiment.md](../commercial-multi-tenant-scaling-experiment.md)

## Czym to się różni od `nas/`

`../nas/` to mój własny, domowy QNAP — środowisko, które kontroluję w 100% i które faktycznie działa. Ten dokument dotyczy innego scenariusza: Lenie wdrożone **on-premise u kogoś innego** (np. w ramach hipotetycznej sprzedaży rozwiązania organizacji, która z jakiegoś powodu nie chce chmury) — serwer/rack/datacenter, którego nie kontroluję i którego operacje IT nie są moje.

## Co się zmienia względem NAS-a

- **Sprzęt i sieć nie są moje** — nie mogę zakładać konkretnego QNAP-a, konkretnych portów, konkretnej topologii sieciowej. Konfiguracja musi być w pełni sparametryzowana (już dziś częściowo tak jest — `STORAGE_*`/Vault, patrz `docs/storage.md`).
- **Object storage musi być self-hosted** — MinIO działa już dziś i przenosi się bez zmian kodu. Alternatywy do rozważenia przy większej skali: Ceph RGW (dojrzały, ciężki operacyjnie), SeaweedFS, Garage (lżejsze, mniej dojrzałe) — patrz też sekcja 16.5 w [`../nas/storage-and-jobs-migration-plan.md`](../nas/storage-and-jobs-migration-plan.md).
- **Ja nie robię już operacji** — potrzebny byłby instalator/paczka wdrożeniowa, wersjonowane wydania, dokumentacja dla cudzego zespołu IT, a nie ręczne `nas-deploy.sh` przez SSH.
- **Model wsparcia** — kto reaguje na awarię o 2 w nocy? To pytanie nieistotne dla instalacji domowej, kluczowe dla on-prem u klienta.
- **Sieć może być ograniczona** — firewall korporacyjny, brak dostępu do internetu (LLM przez chmurowe API może być zablokowany), potencjalnie wymóg lokalnego modelu językowego zamiast Bielik/OpenAI/Bedrock przez sieć.
- **Zgodność i audyt** — inny poziom wymagań niż projekt hobbystyczny (logi, kto miał dostęp do czego, retencja).

## Co to ma wspólnego z eksperymentem komercyjnym wielu użytkowników

Ten dokument dotyczy **gdzie** aplikacja działa; [`../commercial-multi-tenant-scaling-experiment.md`](../commercial-multi-tenant-scaling-experiment.md) dotyczy **dla ilu niezaufanych osób**. On-prem u klienta korporacyjnego niemal zawsze oznacza też wielu użytkowników z izolacją — te dwa dokumenty się przecinają, ale to osobne osie: da się sobie wyobrazić on-prem dla jednej osoby (dzisiejszy NAS) i chmurę hiperskalera dla wielu niezaufanych najemców.

## Co NIE robić teraz

Nic. To jedyny z trzech katalogów eksperymentalnych, który nie ma dziś żadnego taniego kroku wartego zrobienia w kodzie — w przeciwieństwie do modelu właściciela danych (przydatny też dla `nas/`) czy abstrakcji storage (przydatna też dla `hyperscalers/`/`eu_cloud/`), pełne odseparowanie od konkretnego sprzętu i model wsparcia to praca, która ma sens dopiero przy realnej decyzji o sprzedaży on-prem.
