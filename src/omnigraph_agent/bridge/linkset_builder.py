"""Linkset builder for generating bridge graph linksets between two graphs."""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, OWL, XSD
from SPARQLWrapper import SPARQLWrapper, JSON

from ..context_builder.model.context_schema import GlobalContext, IdentifierInfo, IdentifierPattern
from .semantic_mappings import are_semantically_related, get_semantically_related_prefixes


# Namespaces
WOBDBRIDGE = Namespace("https://wobd.org/bridge#")
VOID = Namespace("http://rdfs.org/ns/void#")
PROV = Namespace("http://www.w3.org/ns/prov#")
DCT = Namespace("http://purl.org/dc/terms/")


class LinksetBuilder:
    """Builds linksets between two graphs based on shared identifier patterns."""
    
    # Mapping from identifier prefix to join key type IRI
    JOIN_KEY_MAPPING = {
        'GSE': WOBDBRIDGE.GSE_ID,
        'NCT': WOBDBRIDGE.NCT_ID,
        'MONDO': WOBDBRIDGE.MONDO_ID,
        'HGNC': WOBDBRIDGE.HGNC_ID,
        'GO': WOBDBRIDGE.GO_ID,
        'DOID': WOBDBRIDGE.DOID_ID,
        'HP': WOBDBRIDGE.HP_ID,
        'CHEBI': WOBDBRIDGE.CHEBI_ID,
        'UniProtKB': WOBDBRIDGE.UniProtKB_ID,
        'PMID': WOBDBRIDGE.PMID_ID,
        'PMC': WOBDBRIDGE.PMC_ID,
    }
    
    def __init__(self, source_context_path: Path, target_context_path: Path):
        """
        Initialize linkset builder with two context files.
        
        Args:
            source_context_path: Path to source graph context JSON
            target_context_path: Path to target graph context JSON
        """
        self.source_context_path = source_context_path
        self.target_context_path = target_context_path
        
        # Load contexts
        with open(source_context_path, 'r') as f:
            source_data = json.load(f)
            self.source_context = GlobalContext(**source_data)
        
        with open(target_context_path, 'r') as f:
            target_data = json.load(f)
            self.target_context = GlobalContext(**target_data)
        
        # Initialize SPARQL clients
        self.source_sparql = SPARQLWrapper(self.source_context.endpoint)
        self.source_sparql.setReturnFormat(JSON)
        
        self.target_sparql = SPARQLWrapper(self.target_context.endpoint)
        self.target_sparql.setReturnFormat(JSON)
    
    def find_shared_join_keys(self, include_semantic: bool = True) -> List[str]:
        """
        Find shared join key types between source and target graphs.
        
        Args:
            include_semantic: If True, also include semantically related identifiers
        
        Returns:
            List of join key type prefixes (e.g., ['GSE', 'MONDO', 'NCT'])
        """
        if not self.source_context.identifier_info or not self.target_context.identifier_info:
            return []
        
        source_patterns = {p.prefix: p for p in self.source_context.identifier_info.patterns}
        target_patterns = {p.prefix: p for p in self.target_context.identifier_info.patterns}
        
        shared = []
        # Find exact matches
        for prefix in source_patterns.keys():
            if prefix in target_patterns:
                # Both graphs have this identifier prefix
                if prefix in self.JOIN_KEY_MAPPING:
                    shared.append(prefix)
                else:
                    # Unknown prefix - still include it but will need to create join key type
                    shared.append(prefix)
        
        # Find semantically related matches
        if include_semantic:
            for source_prefix, source_pattern in source_patterns.items():
                for target_prefix, target_pattern in target_patterns.items():
                    if source_prefix != target_prefix and source_prefix not in shared:
                        # Check if semantically related
                        if are_semantically_related(source_prefix, target_prefix):
                            # Use source prefix as canonical
                            shared.append(source_prefix)
        
        return shared
    
    def _find_best_matching_predicate(self, join_key_prefix: str, source_pattern: IdentifierPattern, target_pattern: IdentifierPattern) -> tuple:
        """
        Find the best matching predicate pair for a join key.
        
        Prefers predicates that match between source and target graphs.
        Falls back to any predicate that has the pattern.
        
        Args:
            join_key_prefix: Prefix of the join key (e.g., 'GSE', 'MONDO')
            source_pattern: Source graph's pattern for this prefix
            target_pattern: Target graph's pattern for this prefix
        
        Returns:
            Tuple of (source_predicate, target_predicate)
        """
        source_predicates = source_pattern.predicates if source_pattern.predicates else []
        target_predicates = target_pattern.predicates if target_pattern.predicates else []
        
        # Try to find matching predicates
        for source_pred in source_predicates:
            if source_pred in target_predicates:
                # Found a matching predicate!
                return (source_pred, source_pred)
        
        # No exact match - use the first predicate from each graph
        source_pred = source_predicates[0] if source_predicates else None
        target_pred = target_predicates[0] if target_predicates else None
        
        # Fallback to first identifier predicate if pattern has no predicates
        if not source_pred and self.source_context.identifier_info.predicates:
            source_pred = self.source_context.identifier_info.predicates[0]
        if not target_pred and self.target_context.identifier_info.predicates:
            target_pred = self.target_context.identifier_info.predicates[0]
        
        return (source_pred, target_pred)
    
    def normalize_join_value(self, value: str, join_key_prefix: str) -> str:
        """
        Normalize a join key value for matching.
        
        Handles:
        - Simple identifiers: "MONDO:0000001" or "MONDO0000001"
        - IRIs containing identifiers: "http://purl.obolibrary.org/obo/MONDO_0000001"
        
        Args:
            value: Raw identifier value
            join_key_prefix: Prefix of the join key (e.g., 'GSE', 'MONDO')
        
        Returns:
            Normalized value (e.g., "MONDO:0000001")
        """
        import re
        
        # Strip whitespace
        value = value.strip()
        
        # First, try to extract identifier from IRI if it's a full IRI
        # Pattern: http://.../MONDO_0000001 or http://.../MONDO:0000001
        iri_match = re.search(rf'{join_key_prefix}[:_](\d+)', value)
        if iri_match:
            # Extract the numeric part and create normalized identifier
            return f"{join_key_prefix}:{iri_match.group(1)}"
        
        # Special case: UniProtKB taxon IDs in format uniprot.org/taxonomy/9606
        # Normalize to NCBITaxon format for matching with NCBITaxon identifiers
        if join_key_prefix == 'UniProtKB' and 'uniprot.org/taxonomy' in value:
            taxon_match = re.search(r'/taxonomy/(\d+)', value)
            if taxon_match:
                # Extract just the numeric ID for matching (will match with NCBITaxon:9606)
                return f"NCBITaxon:{taxon_match.group(1)}"  # Normalize to NCBITaxon format for matching
        
        # Special case: NCBITaxon IRIs - normalize to NCBITaxon:ID format
        # This handles both source (UniProtKB) and target (NCBITaxon) normalization for semantic matches
        if 'NCBITaxon' in value or join_key_prefix == 'UniProtKB':
            ncbi_match = re.search(r'NCBITaxon[:_](\d+)', value)
            if ncbi_match:
                # Extract numeric ID and normalize to NCBITaxon:ID format
                return f"NCBITaxon:{ncbi_match.group(1)}"
        
        # Handle case variations for simple identifiers
        if join_key_prefix in ['GSE', 'NCT', 'PMC']:
            # Uppercase prefix
            if value.lower().startswith(join_key_prefix.lower()):
                value = join_key_prefix + value[len(join_key_prefix):]
        elif join_key_prefix in ['MONDO', 'HGNC', 'GO', 'DOID', 'HP', 'CHEBI', 'UniProtKB', 'PMID', 'NCBITaxon', 'ITIS', 'GBIF']:
            # Handle colon-separated IDs
            if ':' not in value and join_key_prefix in value:
                # Try to add colon (e.g., MONDO0000001 -> MONDO:0000001)
                match = re.search(rf'{join_key_prefix}[:_]?(\d+)', value)
                if match:
                    value = f"{join_key_prefix}:{match.group(1)}"
            elif ':' in value and not value.startswith('http'):
                # Already has colon, ensure format is correct (e.g., MONDO:0000001)
                parts = value.split(':', 1)
                if len(parts) == 2 and parts[0].upper() == join_key_prefix.upper():
                    value = f"{join_key_prefix}:{parts[1]}"
        
        return value
    
    def query_source_nodes(self, join_key_prefix: str, preferred_predicate: Optional[str] = None, semantic_match: Optional[str] = None) -> List[Tuple[str, str]]:
        """
        Query source graph for nodes with the given join key prefix.
        
        Args:
            join_key_prefix: Prefix of the join key (e.g., 'GSE', 'MONDO')
            preferred_predicate: Preferred predicate to use (if available)
            semantic_match: If provided, this is a semantic match - use this prefix for querying
        
        Returns:
            List of (node_iri, normalized_join_value) tuples
        """
        if not self.source_context.identifier_info:
            return []
        
        # For semantic matches, use the actual prefix in the source graph
        query_prefix = semantic_match if semantic_match else join_key_prefix
        
        # Find pattern and best matching predicate
        source_pattern = next((p for p in self.source_context.identifier_info.patterns if p.prefix == query_prefix), None)
        if not source_pattern:
            return []
        
        # Use preferred predicate if available and in pattern's predicates
        if preferred_predicate and preferred_predicate in (source_pattern.predicates or []):
            matching_predicate = preferred_predicate
        elif source_pattern.predicates:
            # Use first predicate from pattern
            matching_predicate = source_pattern.predicates[0]
        elif self.source_context.identifier_info.predicates:
            # Fallback to first identifier predicate
            matching_predicate = self.source_context.identifier_info.predicates[0]
        else:
            return []
        
        # Check if this is an entity IRI pattern (special case for ontologies)
        is_entity_iri = matching_predicate == 'ENTITY_IRI' or matching_predicate.startswith('ENTITY_IRI:')
        
        # Build query
        entity_filter = self._get_entity_type_filter(self.source_context.entity_types)
        
        if is_entity_iri:
            # For entity IRI patterns, query the entity IRIs directly
            # Extract identifier from the IRI itself
            import re
            # Pattern to extract identifier from IRI (e.g., MONDO_0000001 from http://purl.obolibrary.org/obo/MONDO_0000001)
            pattern_filter = f'FILTER (REGEX(STR(?entity), "{query_prefix}[:_]\\\\d+") || REGEX(STR(?entity), "{query_prefix}[:_][A-Z0-9]+"))'
            
            query = f"""
            SELECT DISTINCT ?entity
            WHERE {{
                {entity_filter}
                {pattern_filter}
            }}
            LIMIT 10000
            """
            
            self.source_sparql.setQuery(query)
            results = self.source_sparql.query().convert()
            
            nodes = []
            for binding in results['results']['bindings']:
                entity_iri = binding['entity']['value']
                # Extract identifier from entity IRI
                # Try to find MONDO:0000001 or MONDO_0000001 pattern
                match = re.search(rf'{query_prefix}[:_](\d+)', entity_iri)
                if match:
                    # Create normalized identifier value
                    identifier_value = f"{query_prefix}:{match.group(1)}"
                    normalized = self.normalize_join_value(identifier_value, query_prefix)
                    nodes.append((entity_iri, normalized))
        else:
            # Normal predicate-based query
            predicate_expanded = self._expand_property(matching_predicate)
            
            # Get pattern to filter values
            pattern_filter = ""
            if source_pattern.pattern:
                # Use regex filter (escape backslashes for SPARQL)
                escaped_pattern = source_pattern.pattern.replace('\\', '\\\\')
                pattern_filter = f'FILTER (REGEX(STR(?value), "{escaped_pattern}"))'
            elif query_prefix == 'UniProtKB' and source_pattern.example and 'uniprot' in str(source_pattern.example).lower():
                # Special case: UniProtKB taxon IDs in IRI format
                pattern_filter = 'FILTER (CONTAINS(STR(?value), "uniprot.org/taxonomy"))'
            else:
                # Simple prefix filter - use query_prefix for filtering
                pattern_filter = f'FILTER (STRSTARTS(STR(?value), "{query_prefix}") || STRSTARTS(STR(?value), "{query_prefix}:"))'
            
            query = f"""
            SELECT DISTINCT ?entity ?value
            WHERE {{
                {entity_filter}
                ?entity {predicate_expanded} ?value .
                {pattern_filter}
            }}
            LIMIT 10000
            """
            
            self.source_sparql.setQuery(query)
            results = self.source_sparql.query().convert()
            
            nodes = []
            for binding in results['results']['bindings']:
                entity_iri = binding['entity']['value']
                value = binding['value']['value']
                # For semantic matches, normalize to the canonical prefix (join_key_prefix)
                # but keep the original value for matching
                if semantic_match:
                    # Try to normalize to canonical prefix format
                    normalized = self.normalize_join_value(value, join_key_prefix)
                else:
                    normalized = self.normalize_join_value(value, query_prefix)
                nodes.append((entity_iri, normalized))
        
        return nodes
    
    def query_target_nodes(self, join_key_prefix: str, preferred_predicate: Optional[str] = None, semantic_match: Optional[str] = None) -> List[Tuple[str, str]]:
        """
        Query target graph for nodes with the given join key prefix.
        
        Args:
            join_key_prefix: Prefix of the join key (e.g., 'GSE', 'MONDO')
            preferred_predicate: Preferred predicate to use (if available)
            semantic_match: If provided, this is a semantic match - use this prefix for querying
        
        Returns:
            List of (node_iri, normalized_join_value) tuples
        """
        if not self.target_context.identifier_info:
            return []
        
        # For semantic matches, find the semantically related prefix in target
        if semantic_match:
            # Find which prefix in target is semantically related to join_key_prefix
            target_pattern = None
            for pattern in self.target_context.identifier_info.patterns:
                if are_semantically_related(join_key_prefix, pattern.prefix):
                    target_pattern = pattern
                    query_prefix = pattern.prefix
                    break
            if not target_pattern:
                return []
        else:
            query_prefix = join_key_prefix
            target_pattern = next((p for p in self.target_context.identifier_info.patterns if p.prefix == join_key_prefix), None)
            if not target_pattern:
                return []
        
        # Use preferred predicate if available and in pattern's predicates
        if preferred_predicate and preferred_predicate in (target_pattern.predicates or []):
            matching_predicate = preferred_predicate
        elif target_pattern.predicates:
            # Use first predicate from pattern
            matching_predicate = target_pattern.predicates[0]
        elif self.target_context.identifier_info.predicates:
            # Fallback to first identifier predicate
            matching_predicate = self.target_context.identifier_info.predicates[0]
        else:
            return []
        
        # Check if this is an entity IRI pattern (special case for ontologies)
        is_entity_iri = matching_predicate == 'ENTITY_IRI' or matching_predicate.startswith('ENTITY_IRI:')
        
        # Build query
        entity_filter = self._get_entity_type_filter(self.target_context.entity_types)
        
        if is_entity_iri:
            # For entity IRI patterns, query the entity IRIs directly
            # Extract identifier from the IRI itself
            import re
            # Pattern to extract identifier from IRI (e.g., MONDO_0000001 from http://purl.obolibrary.org/obo/MONDO_0000001)
            pattern_filter = f'FILTER (REGEX(STR(?entity), "{query_prefix}[:_]\\\\d+") || REGEX(STR(?entity), "{query_prefix}[:_][A-Z0-9]+"))'
            
            query = f"""
            SELECT DISTINCT ?entity
            WHERE {{
                {entity_filter}
                {pattern_filter}
            }}
            LIMIT 10000
            """
            
            self.target_sparql.setQuery(query)
            results = self.target_sparql.query().convert()
            
            nodes = []
            for binding in results['results']['bindings']:
                entity_iri = binding['entity']['value']
                # Extract identifier from entity IRI
                # Try to find MONDO:0000001 or MONDO_0000001 pattern
                match = re.search(rf'{query_prefix}[:_](\d+)', entity_iri)
                if match:
                    # Create normalized identifier value
                    identifier_value = f"{query_prefix}:{match.group(1)}"
                    normalized = self.normalize_join_value(identifier_value, query_prefix)
                    nodes.append((entity_iri, normalized))
        else:
            # Normal predicate-based query
            predicate_expanded = self._expand_property(matching_predicate)
            
            # Get pattern to filter values
            # For IRIs, we need to check if the IRI contains the identifier pattern
            # For literals, we can use string prefix matching
            pattern_filter = ""
            if target_pattern.pattern:
                # Use regex pattern (works for both IRIs and literals)
                pattern_filter = f'FILTER (REGEX(STR(?value), "{target_pattern.pattern}"))'
            else:
                # For IRIs, check if the IRI contains the prefix pattern
                # For literals, check string prefix
                # Use regex to match prefix in IRI (e.g., MONDO_0000001 in http://.../MONDO_0000001)
                pattern_filter = f'FILTER (REGEX(STR(?value), "{query_prefix}[:_]\\\\d+") || STRSTARTS(STR(?value), "{query_prefix}") || STRSTARTS(STR(?value), "{query_prefix}:"))'
            
            query = f"""
            SELECT DISTINCT ?entity ?value
            WHERE {{
                {entity_filter}
                ?entity {predicate_expanded} ?value .
                {pattern_filter}
            }}
            LIMIT 10000
            """
            
            self.target_sparql.setQuery(query)
            results = self.target_sparql.query().convert()
            
            nodes = []
            for binding in results['results']['bindings']:
                entity_iri = binding['entity']['value']
                value = binding['value']['value']
                # For semantic matches, normalize to canonical prefix
                if semantic_match:
                    normalized = self.normalize_join_value(value, join_key_prefix)
                else:
                    normalized = self.normalize_join_value(value, query_prefix)
                nodes.append((entity_iri, normalized))
        
        return nodes
    
    def build_linkset(self, join_key_prefix: str, confidence: float = 1.0) -> Graph:
        """
        Build a linkset RDF graph for a given join key type.
        
        Args:
            join_key_prefix: Prefix of the join key (e.g., 'GSE', 'MONDO')
            confidence: Default confidence score for links
        
        Returns:
            RDFLib Graph containing the linkset
        """
        g = Graph()
        
        # Bind namespaces
        g.bind("wobd-bridge", WOBDBRIDGE)
        g.bind("void", VOID)
        g.bind("prov", PROV)
        g.bind("dct", DCT)
        g.bind("owl", OWL)
        
        # Get join key type IRI
        if join_key_prefix in self.JOIN_KEY_MAPPING:
            join_key_type = self.JOIN_KEY_MAPPING[join_key_prefix]
        else:
            # Create a new join key type for unknown prefixes
            join_key_type = WOBDBRIDGE[f"{join_key_prefix}_ID"]
        
        # Create linkset IRI
        source_id = self.source_context.graph_id
        target_id = self.target_context.graph_id
        linkset_iri = URIRef(f"https://wobd.org/bridge/linkset/{source_id}__{target_id}-{join_key_prefix.lower()}")
        
        # Create linkset
        g.add((linkset_iri, RDF.type, VOID.Linkset))
        g.add((linkset_iri, DCT.title, Literal(f"Linkset: {source_id} → {target_id} via {join_key_prefix} IDs")))
        g.add((linkset_iri, VOID.subjectsTarget, URIRef(self.source_context.endpoint)))
        g.add((linkset_iri, VOID.objectsTarget, URIRef(self.target_context.endpoint)))
        g.add((linkset_iri, VOID.linkPredicate, OWL.sameAs))
        
        # Check if this is a semantic match (prefix exists in one graph but semantically related prefix in other)
        source_pattern = next((p for p in self.source_context.identifier_info.patterns if p.prefix == join_key_prefix), None)
        target_pattern = next((p for p in self.target_context.identifier_info.patterns if p.prefix == join_key_prefix), None)
        
        # Determine if this is a semantic match
        semantic_source = None
        semantic_target = None
        if not source_pattern:
            # Source doesn't have this prefix - find semantically related one
            for pattern in self.source_context.identifier_info.patterns:
                if are_semantically_related(join_key_prefix, pattern.prefix):
                    source_pattern = pattern
                    semantic_source = pattern.prefix
                    break
        if not target_pattern:
            # Target doesn't have this prefix - find semantically related one
            for pattern in self.target_context.identifier_info.patterns:
                if are_semantically_related(join_key_prefix, pattern.prefix):
                    target_pattern = pattern
                    semantic_target = pattern.prefix
                    break
        
        if source_pattern and target_pattern:
            source_pred, target_pred = self._find_best_matching_predicate(join_key_prefix, source_pattern, target_pattern)
        else:
            source_pred = None
            target_pred = None
        
        # Query nodes from both graphs using best matching predicates
        source_nodes = self.query_source_nodes(join_key_prefix, preferred_predicate=source_pred, semantic_match=semantic_source)
        target_nodes = self.query_target_nodes(join_key_prefix, preferred_predicate=target_pred, semantic_match=semantic_target)
        
        # Create index for fast lookup
        target_index: Dict[str, List[str]] = {}
        for target_iri, target_value in target_nodes:
            if target_value not in target_index:
                target_index[target_value] = []
            target_index[target_value].append(target_iri)
        
        # Match and create link assertions
        link_count = 0
        for source_iri, source_value in source_nodes:
            if source_value in target_index:
                # Match found - create link assertion
                for target_iri in target_index[source_value]:
                    link_iri = URIRef(f"https://wobd.org/bridge/link/{source_id}_{source_iri.split('/')[-1]}__{target_id}_{target_iri.split('/')[-1]}-{join_key_prefix.lower()}")
                    
                    g.add((link_iri, RDF.type, WOBDBRIDGE.LinkAssertion))
                    g.add((link_iri, WOBDBRIDGE.sourceNode, URIRef(source_iri)))
                    g.add((link_iri, WOBDBRIDGE.targetNode, URIRef(target_iri)))
                    g.add((link_iri, WOBDBRIDGE.sourceGraph, URIRef(self.source_context.endpoint)))
                    g.add((link_iri, WOBDBRIDGE.targetGraph, URIRef(self.target_context.endpoint)))
                    g.add((link_iri, WOBDBRIDGE.joinKeyType, join_key_type))
                    g.add((link_iri, WOBDBRIDGE.joinKeyValue, Literal(source_value, datatype=XSD.string)))
                    g.add((link_iri, WOBDBRIDGE.confidence, Literal(confidence, datatype=XSD.double)))
                    g.add((link_iri, WOBDBRIDGE.inLinkset, linkset_iri))
                    
                    link_count += 1
        
        return g
    
    def _get_entity_type_filter(self, entity_types: List[str]) -> str:
        """Generate entity type filter clause."""
        if not entity_types:
            return "?entity a ?type ."
        
        if len(entity_types) == 1:
            return f"?entity a <{entity_types[0]}> ."
        else:
            values = " ".join([f"<{et}>" for et in entity_types])
            return f"?entity a ?type . VALUES ?type {{ {values} }}"
    
    def _expand_property(self, property_name: str) -> str:
        """Expand property name to full IRI."""
        if property_name.startswith('<') and property_name.endswith('>'):
            return property_name
        if property_name.startswith('http'):
            return f"<{property_name}>"
        if ':' in property_name:
            prefix, local = property_name.split(':', 1)
            if prefix == 'schema':
                return f"<http://schema.org/{local}>"
            elif prefix == 'dct':
                return f"<http://purl.org/dc/terms/{local}>"
            elif prefix == 'rdf':
                return f"<http://www.w3.org/1999/02/22-rdf-syntax-ns#{local}>"
        return property_name

