"""
Load entity metadata from mcp-proto-okn-style CSV files.

CSV columns: URI, Label, Description, Type, EdgePropertyOf, SourceClass, TargetClass.
Type is one of: class, predicate, edgeproperty, nodeproperty.

Produces edge_properties and node_properties structures compatible with
mcp-proto-okn's get_schema() and RDF reification patterns, so omnigraph
context files are comparable to that MCP server's metadata.
"""

import csv
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import urlopen
from urllib.error import HTTPError, URLError


MCP_PROTO_OKN_ENTITIES_URL = (
    "https://raw.githubusercontent.com/sbl-sdsc/mcp-proto-okn/main/metadata/entities/{graph_id}_entities.csv"
)


def _generate_query_template(rel_label: str, source_class: str, target_class: str, prop_labels: List[str], kg_id: str) -> str:
    """Generate an RDF reification SPARQL template for a relationship with edge properties."""
    src = (source_class or "source").lower().replace(" ", "_")
    tgt = (target_class or "target").lower().replace(" ", "_")
    schema = f"https://purl.org/okn/frink/kg/{kg_id}/schema/"
    prop_selects = " ".join(f"?{pl}" for pl in prop_labels) if prop_labels else ""
    lines = [f"         schema:{pl} ?{pl} ;" for pl in prop_labels]
    if lines:
        lines[-1] = lines[-1].rstrip(" ;") + " ."
        prop_patterns = "\n".join(lines)
    else:
        prop_patterns = "."
    return f"""PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX schema: <{schema}>

SELECT ?{src} ?{tgt} {prop_selects}
WHERE {{
  ?stmt rdf:subject ?{src} ;
        rdf:predicate schema:{rel_label} ;
        rdf:object ?{tgt} ;
        {prop_patterns}
}}
LIMIT 10"""


def load_entities_csv(path_or_url: str, *, graph_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Load entity metadata from a local path or URL.

    Expects mcp-proto-okn-style CSV: URI, Label, Description, Type,
    EdgePropertyOf, SourceClass, TargetClass. Type in (class, predicate,
    edgeproperty, nodeproperty).

    Args:
        path_or_url: File path or URL to the CSV.
        graph_id: Used when generating query_template for edge_properties.
                  If None, a placeholder is used.

    Returns:
        Dict with 'edge_properties' and 'node_properties'. edge_properties
        is keyed by relationship short name; each value has uri, label,
        description, source_class, target_class, properties (list of
        {uri, label, description, type}), and query_template. node_properties
        is a list of {uri, label, description, type, class}.
        Returns None on 404, empty file, or parse error.
    """
    if path_or_url.startswith(("http://", "https://")):
        try:
            with urlopen(path_or_url, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, OSError, TypeError):
            return None
    else:
        p = Path(path_or_url)
        if not p.exists() or not p.is_file():
            return None
        content = p.read_text(encoding="utf-8", errors="replace")

    rows: List[Dict[str, str]] = []
    try:
        reader = csv.DictReader(StringIO(content))
        # Normalize column names (strip, handle BOM)
        raw_rows = list(reader)
        if not raw_rows:
            return None
        fieldnames = [f.strip().lstrip("\ufeff") for f in reader.fieldnames or []]
        for r in raw_rows:
            row = {}
            for k, v in r.items():
                nk = k.strip().lstrip("\ufeff") if k else ""
                if nk:
                    row[nk] = (v or "").strip()
            rows.append(row)
    except Exception:
        return None

    # Map expected names (allow case variants)
    def get(row: Dict, *candidates: str) -> str:
        for c in candidates:
            for k, v in row.items():
                if k and k.lower() == c.lower():
                    return (v or "").strip()
        return ""

    edge_properties: Dict[str, Any] = {}
    node_properties: List[Dict[str, Any]] = []

    # First pass: collect predicates (for source_class, target_class) and edgeproperty -> parent
    predicates: Dict[str, Dict[str, str]] = {}
    edge_children: Dict[str, List[Dict[str, Any]]] = {}

    for row in rows:
        uri = get(row, "URI")
        label = get(row, "Label")
        desc = get(row, "Description")
        typ = get(row, "Type").lower()
        edge_of = get(row, "EdgePropertyOf")
        src_cls = get(row, "SourceClass")
        tgt_cls = get(row, "TargetClass")

        if not uri:
            continue

        if typ == "predicate":
            short = uri.split("/")[-1] if "/" in uri else uri.split("#")[-1] if "#" in uri else label or uri
            predicates[short] = {"uri": uri, "label": label, "description": desc, "source_class": src_cls, "target_class": tgt_cls}

        elif typ == "edgeproperty":
            for parent in [p.strip() for p in edge_of.split(";") if p.strip()]:
                if parent not in edge_children:
                    edge_children[parent] = []
                edge_children[parent].append({"uri": uri, "label": label, "description": desc, "type": typ})

        elif typ == "nodeproperty":
            node_properties.append({"uri": uri, "label": label, "description": desc, "type": typ, "class": src_cls})

    # Build edge_properties: each parent (relationship) with its edgeproperty list and predicate metadata
    for rel_label, props in edge_children.items():
        pred = predicates.get(rel_label, {})
        prop_labels = [p.get("label") or p.get("uri", "").split("/")[-1].split("#")[-1] for p in props]
        edge_properties[rel_label] = {
            "uri": pred.get("uri"),
            "label": rel_label,
            "description": pred.get("description", ""),
            "source_class": pred.get("source_class", ""),
            "target_class": pred.get("target_class", ""),
            "properties": props,
            "query_template": _generate_query_template(rel_label, pred.get("source_class"), pred.get("target_class"), prop_labels, graph_id or "kg"),
        }

    return {"edge_properties": edge_properties, "node_properties": node_properties}


def fetch_entities_from_mcp_proto_okn(graph_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch and parse the mcp-proto-okn entities CSV for a graph.

    Args:
        graph_id: KG shortname (e.g. 'nde', 'spoke-genelab').

    Returns:
        Same structure as load_entities_csv, or None if the file does not
        exist or cannot be parsed.
    """
    url = MCP_PROTO_OKN_ENTITIES_URL.format(graph_id=graph_id)
    return load_entities_csv(url, graph_id=graph_id)
