"""Independent registry flow and strict privacy boundary; no external calls."""

import json
from unittest.mock import Mock

import pytest
from flask import Flask

from library import company_registry_service as service
from library import company_registry_vat as vat
from library import organization_identifiers
from library.company_registry_routes import company_registry_bp
from library.db import engine
from library.db.models import Organization


REAL_GET_VAT = vat.get_vat


@pytest.fixture(autouse=True)
def clients(monkeypatch):
    mocks = {"vat": Mock(return_value=None), "crbr": Mock(return_value=[]),
             "krs": Mock(return_value=None), "ceidg": Mock(return_value=None)}
    monkeypatch.setattr(vat, "get_vat", mocks["vat"])
    monkeypatch.setattr(service.client, "get_crbr", mocks["crbr"])
    monkeypatch.setattr(service.client, "get_krs", mocks["krs"])
    monkeypatch.setattr(service.ceidg_client, "get_company_by_nip", mocks["ceidg"])
    return mocks


def test_vat_then_krs_and_crbr(clients):
    clients["vat"].return_value = {"krs": "123", "nip": "5260250995"}
    result = service.check_company(nip="5260250995")
    clients["crbr"].assert_called_once_with(nip="5260250995", krs=None)
    clients["krs"].assert_called_once_with("0000000123")
    clients["ceidg"].assert_not_called()
    assert result["vat"]["status"] == "ok"
    assert result["ceidg"]["status"] == "skipped"


def test_ceidg_projection_and_failure_message(clients, caplog):
    clients["ceidg"].return_value = {
        "nazwa": "Firma 12345678901", "status": "AKTYWNY", "dataRozpoczecia": "2020-01-01",
        "dataZawieszenia": "2022-01-01", "dataWykreslenia": "2023-01-01",
        "telefon": "private-phone", "email": "private-email", "www": "private-web", "wlasciciel": {"imie": "private-owner"},
        "adresDzialalnosci": {"miasto": "Łódź", "kod": "90-001", "ulica": "private-street", "budynek": "private-house", "lokal": "private-flat"},
    }
    result = service.check_company(nip="5260250995")
    company = result["ceidg"]["company"]
    assert company["city"] == "Łódź"
    assert set(company) == {"name", "status", "start_date", "suspension_date", "removal_date", "city", "postal_code"}
    assert "private-" not in json.dumps(result) + caplog.text
    assert "12345678901" not in json.dumps(result) + caplog.text
    clients["ceidg"].return_value = None
    assert "brak wpisu, klucza API" in service.check_company(nip="5260250995")["ceidg"]["message"]


def test_vat_privacy():
    subject = {"name": "Firma 12345678901", "pesel": "12345678901", "accountNumbers": ["private-account"],
               "representatives": [{"name": "private-person"}], "authorizedClerks": ["private-clerk"], "partners": ["private-partner"],
               "workingAddress": "ul. Prywatna 15, 90-001 Łódź", "residenceAddress": "90-001 Łódź, ul. Prywatna 15"}
    result = vat.parse_vat(subject)
    assert result["workingAddress"] == result["residenceAddress"] == "90-001 Łódź"
    assert "private-" not in json.dumps(result)
    assert "12345678901" not in json.dumps(result)
    assert "Prywatna" not in json.dumps(result)
    subject["krs"] = "123"
    assert "Prywatna" in vat.parse_vat(subject)["workingAddress"]
    subject["name"] = {"pesel": "private-nested"}
    assert vat.parse_vat(subject)["name"] == ""
    assert vat.postal_city("ul. Prywatna 15") == ""
    assert vat.postal_city("90-001 Łódź Prywatna 15") == ""
    assert vat.postal_city("90-001 Łódź ul. Prywatna 15") == "90-001 Łódź"


def test_vat_http(monkeypatch):
    observer = Mock(side_effect=lambda **kw: kw["request_fn"]())
    response = Mock(status_code=200, json=lambda: {"result": {"subject": None}})
    get = Mock(return_value=response)
    monkeypatch.setattr(vat, "observed_request", observer)
    monkeypatch.setattr(vat.requests, "get", get)
    assert REAL_GET_VAT("5260250995") is None
    assert observer.call_args.kwargs["service"] == "vat_whitelist"
    assert get.call_args.args[0] == f"{vat.VAT_URL}/5260250995"
    assert get.call_args.kwargs["params"] == {"date": vat.date.today().isoformat()}
    for code, body in [(429, {}), (200, {"code": "X", "message": "private-remote"}), (200, {"error": "private-remote"})]:
        response.status_code = code
        response.json = lambda: body
        with pytest.raises(vat.VatLookupError, match="dzienny limit"):
            REAL_GET_VAT("5260250995")


def stored(monkeypatch, rows):
    session = Mock()
    session.get.return_value = Organization(id=1, canonical_name="One")
    monkeypatch.setattr(engine, "get_scoped_session", lambda: session)
    monkeypatch.setattr(organization_identifiers, "list_identifiers", lambda *args: rows)
    return session


def number(kind, value):
    return dict(country_code="PL", identifier_type=kind, value=value)


def test_stored_pair_and_suggestions_are_read_only(monkeypatch, clients):
    session = stored(monkeypatch, [number("nip", "5260250995"), number("krs", "0000000001")])
    clients["vat"].return_value = {"nip": "5260250995", "krs": "2", "regon": "012345675"}
    clients["krs"].return_value = {"regon": "012345675"}
    result = service.check_company(organization_id=1)
    clients["krs"].assert_called_once_with("0000000001")
    clients["crbr"].assert_called_once_with(nip="5260250995", krs=None)
    assert [(s["identifier_type"], s["value"]) for s in result["suggested_identifiers"]] == [
        ("krs", "0000000002"), ("regon", "012345675")]
    assert all(s["source_url"].startswith("https://") for s in result["suggested_identifiers"])
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.flush.assert_not_called()


@pytest.mark.parametrize("rows", [[], [number("nip", "5260250995"), number("nip", "123")],
                                  [number("krs", "1"), number("krs", "2")]])
def test_missing_or_ambiguous_stored_numbers(monkeypatch, clients, rows):
    stored(monkeypatch, rows)
    with pytest.raises(ValueError):
        service.check_company(organization_id=1)
    for mock in clients.values():
        mock.assert_not_called()


@pytest.mark.parametrize("kwargs", [{"organization_id": 0}, {"organization_id": True}, {"organization_id": "1.0"},
                                    {"organization_id": 1, "nip": "5260250995"}, {"organization_id": 1, "krs": "1"}])
def test_exactly_one_and_valid_id(kwargs):
    with pytest.raises(ValueError):
        service.check_company(**kwargs)


def test_route_organization_not_found(monkeypatch):
    session = stored(monkeypatch, [])
    session.get.return_value = None
    app = Flask(__name__)
    app.register_blueprint(company_registry_bp)
    assert app.test_client().get("/company_registry/check?organization_id=99").status_code == 404


def test_independent_errors(clients, caplog):
    clients["vat"].side_effect = RuntimeError("private-remote")
    clients["crbr"].side_effect = RuntimeError("private-remote")
    clients["ceidg"].side_effect = RuntimeError("private-remote")
    result = service.check_company(nip="5260250995")
    assert all(result[key]["status"] == "error" for key in ("vat", "crbr", "ceidg"))
    assert result["krs"]["status"] == "skipped"
    assert "dzienny limit" in result["vat"]["message"]
    assert "private-remote" not in json.dumps(result) + caplog.text
