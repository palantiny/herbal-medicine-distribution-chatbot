from pathlib import Path
from textwrap import dedent

from palantiny.data_sync.manifest import load_monograph_herb_entries, load_price_cypher_herb_names
from palantiny.data_sync.reconcile import reconcile_sets


def test_load_price_cypher_herb_names(tmp_path: Path):
    p = tmp_path / "x.cypher"
    p.write_text(
        "MERGE (h:Herb {name: '감초'})\nMERGE (h:Herb {name: '대추'})\n",
        encoding="utf-8",
    )
    names = load_price_cypher_herb_names(p)
    assert names == {"감초", "대추"}


def test_load_monograph_herb_entries(tmp_path: Path):
    vol = tmp_path / "vol01"
    vol.mkdir()
    f = vol / "stub_herb.cypher.txt"
    f.write_text(
        dedent(
            """\
            // auto-generated
            // herb_name (MERGE key): StubHerb
            // herb_id (attr): H_010
            MERGE (h:Herb {name: 'StubHerb'})
            """
        ),
        encoding="utf-8",
    )
    entries = load_monograph_herb_entries(tmp_path)
    assert entries == [("StubHerb", "H_010")]


def test_reconcile_sets():
    r = reconcile_sets({"a", "b"}, {"b", "c"})
    assert r.both_names == frozenset({"b"})
    assert r.monograph_only_names == frozenset({"a"})
    assert r.price_only_names == frozenset({"c"})
