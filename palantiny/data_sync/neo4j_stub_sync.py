"""
Write or execute MERGE statements for CSV-only herbs (names in price graph, not in monograph).

herb_id assignment: synthetic `H_CSV_{slug}` when no monograph id exists (stable per name).
"""

import hashlib
from pathlib import Path
from typing import Iterable

from palantiny.layer2_graph.stub_herbs import build_stub_herb_cypher


def synthetic_herb_id_for_csv_only(herb_name: str) -> str:
    h = hashlib.sha256(herb_name.encode("utf-8")).hexdigest()[:8].upper()
    return f"H_CSV_{h}"


def build_stub_cypher_document(
    csv_only_herb_names: Iterable[str],
    name_to_id: dict[str, str] | None = None,
) -> str:
    """
    name_to_id: optional map from Korean name → canonical H_XXX when known (e.g. from monograph).
    For names not in map, use synthetic_herb_id_for_csv_only.
    """
    name_to_id = name_to_id or {}
    lines = ["// Auto-generated: CSV-only herb stubs for Neo4j\n"]
    for name in sorted(set(csv_only_herb_names)):
        hid = name_to_id.get(name) or synthetic_herb_id_for_csv_only(name)
        lines.append(f"// stub: {name} -> {hid}\n")
        lines.append(build_stub_herb_cypher(name, hid))
        lines.append("\n")
    return "".join(lines)


def write_stub_cypher_file(
    csv_only_herb_names: Iterable[str],
    output_path: Path,
    name_to_id: dict[str, str] | None = None,
) -> int:
    doc = build_stub_cypher_document(csv_only_herb_names, name_to_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(doc, encoding="utf-8")
    return len(set(csv_only_herb_names))
