"""
Extract canonical herb_id + Korean name from monograph *.cypher.txt headers,
and herb names from generated price MERGE cypher.
"""

import re
from pathlib import Path
from typing import Iterable

_HERB_ID_LINE = re.compile(r"//\s*herb_id\s*\([^)]*\)\s*:\s*(H_[\w]+)\s*(?:\r?\n|$)", re.MULTILINE)
_HERB_NAME_LINE = re.compile(
    r"//\s*herb_name\s*\([^)]*\)\s*:\s*([^\r\n]+?)\s*(?:\r?\n|$)",
    re.MULTILINE,
)
_MERGE_HERB = re.compile(r"MERGE\s*\(h:Herb\s*\{\s*name:\s*'([^']*)'\s*\}\)")


def load_monograph_herb_entries(monograph_root: Path) -> list[tuple[str, str]]:
    """
    Returns list of (herb_name, herb_id) from vol**/*.cypher.txt comment headers.
    """
    out: list[tuple[str, str]] = []
    for path in sorted(monograph_root.rglob("*.cypher.txt")):
        text = path.read_text(encoding="utf-8", errors="replace")
        m_id = _HERB_ID_LINE.search(text)
        m_name = _HERB_NAME_LINE.search(text)
        if m_id and m_name:
            out.append((m_name.group(1).strip(), m_id.group(1).strip()))
    return out


def load_price_cypher_herb_names(cypher_file: Path) -> set[str]:
    """All MERGE (h:Herb {name: '...'}) names from herb_prices_from_csv.cypher."""
    if not cypher_file.is_file():
        return set()
    text = cypher_file.read_text(encoding="utf-8", errors="replace")
    return set(_MERGE_HERB.findall(text))


def monograph_name_to_id_map(entries: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {name: hid for name, hid in entries}
