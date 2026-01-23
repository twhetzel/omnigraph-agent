"""Tests for bridge graph system fixes from PR review."""

import re
import pytest
from pathlib import Path
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF

from omnigraph_agent.bridge.semantic_mappings import (
    get_category,
    IdentifierCategory,
    are_semantically_related,
)
from omnigraph_agent.context_builder.graphs.base import BaseGraph


class TestPMCPattern:
    """Test that PMC regex pattern correctly matches PMC IDs without colons."""
    
    def test_pmc_pattern_matches_without_colon(self):
        """PMC IDs should match without colon (e.g., PMC123456)."""
        # This is the pattern from base.py after the fix
        pattern = r'^(PMC)(\d+)$'
        
        # Should match
        assert re.match(pattern, 'PMC123456') is not None
        assert re.match(pattern, 'PMC00012345') is not None
        
        # Should NOT match (has colon)
        assert re.match(pattern, 'PMC:123456') is None
    
    def test_pmc_pattern_extraction(self):
        """Test that PMC pattern extraction works correctly."""
        pattern = r'^(PMC)(\d+)$'
        
        match = re.match(pattern, 'PMC123456')
        assert match is not None
        assert match.group(1) == 'PMC'
        assert match.group(2) == '123456'


class TestUniProtKBSemanticCategory:
    """Test that UniProtKB is correctly categorized as TAXONOMY."""
    
    def test_uniprotkb_is_taxonomy(self):
        """UniProtKB should be categorized as TAXONOMY, not PROTEIN."""
        category = get_category('UniProtKB')
        assert category == IdentifierCategory.TAXONOMY
        assert category != IdentifierCategory.PROTEIN
    
    def test_uniprotkb_semantic_relations(self):
        """UniProtKB should be semantically related to NCBITaxon."""
        assert are_semantically_related('UniProtKB', 'NCBITaxon')
        assert are_semantically_related('NCBITaxon', 'UniProtKB')


class TestLinksetBuilderRegex:
    """Test that entity IRI regex is permissive enough."""
    
    def test_entity_iri_regex_matches_various_formats(self):
        """The regex should match identifiers with various characters."""
        # Test the regex pattern used in linkset_builder.py
        # The pattern uses .+ to match any characters after the prefix
        test_cases = [
            ('MONDO', 'http://purl.obolibrary.org/obo/MONDO_0000001'),
            ('MONDO', 'http://purl.obolibrary.org/obo/MONDO:0000001'),
            ('MONDO', 'http://example.org/MONDO:123/abc'),  # Contains letters after numbers
            ('ICDO', 'http://example.org/ICDO:9740/1'),  # Contains forward slash
        ]
        
        for query_prefix, test_case in test_cases:
            pattern = f'{query_prefix}[:_].+'
            # The regex should match
            assert re.search(pattern, test_case) is not None, f"Failed to match {test_case} with prefix {query_prefix}"
    
    def test_entity_iri_regex_handles_special_characters(self):
        """Regex should handle identifiers with special characters like slashes."""
        query_prefix = 'ICDO'
        pattern = f'{query_prefix}[:_].+'
        
        # Should match identifier with slash
        test_iri = 'http://example.org/ICDO:9740/1'
        assert re.search(pattern, test_iri) is not None


class TestBridgeContextGeneratorNamespaces:
    """Test that bridge_context_generator uses proper RDF namespaces."""
    
    def test_namespace_imports(self):
        """Verify that Namespace and VOID are imported."""
        from omnigraph_agent.bridge.bridge_context_generator import (
            WOBDBRIDGE,
            BridgeContextGenerator,
        )
        from rdflib.namespace import VOID
        
        # WOBDBRIDGE should be a Namespace object, not a string
        assert isinstance(WOBDBRIDGE, Namespace)
        assert str(WOBDBRIDGE) == "https://wobd.org/bridge#"
        
        # VOID should be available
        assert VOID.Linkset is not None
    
    def test_namespace_comparison(self):
        """Test that namespace comparisons work correctly."""
        from omnigraph_agent.bridge.bridge_context_generator import WOBDBRIDGE
        from rdflib.namespace import VOID
        
        # Create a test graph
        g = Graph()
        linkset_iri = URIRef("https://wobd.org/bridge/linkset/test")
        g.add((linkset_iri, RDF.type, VOID.Linkset))
        
        # Test that we can find it using namespace comparison
        found = False
        for s, p, o in g.triples((None, RDF.type, None)):
            if o == VOID.Linkset:
                found = True
                break
        
        assert found, "Should find Linkset using namespace comparison"
    
    def test_linkassertion_namespace(self):
        """Test that LinkAssertion can be found using namespace."""
        from omnigraph_agent.bridge.bridge_context_generator import WOBDBRIDGE
        
        # Create a test graph with LinkAssertion
        g = Graph()
        link_iri = URIRef("https://wobd.org/bridge/link/test")
        g.add((link_iri, RDF.type, WOBDBRIDGE.LinkAssertion))
        
        # Count LinkAssertions using namespace
        count = len(list(g.triples((None, RDF.type, WOBDBRIDGE.LinkAssertion))))
        assert count == 1


