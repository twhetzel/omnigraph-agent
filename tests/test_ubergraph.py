"""Tests for Ubergraph discovery and config generation."""

import pytest
from unittest.mock import patch, MagicMock

from omnigraph_agent.context_builder.sources.ubergraph import (
    graph_uri_to_graph_id,
    obo_namespace_scope_from_graph_id,
    build_ubergraph_ontology_config,
    discover_named_graphs,
    ontology_url_to_graph_id,
    load_ontology_list,
    UBERGRAPH_GRAPHS_PREFIX,
    DEFAULT_UBERGRAPH_ENDPOINT,
)


class TestGraphUriToGraphId:
    def test_standard_ubergraph_uri(self):
        uri = "http://ubergraph.apps.renci.org/graphs/mondo"
        assert graph_uri_to_graph_id(uri) == "mondo"

    def test_go_uri(self):
        uri = "http://ubergraph.apps.renci.org/graphs/go"
        assert graph_uri_to_graph_id(uri) == "go"

    def test_lowercase(self):
        uri = "http://ubergraph.apps.renci.org/graphs/MONDO"
        assert graph_uri_to_graph_id(uri) == "mondo"

    def test_non_matching_prefix_returns_none(self):
        assert graph_uri_to_graph_id("http://other.org/graphs/mondo") is None

    def test_empty_suffix_returns_none(self):
        assert graph_uri_to_graph_id("http://ubergraph.apps.renci.org/graphs/") is None


class TestOboNamespaceScopeFromGraphId:
    def test_mondo(self):
        assert obo_namespace_scope_from_graph_id("mondo") == "http://purl.obolibrary.org/obo/MONDO_"

    def test_go(self):
        assert obo_namespace_scope_from_graph_id("go") == "http://purl.obolibrary.org/obo/GO_"

    def test_go_plus_takes_first_segment(self):
        assert obo_namespace_scope_from_graph_id("go-plus") == "http://purl.obolibrary.org/obo/GO_"


class TestBuildUbergraphOntologyConfig:
    def test_minimal_config_structure(self):
        cfg = build_ubergraph_ontology_config(
            "mondo",
            "http://ubergraph.apps.renci.org/graphs/mondo",
            "https://ubergraph.apps.renci.org/sparql",
        )
        assert cfg["graph_id"] == "mondo"
        assert cfg["endpoint"] == "https://ubergraph.apps.renci.org/sparql"
        assert cfg["named_graph"] == "http://ubergraph.apps.renci.org/graphs/mondo"
        assert cfg["namespace_scope"] == "http://purl.obolibrary.org/obo/MONDO_"
        assert "entity_types" in cfg
        assert "http://www.w3.org/2002/07/owl#Class" in cfg["entity_types"]
        assert cfg["dimensions"] == []
        assert cfg["repo_filter_property"] == "rdf:type"


class TestDiscoverNamedGraphs:
    @patch("omnigraph_agent.context_builder.sources.ubergraph.SPARQLWrapper")
    def test_parses_bindings_and_filters_by_prefix(self, mock_wrapper_cls):
        mock_wrapper = MagicMock()
        mock_wrapper_cls.return_value = mock_wrapper
        mock_wrapper.query.return_value.convert.return_value = {
            "results": {
                "bindings": [
                    {"g": {"value": "http://ubergraph.apps.renci.org/graphs/mondo"}},
                    {"g": {"value": "http://ubergraph.apps.renci.org/graphs/go"}},
                    {"g": {"value": "http://other.org/other"}},
                ]
            }
        }

        out = discover_named_graphs(
            "https://example.org/sparql",
            limit=10,
            uri_prefix=UBERGRAPH_GRAPHS_PREFIX,
        )
        assert out == [
            "http://ubergraph.apps.renci.org/graphs/go",
            "http://ubergraph.apps.renci.org/graphs/mondo",
        ]
        # other is dropped by prefix filter


class TestOntologyUrlToGraphId:
    def test_obo_subdir(self):
        assert ontology_url_to_graph_id("http://purl.obolibrary.org/obo/mondo/mondo-base.owl") == "mondo"
        assert ontology_url_to_graph_id("http://purl.obolibrary.org/obo/go/go-base.owl") == "go"
        assert ontology_url_to_graph_id("http://purl.obolibrary.org/obo/ro/ro-base.owl") == "ro"

    def test_obo_flat_owl(self):
        assert ontology_url_to_graph_id("http://purl.obolibrary.org/obo/chebi.owl.gz") == "chebi"
        assert ontology_url_to_graph_id("http://purl.obolibrary.org/obo/ncbitaxon.owl") == "ncbitaxon"

    def test_non_obo(self):
        assert ontology_url_to_graph_id("https://w3id.org/orcidio/orcidio.owl") == "orcidio"


class TestLoadOntologyList:
    def test_from_local_file(self, tmp_path):
        f = tmp_path / "ontologies.txt"
        f.write_text(
            "http://purl.obolibrary.org/obo/mondo/mondo-base.owl\n"
            "http://purl.obolibrary.org/obo/go/go-base.owl\n"
            "# comment\n"
            "http://purl.obolibrary.org/obo/mondo/mondo-base.owl\n"
        )
        out = load_ontology_list(str(f), dedupe=True)
        assert len(out) == 2  # mondo, go; duplicate mondo dropped
        gids = [g for g, _ in out]
        assert "mondo" in gids and "go" in gids
        assert out[0][1] == "http://ubergraph.apps.renci.org/graphs/mondo"
        assert out[1][1] == "http://ubergraph.apps.renci.org/graphs/go"
