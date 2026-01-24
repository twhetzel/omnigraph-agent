"""
Discover named graphs from the Ubergraph SPARQL endpoint and build minimal
ontology configs for context generation.

Ubergraph graph URIs follow: http://ubergraph.apps.renci.org/graphs/{graph_id}

Alternatively, ontology IDs can be derived from Ubergraph's ontologies.txt:
https://github.com/INCATools/ubergraph/blob/master/ontologies.txt
"""

import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from SPARQLWrapper import SPARQLWrapper, JSON


DEFAULT_UBERGRAPH_ENDPOINT = "https://ubergraph.apps.renci.org/sparql"
UBERGRAPH_GRAPHS_PREFIX = "http://ubergraph.apps.renci.org/graphs/"
# Some endpoints may return https for graph URIs
UBERGRAPH_GRAPHS_PREFIX_HTTPS = "https://ubergraph.apps.renci.org/graphs/"

ONTOLOGIES_TXT_URL = "https://raw.githubusercontent.com/INCATools/ubergraph/master/ontologies.txt"


def ontology_url_to_graph_id(url: str) -> str:
    """
    Derive a Ubergraph graph_id from an ontology OWL URL (e.g. from ontologies.txt).

    - OBO: .../obo/{id}/... or .../obo/{id}.owl(.gz) -> id (e.g. mondo, go, chebi).
    - Other: last path segment, minus .owl/.owl.gz/-base -> e.g. orcidio, mbao.
    """
    path = urlparse(url.strip()).path
    parts = [p for p in path.split("/") if p]
    if "obo" in parts:
        idx = parts.index("obo")
        if idx + 1 < len(parts):
            seg = parts[idx + 1]
            for suffix in (".owl.gz", ".owl", ".gz"):
                if seg.endswith(suffix):
                    seg = seg[: -len(suffix)]
                    break
            return seg.lower()
    if not parts:
        return "unknown"
    seg = parts[-1]
    for suffix in (".owl.gz", ".owl", ".gz"):
        if seg.endswith(suffix):
            seg = seg[: -len(suffix)]
            break
    if seg.endswith("-base"):
        seg = seg[:-5]
    return seg.lower()


