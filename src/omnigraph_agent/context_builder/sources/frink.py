"""
Discover knowledge graphs from the FRINK registry and build minimal configs
for context generation.

FRINK (https://frink.renci.org/registry/) hosts many OKN knowledge graphs.
Endpoint convention for FRINK-hosted graphs: https://frink.apps.renci.org/{shortname}/sparql

Design allows adding other knowledge-graph registries later (e.g. a custom
YAML/JSON list or another API) by implementing the same interface:
  get_graph_list() -> List[Tuple[str, str]]
  build_kg_config(graph_id, endpoint, **overrides) -> dict
"""

from typing import List, Tuple, Dict, Any, Optional

FRINK_BASE = "https://frink.apps.renci.org"

# Knowledge graph shortnames from the FRINK registry (https://frink.renci.org/registry/)
# plus nde. Excludes ontologies that are built from Ubergraph (mondo, go, etc.).
FRINK_GRAPH_IDS = [
    "nde",
    "biobricks-aopwiki",
    "biobricks-ice",
    "biobricks-mesh",
    "biobricks-pubchem-annotations",
    "biobricks-tox21",
    "biobricks-toxcast",
    "biohealth",
    "climatemodelskg",
    "dreamkg",
    "fiokg",
    "gene-expression-atlas-okn",
    "geoconnex",
    "hydrologykg",
    "identifier-mappings",
    "nasa-gesdisc-kg",
    "nikg",
    "prokn",
    "ruralkg",
    "sawgraph",
    "scales",
    "securechainkg",
    "semopenalex",
    "sockg",
    "spatialkg",
    "spoke-genelab",
    "spoke-okn",
    "sudokn",
    "ubergraph",
    "ufokn",
    "wikidata",
    "wildlifekn",
]

# Endpoint overrides for graphs not hosted at frink.apps.renci.org/{id}/sparql
ENDPOINT_OVERRIDES: Dict[str, str] = {
    "wikidata": "https://query.wikidata.org/sparql",
}


def get_frink_graph_list(limit: Optional[int] = None) -> List[Tuple[str, str]]:
    """
    Return (graph_id, endpoint) for each FRINK registry knowledge graph.

    Args:
        limit: Max number to return; None for all.

    Returns:
        List of (graph_id, endpoint) tuples.
    """
    out: List[Tuple[str, str]] = []
    for gid in FRINK_GRAPH_IDS:
        endpoint = ENDPOINT_OVERRIDES.get(gid) or f"{FRINK_BASE}/{gid}/sparql"
        out.append((gid, endpoint))
        if limit is not None and len(out) >= limit:
            break
    return out


def build_frink_kg_config(
    graph_id: str,
    endpoint: str,
    *,
    repo_filter_property: str = "",
    entity_types: Optional[List[str]] = None,
    dimensions: Optional[List[Dict[str, Any]]] = None,
    text_blurb: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a minimal knowledge-graph config for ContextBuilder.

    Used for FRINK registry graphs and can be reused for other KG registries.
    When entity_types/dimensions are empty, introspection will discover them.

    Args:
        graph_id: Shortname (e.g. 'nde', 'spoke-okn')
        endpoint: SPARQL endpoint URL
        repo_filter_property: Property linking entities to catalogs; "" for single-source
        entity_types: Optional; default [] (introspection)
        dimensions: Optional; default [] (introspection)
        text_blurb: Optional; default describes FRINK registry

    Returns:
        Config dict for GenericGraph / ContextBuilder
    """
    if entity_types is None:
        entity_types = []
    if dimensions is None:
        dimensions = []
    if text_blurb is None:
        text_blurb = f"Knowledge graph {graph_id} from the FRINK registry (https://frink.renci.org/registry/)."

    return {
        "graph_id": graph_id,
        "endpoint": endpoint,
        "repo_filter_property": repo_filter_property,
        "entity_types": entity_types,
        "dimensions": dimensions,
        "text_blurb": text_blurb,
        "graph_type": "knowledge_graph",
    }
