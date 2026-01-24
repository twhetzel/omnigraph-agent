"""Tests for LLMContextEnricher."""

import pytest

from omnigraph_agent.context_builder.enrichers import LLMContextEnricher
from omnigraph_agent.context_builder.model.context_schema import (
    GlobalContext,
    QueryGenerationHints,
)


class TestInferGoodFor:
    def test_ontology_specific_go(self):
        enricher = LLMContextEnricher()
        out = enricher.infer_good_for("go")
        assert any("Gene function" in s for s in out)
        assert any("Biological process" in s for s in out)
        assert any("Cellular component" in s for s in out)

    def test_ontology_specific_mondo(self):
        enricher = LLMContextEnricher()
        out = enricher.infer_good_for("mondo")
        assert any("Disease name resolution" in s for s in out)
        assert any("Disease-phenotype" in s for s in out)

    def test_ontology_specific_case_insensitive(self):
        enricher = LLMContextEnricher()
        out_go = enricher.infer_good_for("GO")
        out_mondo = enricher.infer_good_for("MONDO")
        assert out_go == enricher.infer_good_for("go")
        assert out_mondo == enricher.infer_good_for("mondo")

    def test_domain_fallback(self):
        enricher = LLMContextEnricher()
        out = enricher.infer_good_for("unknown_ont", domain="phenotype and anatomy")
        assert "Phenotype description" in out or "Anatomical structure" in str(out)

    def test_generic_fallback(self):
        enricher = LLMContextEnricher()
        out = enricher.infer_good_for("xyz", domain=None)
        assert "Entity lookup" in out or "Hierarchy traversal" in out


class TestExtractQueryPatterns:
    def test_includes_namespace_pattern_when_scope_in_hints(self):
        enricher = LLMContextEnricher()
        hints = {
            "namespace_scope": 'FILTER STRSTARTS(STR(?class), "http://purl.obolibrary.org/obo/MONDO_")',
            "label_property": "rdfs:label",
        }
        out = enricher.extract_query_patterns("mondo", hints)
        names = [p.pattern for p in out]
        assert "Find all terms in namespace" in names
        assert "Find all child terms" in names
        assert "Find labels for a term" in names
        assert "Find cross-references to external databases" in names

    def test_includes_label_pattern_when_label_property_in_hints(self):
        enricher = LLMContextEnricher()
        hints = {"label_property": "rdfs:label"}
        out = enricher.extract_query_patterns("x", hints)
        label_p = next((p for p in out if "label" in p.pattern.lower()), None)
        assert label_p is not None
        assert "rdfs:label" in (label_p.sparql_hint or "")

    def test_hierarchy_pattern_has_property_path_note(self):
        enricher = LLMContextEnricher()
        out = enricher.extract_query_patterns("go", query_hints={})
        child = next((p for p in out if "child" in p.pattern.lower()), None)
        assert child is not None
        assert "subClassOf+" in (child.sparql_hint or "")
        assert "property path" in (child.note or "").lower() or "transitive" in (child.note or "").lower()


class TestDiscoverConnections:
    def test_returns_imports_from_obo_metadata(self):
        enricher = LLMContextEnricher()
        obo = {"imports": ["ro", "bfo"]}
        out = enricher.discover_connections("go", obo)
        ontologies = [c.ontology for c in out]
        assert "RO" in ontologies
        assert "BFO" in ontologies
        imp = next((c for c in out if c.ontology == "RO"), None)
        assert imp is not None
        assert imp.relationship_type == "direct import"

    def test_go_has_mondo_and_hp_connections(self):
        enricher = LLMContextEnricher()
        # obo_metadata must be truthy or we early-return; use {"imports": []} to exercise go-specific block
        out = enricher.discover_connections("go", obo_metadata={"imports": []})
        ontologies = [c.ontology for c in out]
        assert "MONDO" in ontologies
        assert "HP" in ontologies
        mondo = next((c for c in out if c.ontology == "MONDO"), None)
        assert mondo is not None
        assert "apoptosis" in (mondo.example_query or "").lower() or "gene" in (mondo.description or "").lower()

    def test_mondo_has_hp_and_go_connections(self):
        enricher = LLMContextEnricher()
        out = enricher.discover_connections("mondo", obo_metadata={"imports": []})
        ontologies = [c.ontology for c in out]
        assert "HP" in ontologies
        assert "GO" in ontologies
        hp = next((c for c in out if c.ontology == "HP"), None)
        assert hp is not None
        assert hp.relationship_type == "direct import"
        assert hp.typical_hop_count == 1

    def test_hp_has_mondo_connection(self):
        enricher = LLMContextEnricher()
        out = enricher.discover_connections("hp", obo_metadata={"imports": []})
        ontologies = [c.ontology for c in out]
        assert "MONDO" in ontologies

    def test_unknown_ontology_returns_only_imports(self):
        enricher = LLMContextEnricher()
        out = enricher.discover_connections("xyz", obo_metadata={"imports": ["foo"]})
        assert len(out) == 1
        assert out[0].ontology == "FOO"

    def test_none_obo_returns_empty(self):
        enricher = LLMContextEnricher()
        assert enricher.discover_connections("go", obo_metadata=None) == []


class TestEnrichContext:
    def test_sets_good_for_query_patterns_connects_to(self):
        enricher = LLMContextEnricher()
        ctx = GlobalContext(
            graph_id="mondo",
            endpoint="https://example.org/sparql",
            entity_types=[],
            dimensions=[],
            prefixes={},
            text_blurb="Monarch Disease Ontology",
            query_hints=QueryGenerationHints(
                namespace_scope='FILTER STRSTARTS(STR(?class), "http://purl.obolibrary.org/obo/MONDO_")',
                label_property="rdfs:label",
            ),
        )
        obo = {"domain": "disease", "imports": ["hp"]}
        out = enricher.enrich_context(ctx, obo)
        assert out.good_for is not None
        assert "Disease" in str(out.good_for)
        assert out.query_patterns is not None
        assert len(out.query_patterns) > 0
        assert out.connects_to is not None
        assert any(c.ontology == "HP" for c in out.connects_to)

    def test_domains_parsed_from_obo_domain_string(self):
        enricher = LLMContextEnricher()
        ctx = GlobalContext(
            graph_id="go",
            endpoint="https://example.org/sparql",
            entity_types=[],
            dimensions=[],
            prefixes={},
            query_hints=QueryGenerationHints(),
        )
        obo = {"domain": "biological_process, molecular_function"}
        out = enricher.enrich_context(ctx, obo)
        assert out.domains is not None
        assert "biological_process" in out.domains
        assert "molecular_function" in out.domains

    def test_handles_none_obo_metadata(self):
        enricher = LLMContextEnricher()
        ctx = GlobalContext(
            graph_id="go",
            endpoint="https://example.org/sparql",
            entity_types=[],
            dimensions=[],
            prefixes={},
        )
        out = enricher.enrich_context(ctx, obo_metadata=None)
        assert out.good_for is not None
        # discover_connections returns [] when obo_metadata is None, so connects_to is None
        assert out.query_patterns is not None
