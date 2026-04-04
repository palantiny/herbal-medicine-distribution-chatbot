"""
CSV-only herbs: MERGE minimal :Herb nodes so GraphRAG / name lookup can reach them.

`monograph_loaded=false` distinguishes stubs from monograph-rich nodes.
`stub_embedding_text` is for future vector upsert pipelines.
"""

def escape_cypher_string(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace("'", "\\'")


def stub_embedding_blurb(herb_name: str, herb_id: str) -> str:
    return (
        f"{herb_name} ({herb_id}) — 이 한약재는 가격·유통 DB(CSV/PostgreSQL)에 등록되어 있으나 "
        "모노그래프 기반 상세 온톨로지는 없거나 최소 노드(stub)로만 그래프에 존재합니다."
    )


def build_stub_herb_cypher(herb_name: str, herb_id: str) -> str:
    n = escape_cypher_string(herb_name)
    hid = escape_cypher_string(herb_id)
    blur = escape_cypher_string(stub_embedding_blurb(herb_name, herb_id))
    return (
        f"MERGE (h:Herb {{name: '{n}'}})\n"
        f"ON CREATE SET h.herb_id = '{hid}', h.monograph_loaded = false, "
        f"h.data_source = 'csv_only_stub', h.stub_embedding_text = '{blur}'\n"
        f"ON MATCH SET h.herb_id = coalesce(h.herb_id, '{hid}'), "
        f"h.stub_embedding_text = coalesce(h.stub_embedding_text, '{blur}')\n"
        f";\n"
    )
