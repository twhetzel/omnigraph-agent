"""Tests for YAMLContextWriter."""

import pytest
import yaml
from pathlib import Path

from omnigraph_agent.context_builder.writers import YAMLContextWriter
from omnigraph_agent.context_builder.model.context_schema import GlobalContext, QueryGenerationHints


class TestYAMLContextWriter:
    """Tests for YAMLContextWriter.write."""

    def test_writes_dict_to_yaml(self, tmp_path):
        writer = YAMLContextWriter()
        data = {"graph_id": "go", "endpoint": "https://example.org/sparql", "entity_types": ["owl:Class"]}
        out = tmp_path / "context.yaml"
        result = writer.write(data, out)
        assert result == out
        assert out.exists()
        with open(out) as f:
            loaded = yaml.safe_load(f)
        assert loaded["graph_id"] == "go"
        assert loaded["endpoint"] == "https://example.org/sparql"
        assert loaded["entity_types"] == ["owl:Class"]

    def test_writes_pydantic_model_to_yaml(self, tmp_path):
        writer = YAMLContextWriter()
        ctx = GlobalContext(
            graph_id="mondo",
            endpoint="https://ubergraph.apps.renci.org/sparql",
            entity_types=["http://www.w3.org/2002/07/owl#Class"],
            dimensions=[],
            prefixes={"rdfs": "http://www.w3.org/2000/01/rdf-schema#"},
            text_blurb="Monarch Disease Ontology",
            query_hints=QueryGenerationHints(namespace_scope='FILTER STRSTARTS(STR(?class), "http://purl.obolibrary.org/obo/MONDO_")'),
        )
        out = tmp_path / "mondo_global.yaml"
        result = writer.write(ctx, out)
        assert result == out
        with open(out) as f:
            loaded = yaml.safe_load(f)
        assert loaded["graph_id"] == "mondo"
        assert loaded["text_blurb"] == "Monarch Disease Ontology"
        assert "query_hints" in loaded
        assert "namespace_scope" in loaded["query_hints"]

    def test_exclude_none_on_model(self, tmp_path):
        writer = YAMLContextWriter()
        ctx = GlobalContext(
            graph_id="hp",
            endpoint="https://example.org/sparql",
            entity_types=[],
            dimensions=[],
            prefixes={},
            good_for=["Phenotype description"],
        )
        out = tmp_path / "hp.yaml"
        writer.write(ctx, out)
        with open(out) as f:
            loaded = yaml.safe_load(f)
        assert "good_for" in loaded
        assert loaded["good_for"] == ["Phenotype description"]
        # optional unset fields should be omitted (exclude_none)
        assert "query_hints" not in loaded or loaded.get("query_hints") is None

    def test_creates_parent_dirs(self, tmp_path):
        writer = YAMLContextWriter()
        out = tmp_path / "sub" / "dir" / "ctx.yaml"
        writer.write({"graph_id": "x"}, out)
        assert out.exists()
        assert out.parent.exists()

    def test_roundtrip_preserves_structure(self, tmp_path):
        writer = YAMLContextWriter()
        data = {
            "graph_id": "go",
            "good_for": ["Gene function annotation", "Pathway analysis"],
            "connects_to": [
                {"ontology": "MONDO", "relationship_type": "indirect via genes", "typical_hop_count": 2},
            ],
        }
        out = tmp_path / "roundtrip.yaml"
        writer.write(data, out)
        with open(out) as f:
            back = yaml.safe_load(f)
        assert back["graph_id"] == data["graph_id"]
        assert back["good_for"] == data["good_for"]
        assert len(back["connects_to"]) == 1
        assert back["connects_to"][0]["ontology"] == "MONDO"
        assert back["connects_to"][0]["typical_hop_count"] == 2
