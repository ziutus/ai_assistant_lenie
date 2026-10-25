"""DB-backed additions to the NER gazetteers (ADR-029): cache, resilience, validation, merging."""

import pytest

pytest.importorskip("unidecode")

from library import city_gazetteer, geocode_aliases, ner_gazetteer_store as store
from library.ner_gazetteer_store import GazetteerEntry, GazetteerValidationError, validate_entry


@pytest.fixture(autouse=True)
def fresh_cache():
    store.invalidate_cache()
    yield
    store.invalidate_cache()


def provide(monkeypatch, rows):
    calls = []

    def fetch():
        calls.append(1)
        return list(rows)

    monkeypatch.setattr(store, "_fetch_rows", fetch)
    return calls


class TestStore:
    def test_groups_entries_by_kind(self, monkeypatch):
        provide(monkeypatch, [
            GazetteerEntry("city", "Teksas", ("teksas*",)),
            GazetteerEntry("geocode_alias", "Luizjana", (), "Louisiana"),
        ])
        assert [e.name_pl for e in store.get_entries("city")] == ["Teksas"]
        assert store.get_entries("geocode_alias")[0].geocode_alias == "Louisiana"
        assert store.get_entries("unknown") == ()

    def test_ttl_cache_and_invalidate(self, monkeypatch):
        calls = provide(monkeypatch, [])
        store.get_entries("city")
        store.get_entries("city")
        assert len(calls) == 1
        store.invalidate_cache()
        store.get_entries("city")
        assert len(calls) == 2

    def test_version_changes_on_refresh(self, monkeypatch):
        provide(monkeypatch, [])
        first = store.cache_version()
        assert store.cache_version() == first
        store.invalidate_cache()
        assert store.cache_version() != first

    @pytest.mark.parametrize("error", [RuntimeError("db down"), SystemExit(1)])
    def test_database_failure_yields_empty_list(self, monkeypatch, error):
        def boom():
            raise error

        monkeypatch.setattr(store, "_fetch_rows", boom)
        assert store.get_entries("city") == ()


class TestValidation:
    def test_city_entry_is_normalized(self):
        values = validate_entry(kind="city", name_pl=" Teksas ", patterns=["Teksas*", "TEKSAŃ*"])
        assert values == {"kind": "city", "name_pl": "Teksas", "patterns": ["teksas*", "teksan*"], "geocode_alias": None}

    def test_alias_entry(self):
        values = validate_entry(kind="geocode_alias", name_pl="Luizjana", geocode_alias=" Louisiana ")
        assert values["geocode_alias"] == "Louisiana"
        assert values["patterns"] == []

    def test_place_mention_entry_is_normalized_like_a_city(self):
        values = validate_entry(kind="place_mention", name_pl="Brama Smoleńska", patterns=["Brama* Smoleńsk*"])
        assert values == {
            "kind": "place_mention", "name_pl": "Brama Smoleńska",
            "patterns": ["brama* smolensk*"], "geocode_alias": None,
        }

    @pytest.mark.parametrize("kwargs", [
        {"kind": "place_mention", "name_pl": "Brama", "patterns": []},
        {"kind": "place_mention", "name_pl": "Brama", "patterns": ["a*"]},
        {"kind": "region", "name_pl": "X", "patterns": ["abc*"]},
        {"kind": "city", "name_pl": "", "patterns": ["abc*"]},
        {"kind": "city", "name_pl": "x" * 201, "patterns": ["abc*"]},
        {"kind": "city", "name_pl": "Teksas", "patterns": []},
        {"kind": "city", "name_pl": "Teksas", "patterns": None},
        {"kind": "city", "name_pl": "Teksas", "patterns": ["a*"]},
        {"kind": "city", "name_pl": "Teksas", "patterns": ["*"]},
        {"kind": "city", "name_pl": "Teksas", "patterns": ["te*xas"]},
        {"kind": "city", "name_pl": "Teksas", "patterns": ["tek.*"]},
        {"kind": "city", "name_pl": "Teksas", "patterns": ["abc*"] * 9},
        {"kind": "city", "name_pl": "Teksas", "patterns": [5]},
        {"kind": "geocode_alias", "name_pl": "Luizjana", "geocode_alias": ""},
        {"kind": "geocode_alias", "name_pl": "Luizjana"},
    ])
    def test_rejects_unsafe_entries(self, kwargs):
        with pytest.raises(GazetteerValidationError):
            validate_entry(**kwargs)


class TestCityGazetteerMerge:
    def test_database_entry_extends_canonicalization(self, monkeypatch):
        assert city_gazetteer.canonical_city_name("Teksasie") is None
        provide(monkeypatch, [GazetteerEntry("city", "Teksas", ("teksas*",))])
        store.invalidate_cache()
        assert city_gazetteer.canonical_city_name("Teksasie") == "Teksas"

    def test_database_pattern_extends_seed_name(self, monkeypatch):
        provide(monkeypatch, [GazetteerEntry("city", "luizjana", ("luzjan*",))])
        assert city_gazetteer.canonical_city_name("Luzjanie") == "Luizjana"
        # Seed patterns of the same name keep working.
        assert city_gazetteer.canonical_city_name("Luisianie") == "Luizjana"

    def test_seed_works_when_database_is_unavailable(self, monkeypatch):
        def boom():
            raise RuntimeError("db down")

        monkeypatch.setattr(store, "_fetch_rows", boom)
        assert city_gazetteer.canonical_city_name("Riadzie") == "Rijad"

    def test_invalid_database_pattern_is_skipped(self, monkeypatch):
        provide(monkeypatch, [GazetteerEntry("city", "Zlyland", ("zly(*", "zlyland*"))])
        assert city_gazetteer.canonical_city_name("Zlylandzie") == "Zlyland"

    def test_database_entry_cannot_remove_seed(self, monkeypatch):
        provide(monkeypatch, [GazetteerEntry("city", "Teksas", ("teksas*",))])
        assert city_gazetteer.canonical_city_name("Omdurmanie") == "Omdurman"

    def test_ambiguous_database_entry_resolves_to_nothing(self, monkeypatch):
        provide(monkeypatch, [GazetteerEntry("city", "Rijadia", ("riad*",))])
        assert city_gazetteer.canonical_city_name("Riadzie") is None


class TestGeocodeAliasMerge:
    def test_database_alias(self, monkeypatch):
        provide(monkeypatch, [GazetteerEntry("geocode_alias", "Nowa Nazwa", (), "New Name")])
        assert geocode_aliases.geocode_alias("nowa nazwa") == "New Name"

    def test_seed_has_priority(self, monkeypatch):
        provide(monkeypatch, [GazetteerEntry("geocode_alias", "Kaliningrad", (), "Other")])
        assert geocode_aliases.geocode_alias("Kaliningrad") == "Królewiec"

    def test_unknown_name_returns_none(self, monkeypatch):
        provide(monkeypatch, [])
        assert geocode_aliases.geocode_alias("Nigdzie") is None
