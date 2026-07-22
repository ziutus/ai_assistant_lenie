# Eksperyment myślowy: komercyjne wdrożenie on-premise

Status: eksperyment myślowy, niski priorytet — nauka architektury w wolnym czasie, horyzont 1+ rok  
Powiązane: [../README.md](../README.md) · [../commercial-multi-tenant-scaling-experiment.md](../commercial-multi-tenant-scaling-experiment.md)

## Czym to się różni od `nas/`

`../nas/` to mój własny, domowy QNAP — środowisko, które kontroluję w 100% i które faktycznie działa. Ten dokument dotyczy innego scenariusza: Lenie wdrożone **on-premise u kogoś innego** (np. w ramach hipotetycznej sprzedaży rozwiązania organizacji, która z jakiegoś powodu nie chce chmury) — serwer/rack/datacenter, którego nie kontroluję i którego operacje IT nie są moje.

## Co to ma wspólnego z eksperymentem komercyjnym wielu użytkowników

Ten dokument dotyczy **gdzie** aplikacja działa; [`../commercial-multi-tenant-scaling-experiment.md`](../commercial-multi-tenant-scaling-experiment.md) dotyczy **dla ilu niezaufanych osób**. To osobne osie: da się sobie wyobrazić on-prem dla jednej osoby (dzisiejszy NAS) i chmurę hiperskalera dla wielu niezaufanych najemców.

## Co NIE robić teraz

Nic. To jedyny z trzech katalogów eksperymentalnych, który nie ma dziś żadnego taniego kroku wartego zrobienia w kodzie — w przeciwieństwie do modelu właściciela danych (przydatny też dla `nas/`) czy abstrakcji storage (przydatna też dla `hyperscalers/`/`eu_cloud/`), pełne odseparowanie od konkretnego sprzętu i model wsparcia to praca, która ma sens dopiero przy realnej decyzji o sprzedaży on-prem.
