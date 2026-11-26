import json
from unittest.mock import Mock

import pytest
from flask import Flask

from library import company_registry_client as client
from library import company_registry_service as service
from library.company_registry_routes import company_registry_bp


def xml(filings="", status="IstniejaInformacje"):
    return f'<Response xmlns="{client.CRBR_NS}"><Status>{status}</Status>{filings}</Response>'


def filing(start="2026-03-02", end="2026-11-26"):
    return f"""<SpolkaIBeneficjenci><Nazwa>Przykład</Nazwa><KRS>0000123456</KRS>
    <DataPoczatkuPrezentacjiZgloszenia>{start}</DataPoczatkuPrezentacjiZgloszenia>
    <DataKoncaPrezentacjiZgloszenia>{end}</DataKoncaPrezentacjiZgloszenia>
    <ListaBeneficjentowRzeczywistych><BeneficjentRzeczywisty>
    <PierwszeImie>Ada</PierwszeImie><Nazwisko>Testowa</Nazwisko>
    <PESEL>12345678901</PESEL><DataUrodzenia>1980-02-03</DataUrodzenia>
    <ListaInformacjiOUdzialach><InformacjaOUdzialach>
    <UprawnieniaWlascicielskiePosrednie>60% FIKCYJNA GROUP SP. Z O.O., która ma 50%; 98765432109</UprawnieniaWlascicielskiePosrednie>
    <UprawnieniaWlascicielskieBezposrednie><Ilosc>25</Ilosc><PESEL>12345678901</PESEL></UprawnieniaWlascicielskieBezposrednie>
    </InformacjaOUdzialach></ListaInformacjiOUdzialach></BeneficjentRzeczywisty></ListaBeneficjentowRzeczywistych>
    <ListaReprezentantow><PESEL>12345678901</PESEL></ListaReprezentantow></SpolkaIBeneficjenci>"""


def krs_payload():
    return {"odpis": {"naglowekP": {"stanZDnia": "26.11.2026", "wpis": [
        {"numerWpisu": 1, "dataWpisu": "01.01.2020"}, {"numerWpisu": 6, "dataWpisu": "30.09.2026"}]},
        "dane": {"dzial1": {"danePodmiotu": {"nazwa": [{"nazwa": "Przykład", "nrWpisuWprow": 1}]},
                            "wspolnicySpzoo": [
            {"nazwa": [{"nazwa": "Fikcyjna Group spółka z ograniczoną odpowiedzialnością", "nrWpisuWprow": 1, "nrWpisuWykr": 6}],
             "posiadaneUdzialy": [{"posiadaneUdzialy": "50 udziałów", "nrWpisuWprow": 1, "nrWpisuWykr": 6}]},
            {"nazwisko": [{"nazwisko": {"nazwiskoICzlon": "T*****"}, "nrWpisuWprow": 6}],
             "imiona": [{"imiona": {"imie": "A****"}, "nrWpisuWprow": 6}],
             "identyfikator": {"pesel": "12345678901"},
             "posiadaneUdzialy": [{"posiadaneUdzialy": "50 udziałów 98765432109", "nrWpisuWprow": 6}]}]}}}}


def test_privacy_history_and_warnings(monkeypatch, caplog):
    filings = client.parse_crbr(xml(filing("2020-01-01", "2026-03-01") + filing()))
    data = client.parse_krs(krs_payload())
    monkeypatch.setattr(client, "get_crbr", lambda **kw: filings)
    monkeypatch.setattr(client, "get_krs", lambda krs: data)
    result = service.check_company(krs="123456")
    serialized = json.dumps(result) + caplog.text
    for forbidden in ("12345678901", "98765432109", "1980-02-03", "PESEL", "DataUrodzenia", "pesel"):
        assert forbidden not in serialized
    assert "[ukryto]" in serialized
    assert [f["is_current"] for f in filings] == [True, False]
    assert data["current_shareholders"][0]["name"] == "A**** T*****"
    assert data["former_shareholders"][0]["removed_at"] == "2026-09-30"
    assert {w["code"] for w in result["warnings"]} == {
        "krs_shareholders_changed_after_filing", "crbr_mentions_former_shareholder"}