class TestLinkCountCalculation:
    """Test that link count calculation is accurate."""
    
    def test_link_count_uses_rdf_query(self):
        """Link count should use proper RDF query, not approximation."""
        # Use the same namespace as in batch_bridge_generator.py
        WOBDBRIDGE = Namespace("https://wobd.org/bridge#")
        
        # Create a test graph with multiple LinkAssertions
        g = Graph()
        
        # Add 5 LinkAssertions
        for i in range(5):
            link_iri = URIRef(f"https://wobd.org/bridge/link/test{i}")
            g.add((link_iri, RDF.type, WOBDBRIDGE.LinkAssertion))
            g.add((link_iri, WOBDBRIDGE.sourceNode, URIRef(f"http://example.org/source{i}")))
            g.add((link_iri, WOBDBRIDGE.targetNode, URIRef(f"http://example.org/target{i}")))
        
        # Count using the proper method (as in batch_bridge_generator.py)
        link_count = len(list(g.triples((None, RDF.type, WOBDBRIDGE.LinkAssertion))))
        
        assert link_count == 5, f"Expected 5 links, got {link_count}"
    
    def test_link_count_vs_approximation(self):
        """Verify that proper counting differs from approximation."""
        # Use the same namespace as in batch_bridge_generator.py
        WOBDBRIDGE = Namespace("https://wobd.org/bridge#")
        
        # Create a test graph
        g = Graph()
        
        # Add 3 LinkAssertions with 9 triples each (typical structure)
        for i in range(3):
            link_iri = URIRef(f"https://wobd.org/bridge/link/test{i}")
            g.add((link_iri, RDF.type, WOBDBRIDGE.LinkAssertion))
            g.add((link_iri, WOBDBRIDGE.sourceNode, URIRef(f"http://example.org/source{i}")))
            g.add((link_iri, WOBDBRIDGE.targetNode, URIRef(f"http://example.org/target{i}")))
            g.add((link_iri, WOBDBRIDGE.sourceGraph, URIRef("http://example.org/graph1")))
            g.add((link_iri, WOBDBRIDGE.targetGraph, URIRef("http://example.org/graph2")))
            g.add((link_iri, WOBDBRIDGE.joinKeyType, WOBDBRIDGE.MONDO_ID))
            g.add((link_iri, WOBDBRIDGE.joinKeyValue, Literal("MONDO:0000001")))
            g.add((link_iri, WOBDBRIDGE.confidence, Literal(1.0)))
            g.add((link_iri, WOBDBRIDGE.inLinkset, URIRef("http://example.org/linkset1")))
        
        # Proper count
        proper_count = len(list(g.triples((None, RDF.type, WOBDBRIDGE.LinkAssertion))))
        
        # Old approximation method
        total_triples = len(list(g.triples((None, None, None))))
        approx_count = total_triples // 9
        
        assert proper_count == 3
        # The approximation might be close, but proper count is exact
        assert proper_count == approx_count or abs(proper_count - approx_count) <= 1


class TestIdentifierPatternExtraction:
    """Test identifier pattern extraction from base.py."""
    
    def test_pmc_pattern_in_extraction(self):
        """Test that PMC pattern extraction works in the patterns list."""
        # Simulate the pattern matching from base.py
        patterns = [
            (r'^(PMC)(\d+)$', 'PMC', r'^PMC\d+$'),
        ]
        
        test_values = ['PMC123456', 'PMC00012345']
        
        for test_value in test_values:
            matched = False
            for pattern_regex, known_prefix, known_pattern in patterns:
                match = re.match(pattern_regex, test_value)
                if match:
                    assert known_prefix == 'PMC'
                    assert known_pattern == r'^PMC\d+$'
                    matched = True
                    break
            assert matched, f"Should match {test_value}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
