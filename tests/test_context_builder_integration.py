"""Integration tests for context builder: full build with YAML and LLM metadata.

These tests run a full build (SPARQL introspection, OBO Foundry fetch) and assert
that the output YAML contains good_for and connects_to. They require network
access to Ubergraph and OBO Foundry. Skip with: pytest -m 'not integration'
"""

import pytest
import yaml
from pathlib import Path

from omnigraph_agent.context_builder.builder import ContextBuilder


@pytest.mark.integration
class TestBuildMondoYAMLGoodForConnectsTo:
    """Build mondo --format yaml and verify good_for and connects_to are present."""

    def test_build_mondo_yaml_has_good_for_and_connects_to(self, tmp_path):
        builder = ContextBuilder("mondo", tmp_path, output_format="yaml")
        files = builder.build()
        assert "global" in files
        yaml_path = files["global"]
        assert yaml_path.suffix in (".yaml", ".yml")
        assert yaml_path.exists()

        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        assert "good_for" in data, "good_for must be present after LLM enrichment"
        good_for = data["good_for"]
        assert isinstance(good_for, list) and len(good_for) > 0
        assert any("Disease" in s or "disease" in s for s in good_for), (
            "good_for for MONDO should mention disease-related use cases"
        )

        assert "connects_to" in data, "connects_to must be present after LLM enrichment"
        connects = data["connects_to"]
        assert isinstance(connects, list)
        ontologies = [c.get("ontology") for c in connects if isinstance(c, dict)]
        assert "HP" in ontologies or "GO" in ontologies, (
            "MONDO should connect to HP and/or GO"
        )

        # Sanity: graph_id and endpoint
        assert data.get("graph_id") == "mondo"
        assert "endpoint" in data and "ubergraph" in data.get("endpoint", "").lower()