def fetch_ontologies_txt(url: str = ONTOLOGIES_TXT_URL) -> List[str]:
    """Fetch ontologies.txt from URL and return non-empty, non-comment lines (ontology URLs)."""
    from urllib.request import urlopen

    with urlopen(url) as resp:
        raw = resp.read().decode("utf-8")
    return [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def load_ontology_list(
    url_or_path: str,
    *,
    dedupe: bool = True,
) -> List[Tuple[str, str]]:
    """
    Load ontology URLs from a URL or local file and derive (graph_id, named_graph_uri).

    Args:
        url_or_path: URL (http/https) to fetch, or local file path.
        dedupe: If True, keep first occurrence of each graph_id.

    Returns:
        List of (graph_id, named_graph_uri) with named_graph_uri =
        http://ubergraph.apps.renci.org/graphs/{graph_id}.
    """
    if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        lines = fetch_ontologies_txt(url_or_path)
    else:
        with open(url_or_path, "r") as f:
            lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    seen: set = set()
    out: List[Tuple[str, str]] = []
    for line in lines:
        gid = ontology_url_to_graph_id(line)
        if not gid or gid == "unknown":
            continue
        if dedupe and gid in seen:
            continue
        seen.add(gid)
        named = f"{UBERGRAPH_GRAPHS_PREFIX}{gid}"
        out.append((gid, named))
    return out


def discover_named_graphs(
    endpoint: str = DEFAULT_UBERGRAPH_ENDPOINT,
    *,
    limit: Optional[int] = 2000,
    uri_prefix: str = UBERGRAPH_GRAPHS_PREFIX,
) -> List[str]:
    """
    Discover named graph URIs from the endpoint.

    Args:
        endpoint: SPARQL endpoint URL
        limit: Max number of graphs to return; None for no limit
        uri_prefix: Only include graphs whose URI starts with this (e.g. Ubergraph /graphs/)

    Returns:
        List of named graph URIs matching uri_prefix
    """
    # Use a simple GRAPH pattern; filter by uri_prefix in Python.
    # An in-SPARQL FILTER(STRSTARTS(STR(?g), ...)) can trigger timeouts on
    # Ubergraph (the store may need to evaluate many ?g before finding
    # matches). We fetch a batch and filter client-side.
    query = """
    SELECT DISTINCT ?g WHERE {
        GRAPH ?g {
            ?s ?p ?o .
        }
    }
    """
    if limit is not None:
        query += f"\n    LIMIT {limit}"

    sparql = SPARQLWrapper(endpoint)
    sparql.setReturnFormat(JSON)
    sparql.setQuery(query)

    graphs: List[str] = []
    try:
        results = sparql.query().convert()
        for b in results.get("results", {}).get("bindings", []):
            g = b.get("g", {}).get("value", "")
            if not g:
                continue
            if uri_prefix:
                ok = g.startswith(uri_prefix) or (
                    uri_prefix == UBERGRAPH_GRAPHS_PREFIX
                    and g.startswith(UBERGRAPH_GRAPHS_PREFIX_HTTPS)
                )
                if not ok:
                    continue
            graphs.append(g)
    except Exception as e:
        raise RuntimeError(f"Failed to discover named graphs from {endpoint}: {e}") from e

    return sorted(graphs)


def graph_uri_to_graph_id(uri: str, uri_prefix: str = UBERGRAPH_GRAPHS_PREFIX) -> Optional[str]:
    """
    Extract graph_id from a Ubergraph-style graph URI.

    Examples:
        http://ubergraph.apps.renci.org/graphs/mondo -> mondo
        https://ubergraph.apps.renci.org/graphs/go -> go

    Args:
        uri: Full graph URI
        uri_prefix: Prefix to strip (e.g. Ubergraph /graphs/ base)

    Returns:
        Trailing segment (graph_id) or None if URI does not match
    """
    to_strip = None
    if uri.startswith(UBERGRAPH_GRAPHS_PREFIX_HTTPS):
        to_strip = UBERGRAPH_GRAPHS_PREFIX_HTTPS
    elif uri.startswith(UBERGRAPH_GRAPHS_PREFIX):
        to_strip = UBERGRAPH_GRAPHS_PREFIX
    elif uri.startswith(uri_prefix):
        to_strip = uri_prefix
    if to_strip is None:
        return None
    suffix = uri[len(to_strip) :].strip("/")
    if not suffix:
        return None
    # take the first path segment if there were extra slashes
    return suffix.split("/")[0].lower()


def obo_namespace_scope_from_graph_id(graph_id: str) -> str:
    """
    Heuristic OBO namespace IRI from graph_id.

    OBO IRIs are http://purl.obolibrary.org/obo/PREFIX_ (e.g. MONDO_, GO_).
    We use the graph_id with common normalizations: uppercase, take the
    first part before '-' (e.g. go-plus -> GO).

    Args:
        graph_id: e.g. mondo, go, go-plus, hp

    Returns:
        e.g. http://purl.obolibrary.org/obo/MONDO_
    """
    base = (graph_id.split("-")[0] or graph_id).upper()
    # sanitize: only alphanumeric and underscore
    base = re.sub(r"[^A-Z0-9_]", "", base) or graph_id.upper()
    return f"http://purl.obolibrary.org/obo/{base}_"


def build_ubergraph_ontology_config(
    graph_id: str,
    named_graph_uri: str,
    endpoint: str = DEFAULT_UBERGRAPH_ENDPOINT,
) -> dict:
    """
    Build a minimal ontology config for a Ubergraph named graph.

    Suitable for GenericOntologyGraph(config=...). The builder will use
    named_graph for FROM and namespace_scope for FILTERs when appropriate.

    Args:
        graph_id: e.g. mondo, go
        named_graph_uri: Full graph URI (e.g. http://ubergraph.apps.renci.org/graphs/mondo)
        endpoint: SPARQL endpoint

    Returns:
        Config dict compatible with BaseGraph / GenericOntologyGraph
    """
    namespace_scope = obo_namespace_scope_from_graph_id(graph_id)
    return {
        "graph_id": graph_id,
        "endpoint": endpoint,
        "repo_filter_property": "rdf:type",  # placeholder; ontologies do not use repo filters
        "named_graph": named_graph_uri,
        "namespace_scope": namespace_scope,
        "entity_types": ["http://www.w3.org/2002/07/owl#Class"],
        "dimensions": [],
        "text_blurb": f"Ontology {graph_id} from Ubergraph.",
    }