@pytest.mark.parametrize("payload", ['<!DOCTYPE x><x/>', '<!DOCTYPE x [<!ENTITY e "secret">]><x>&e;</x>', '<broken>'])
def test_reject_unsafe_xml(payload):
    with pytest.raises(Exception):
        client.parse_crbr(payload)


@pytest.mark.parametrize("kwargs", [{}, {"nip": "123", "krs": "1"}, {"nip": "1234567890"}, {"nip": ""},
                                    {"nip": "abc5260250995"}, {"krs": "12345678901"}, {"krs": "x"}])
def test_invalid_input(kwargs):
    with pytest.raises(ValueError):
        service.check_company(**kwargs)


def test_normalization():
    assert service.normalize_nip("PL 526-025-09-95") == "5260250995"
    assert service.normalize_krs("123") == "0000000123"


def test_independent_failures_and_discovery(monkeypatch):
    crbr = Mock(side_effect=RuntimeError("12345678901"))
    krs = Mock(return_value=client.parse_krs(krs_payload()))
    monkeypatch.setattr(client, "get_crbr", crbr)
    monkeypatch.setattr(client, "get_krs", krs)
    result = service.check_company(krs="1")
    assert result["crbr"]["status"] == "error"
    assert result["krs"]["status"] == "ok"
    assert "12345678901" not in json.dumps(result)
    crbr.side_effect = None
    crbr.return_value = []
    krs.reset_mock()
    assert service.check_company(nip="5260250995")["krs"]["status"] == "skipped"
    krs.assert_not_called()
    crbr.return_value = client.parse_crbr(xml(filing()))
    krs.side_effect = RuntimeError("remote failure")
    result = service.check_company(nip="5260250995")
    krs.assert_called_once_with("0000123456")
    assert result["crbr"]["status"] == "ok"
    assert result["krs"]["status"] == "error"


def test_warning_negatives():
    filings = client.parse_crbr(xml(filing("2026-10-01")))
    data = client.parse_krs(krs_payload())
    data["former_shareholders"][0]["name"] = "Inna Firma S.A."
    assert service._warnings(filings, data) == []
    data["current_shareholders"][0].update(added_entry=1, added_at="2027-01-01")
    assert service._warnings(filings, data) == []


def test_correction_entry_is_not_a_shareholder_change():
    payload = krs_payload()
    payload["odpis"]["naglowekP"]["wpis"][1]["opis"] = "SPROSTOWANIE WPISU"
    data = client.parse_krs(payload)
    assert data["current_shareholders"][0]["added_by_correction"] is True
    warnings = service._warnings(client.parse_crbr(xml(filing())), data)
    assert "krs_shareholders_changed_after_filing" not in {w["code"] for w in warnings}


def test_http_contract_and_fallback(monkeypatch):
    observer = Mock(side_effect=lambda **kw: kw["request_fn"]())
    monkeypatch.setattr(client, "observed_request", observer)
    post = Mock(return_value=Mock(content=xml(status="BrakInformacji").encode()))
    monkeypatch.setattr(client.requests, "post", post)
    assert client.get_crbr(krs="0000000001") == []
    request = client.fromstring(post.call_args.kwargs["data"])
    assert request.find(f".//{{{client.CRBR_NS}}}DataOd").text == "2019-10-13"
    assert request.find(f".//{{{client.CRBR_NS}}}DataDo").text == client.date.today().isoformat()
    assert request.find(".//PobierzInformacjeOSpolkachIBeneficjentachDane") is not None
    get = Mock(side_effect=[Mock(status_code=404), Mock(status_code=200, json=lambda: krs_payload())])
    monkeypatch.setattr(client.requests, "get", get)
    result = client.get_krs("0000000001")
    assert result["name"] == "Przykład"
    assert result["source_url"].endswith("?rejestr=S&format=json")
    assert [call.kwargs["params"]["rejestr"] for call in get.call_args_list] == ["P", "S"]
    assert [call.kwargs["service"] for call in observer.call_args_list] == ["crbr", "krs", "krs"]


def test_route(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(company_registry_bp)
    monkeypatch.setattr(client, "get_crbr", lambda **kw: [])
    monkeypatch.setattr(client, "get_krs", lambda krs: None)
    browser = app.test_client()
    assert browser.get("/company_registry/check").status_code == 400
    response = browser.get("/company_registry/check?krs=1")
    assert response.status_code == 200
    assert response.json["krs"]["status"] == "not_found"
