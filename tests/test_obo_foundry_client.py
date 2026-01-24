"""Tests for OBOfoundryClient."""

import pytest
from pathlib import Path
from unittest.mock import patch

from omnigraph_agent.context_builder.sources.obo_foundry_client import OBOfoundryClient


# Minimal OBO Foundry–style registry for tests
def _make_registry(ontologies):
    return {"ontologies": ontologies}


class TestNormalizeOntologyId:
    def test_lowercase(self):
        client = OBOfoundryClient(cache_dir=Path("/tmp/empty"))
        assert client._normalize_ontology_id("go") == "go"
        assert client._normalize_ontology_id("mondo") == "mondo"

    def test_uppercase(self):
        client = OBOfoundryClient(cache_dir=Path("/tmp/empty"))
        assert client._normalize_ontology_id("GO") == "go"
        assert client._normalize_ontology_id("MONDO") == "mondo"

    def test_strips_whitespace(self):
        client = OBOfoundryClient(cache_dir=Path("/tmp/empty"))
        assert client._normalize_ontology_id("  go  ") == "go"


class TestGetOntologyMetadata:
    @patch.object(OBOfoundryClient, "_load_registry")
    def test_returns_metadata_for_known_ontology(self, mock_load):
        mock_load.return_value = _make_registry([
            {
                "id": "go",
                "title": "Gene Ontology",
                "description": "A framework for gene product function.",
                "homepage": "http://geneontology.org/",
                "license": {"label": "CC BY 4.0"},
                "contact": {"label": "go-discuss@geneontology.org"},
                "domain": "biological systems",
                "products": [{"id": "go.owl"}],
                "dependencies": [{"id": "ro", "type": "imports"}],
            },
        ])
        client = OBOfoundryClient(cache_dir=Path("/tmp/empty"))
        meta = client.get_ontology_metadata("go")
        assert meta is not None
        assert meta["id"] == "go"
        assert meta["title"] == "Gene Ontology"
        assert meta["description"] == "A framework for gene product function."
        assert meta["homepage"] == "http://geneontology.org/"
        assert meta["license"] == "CC BY 4.0"
        assert meta["domain"] == "biological systems"
        assert "ro" in (meta.get("imports") or [])

    @patch.object(OBOfoundryClient, "_load_registry")
    def test_returns_none_for_unknown_ontology(self, mock_load):
        mock_load.return_value = _make_registry([{"id": "go", "title": "Gene Ontology"}])
        client = OBOfoundryClient(cache_dir=Path("/tmp/empty"))
        assert client.get_ontology_metadata("unknown_ont") is None

    @patch.object(OBOfoundryClient, "_load_registry")
    def test_case_insensitive_match(self, mock_load):
        mock_load.return_value = _make_registry([{"id": "go", "title": "Gene Ontology"}])
        client = OBOfoundryClient(cache_dir=Path("/tmp/empty"))
        m1 = client.get_ontology_metadata("GO")
        m2 = client.get_ontology_metadata("go")
        assert m1 is not None and m2 is not None
        assert m1["id"] == m2["id"]

    @patch.object(OBOfoundryClient, "_load_registry")
    def test_caches_result(self, mock_load):
        mock_load.return_value = _make_registry([{"id": "go", "title": "Gene Ontology"}])
        client = OBOfoundryClient(cache_dir=Path("/tmp/empty"))
        client.get_ontology_metadata("go")
        client.get_ontology_metadata("go")
        assert mock_load.call_count == 1

    @patch.object(OBOfoundryClient, "_load_registry")
    def test_empty_registry_returns_none(self, mock_load):
        mock_load.return_value = {}
        client = OBOfoundryClient(cache_dir=Path("/tmp/empty"))
        assert client.get_ontology_metadata("go") is None

    @patch.object(OBOfoundryClient, "_load_registry")
    def test_none_registry_returns_none(self, mock_load):
        mock_load.return_value = None
        client = OBOfoundryClient(cache_dir=Path("/tmp/empty"))
        assert client.get_ontology_metadata("go") is None


class TestIsCacheValid:
    def test_missing_file_invalid(self, tmp_path):
        client = OBOfoundryClient(cache_dir=tmp_path)
        client.registry_file = tmp_path / "nonexistent.yml"
        assert client._is_cache_valid() is False

    def test_fresh_file_valid(self, tmp_path):
        client = OBOfoundryClient(cache_dir=tmp_path)
        client.registry_file = tmp_path / "ontologies.yml"
        client.registry_file.write_text("ontologies: []")
        assert client._is_cache_valid() is True


class TestInit:
    def test_creates_cache_dir_and_sets_registry_file(self, tmp_path):
        d = tmp_path / "obo_cache"
        client = OBOfoundryClient(cache_dir=d)
        assert d.exists()
        assert client.registry_file == d / "ontologies.yml"
