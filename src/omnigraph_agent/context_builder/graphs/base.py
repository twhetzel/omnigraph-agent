"""
Base graph handler for context building.

Provides general SPARQL query functionality and introspection methods
that can be used across different knowledge graphs.
"""

APPROX_DISTINCT_THRESHOLD = 10000

import yaml
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from SPARQLWrapper import SPARQLWrapper, JSON
from urllib.parse import urlparse


class BaseGraph(ABC):
    """Base class for graph handlers."""
    
    def __init__(self, config_path: Optional[Path] = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize graph handler with configuration.
        
        Args:
            config_path: Path to YAML config file
            config: Optional pre-loaded config dict (takes precedence over config_path)
        """
        if config is None:
            if config_path is None:
                raise ValueError("Either config_path or config must be provided")
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
        
        self.config = config
        self.endpoint = self.config['endpoint']
        self.graph_id = self.config['graph_id']
        self.repo_filter_property = self.config['repo_filter_property']
        self.dimensions = self.config.get('dimensions', [])
        self.entity_types = self.config.get('entity_types', [])
        self.text_blurb = self.config.get('text_blurb', '')
        
        # Named graph and namespace scope for ontology filtering
        self.named_graph = self.config.get('named_graph')
        self.namespace_scope = self.config.get('namespace_scope')
        
        self.sparql = SPARQLWrapper(self.endpoint)
        self.sparql.setReturnFormat(JSON)
    
    def _expand_property(self, property_name: str) -> str:
        """
        Expand a property name to full IRI.
        
        Args:
            property_name: Property name like "schema:name" or full IRI
        
        Returns:
            Full IRI in angle brackets
        """
        if property_name.startswith('<') and property_name.endswith('>'):
            return property_name  # Already expanded
        if property_name.startswith('http'):
            return f"<{property_name}>"  # Full IRI without brackets
        if ':' in property_name:
            # Prefixed name - expand to full IRI
            prefix, local = property_name.split(':', 1)
            if prefix == 'schema':
                return f"<http://schema.org/{local}>"
            elif prefix == 'rdf':
                return f"<http://www.w3.org/1999/02/22-rdf-syntax-ns#{local}>"
            # Unknown prefix - return as-is (might work with PREFIX)
            return property_name
        return property_name
    
    def _get_entity_type_filter(self, entity_var: str = "?entity") -> str:
        """
        Generate entity type filter clause for queries.
        
        Args:
            entity_var: Variable name to use for entity (default: "?entity")
        
        Returns SPARQL pattern like "?entity a schema:Dataset ." or
        "?entity a ?type . FILTER (?type IN (...))" for multiple types.
        """
        if not self.entity_types:
            return f"{entity_var} a ?type ."  # Generic fallback
        
        if len(self.entity_types) == 1:
            # Single entity type - simple pattern
            entity_type = self.entity_types[0]
            return f"{entity_var} a <{entity_type}> ."
        else:
            # Multiple entity types - use VALUES for better performance than UNION
            values = " ".join([f"<{et}>" for et in self.entity_types])
            return f"{entity_var} a ?type . VALUES ?type {{ {values} }}"
    
    def _extract_repo_id(self, uri: str) -> str:
        """Extract a clean repository ID from a URI."""
        # Try to get the last segment of the path
        parsed = urlparse(uri)
        path_parts = [p for p in parsed.path.split('/') if p]
        if path_parts:
            return path_parts[-1].lower()
        # Fallback to domain name
        domain = parsed.netloc.replace('www.', '').split('.')[0]
        return domain.lower()
    
    def _guess_named_graph(self) -> Optional[str]:
        """
        Guess the named graph URI based on endpoint and graph_id.
        
        For Ubergraph, named graphs are typically:
        - http://ubergraph.apps.renci.org/graphs/{graph_id}
        
        Returns:
            Guessed named graph URI or None if not applicable
        """
        if 'ubergraph' in self.endpoint.lower():
            # Ubergraph uses /graphs/{ontology_id} pattern
            return f"http://ubergraph.apps.renci.org/graphs/{self.graph_id.lower()}"
        return None
    
    def _discover_named_graphs(self) -> List[str]:
        """
        Discover available named graphs from the endpoint.
        
        Returns:
            List of named graph URIs
        """
        try:
            query = """
            SELECT DISTINCT ?g WHERE {
                GRAPH ?g {
                    ?s ?p ?o .
                }
            }
            LIMIT 100
            """
            self.sparql.setQuery(query)
            results = self.sparql.query().convert()
            
            graphs = []
            for binding in results['results']['bindings']:
                graph_uri = binding['g']['value']
                graphs.append(graph_uri)
            
            return graphs
        except Exception:
            # If discovery fails, return empty list
            return []
    
    def _get_graph_clause(self) -> str:
        """
        Get the SPARQL clause to limit queries to a specific named graph.
        
        Returns:
            "FROM <graph_uri>" clause if named graph is available, empty string otherwise
        """
        # Use explicitly configured named graph
        if self.named_graph:
            return f"FROM <{self.named_graph}>\n        "
        
        # Try to guess named graph (e.g., for Ubergraph)
        guessed_graph = self._guess_named_graph()
        if guessed_graph:
            # Verify the graph exists by trying a simple query
            try:
                test_query = f"""
                FROM <{guessed_graph}>
                SELECT (COUNT(*) as ?count) WHERE {{
                    ?s ?p ?o .
                }}
                LIMIT 1
                """
                self.sparql.setQuery(test_query)
                self.sparql.query().convert()
                # If query succeeds, use the guessed graph
                return f"FROM <{guessed_graph}>\n        "
            except Exception:
                # Graph doesn't exist or endpoint doesn't support FROM
                pass
        
        return ""
    
    def _get_namespace_filter(self, entity_var: str = "?entity") -> str:
        """
        Get the SPARQL FILTER clause to limit queries by namespace scope.
        
        Args:
            entity_var: Variable name to filter (default: "?entity")
        
        Returns:
            FILTER clause string or empty string if no namespace scope
        """
        if self.namespace_scope:
            return f'FILTER STRSTARTS(STR({entity_var}), "{self.namespace_scope}")'
        return ""
    
    def get_repository_filter(self, repo_id: str, repo_uri: str) -> Dict[str, str]:
        """Generate repository filter dictionary for a specific repository."""
        return {
            self.repo_filter_property: repo_uri
        }

    def get_prefixes(self) -> Dict[str, str]:
        """
        Collect prefix mappings used across dimensions, entity types, and repo filter.
        Simple heuristic: detect prefixed names (prefix:suffix) and add common known IRIs.
        For ontologies, also adds ontology-specific prefixes based on namespace_scope.
        """
        # Initialize with core prefixes always used in queries
        prefixes: Dict[str, str] = {
            "schema": "http://schema.org/",
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "dc": "http://purl.org/dc/elements/1.1/",
            "obo": "http://purl.obolibrary.org/obo/",
            "oboInOwl": "http://www.geneontology.org/formats/oboInOwl#"
        }
        
        # Add ontology-specific prefixes if this is an ontology (has namespace_scope)
        if hasattr(self, 'namespace_scope') and self.namespace_scope:
            # Add owl and xsd for ontologies
            prefixes["owl"] = "http://www.w3.org/2002/07/owl#"
            prefixes["xsd"] = "http://www.w3.org/2001/XMLSchema#"
            
            # Extract ontology prefix from namespace_scope (e.g., "http://purl.obolibrary.org/obo/VBO_" -> "VBO")
            if "purl.obolibrary.org/obo/" in self.namespace_scope:
                # Extract ontology ID (e.g., VBO, MONDO, RO, IAO)
                parts = self.namespace_scope.split("/obo/")
                if len(parts) > 1:
                    ontology_id = parts[1].rstrip("_").upper()
                    if ontology_id:
                        prefixes[ontology_id] = self.namespace_scope
                
                # Add common OBO ontology prefixes
                prefixes["RO"] = "http://purl.obolibrary.org/obo/RO_"
                prefixes["IAO"] = "http://purl.obolibrary.org/obo/IAO_"

        def add_prefixed(name: str):
            if name.startswith("http") or name.startswith("<"):
                return
            if ":" in name:
                prefix = name.split(":", 1)[0]
                # Only add unknown prefixes (core prefixes already initialized)
                if prefix not in prefixes:
                    # Unknown prefix; leave unmapped (could be extended later)
                    prefixes[prefix] = ""

        add_prefixed(self.repo_filter_property)
        for et in self.entity_types:
            add_prefixed(et)
        for dim in self.dimensions:
            add_prefixed(dim.get("property", ""))

        return prefixes
    
    def get_dimension_property(self, dimension_name: str) -> Optional[str]:
        """Get the property IRI for a dimension."""
        for dim in self.dimensions:
            if dim.get('name') == dimension_name:
                return dim.get('property')
        return None
    
    def count_datasets(self, repository_filter: Optional[Dict[str, str]] = None) -> int:
        """Count total entities, optionally filtered by repository."""
        filter_clause = ""
        if repository_filter:
            prop = list(repository_filter.keys())[0]
            value = list(repository_filter.values())[0]
            prop_expanded = self._expand_property(prop)
            filter_clause = f"?entity {prop_expanded} <{value}> ."
        
        entity_filter = self._get_entity_type_filter("?entity")
        
        query = f"""
        PREFIX schema: <http://schema.org/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        
        SELECT (COUNT(DISTINCT ?entity) as ?count)
        WHERE {{
            {entity_filter}
            {filter_clause}
        }}
        """
        
        self.sparql.setQuery(query)
        results = self.sparql.query().convert()
        
        if results['results']['bindings']:
            return int(results['results']['bindings'][0]['count']['value'])
        return 0
    
    def get_dimension_coverage(self, dimension: Dict[str, Any], 
                              repository_filter: Optional[Dict[str, str]] = None) -> float:
        """
        Calculate coverage: fraction of entities that have this dimension.
        
        Returns a float between 0.0 and 1.0.
        """
        total = self.count_datasets(repository_filter)
        if total == 0:
            return 0.0
        
        property_iri = dimension.get('property')
        property_iri_expanded = self._expand_property(property_iri)
        filter_expr = dimension.get('filter', '').strip()
        
        filter_clause = ""
        if repository_filter:
            prop = list(repository_filter.keys())[0]
            value = list(repository_filter.values())[0]
            prop_expanded = self._expand_property(prop)
            filter_clause = f"?entity {prop_expanded} <{value}> ."
        
        # Add filter expression if provided (applied to ?value)
        value_filter = f"?value {filter_expr} ." if filter_expr else ""
        
        entity_filter = self._get_entity_type_filter("?entity")
        
        query = f"""
        PREFIX schema: <http://schema.org/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        
        SELECT (COUNT(DISTINCT ?entity) as ?count)
        WHERE {{
            {entity_filter}
            {filter_clause}
            ?entity {property_iri_expanded} ?value .
            {value_filter}
        }}
        """
        
        self.sparql.setQuery(query)
        results = self.sparql.query().convert()
        
        if results['results']['bindings']:
            with_dimension = int(results['results']['bindings'][0]['count']['value'])
            return with_dimension / total if total > 0 else 0.0
        
        return 0.0
    
    def get_distinct_values_count(self, dimension: Dict[str, Any],
                                  repository_filter: Optional[Dict[str, str]] = None,
                                  limit: int = 10000) -> int:
        """
        Get approximate count of distinct values for a dimension.
        
        Uses LIMIT to avoid expensive exact counts on large graphs.
        """
        property_iri = dimension.get('property')
        property_iri_expanded = self._expand_property(property_iri)
        filter_expr = dimension.get('filter', '').strip()
        
        filter_clause = ""
        if repository_filter:
            prop = list(repository_filter.keys())[0]
            value = list(repository_filter.values())[0]
            prop_expanded = self._expand_property(prop)
            filter_clause = f"?entity {prop_expanded} <{value}> ."
        
        # Add filter expression if provided (applied to ?value)
        value_filter = f"?value {filter_expr} ." if filter_expr else ""
        
        entity_filter = self._get_entity_type_filter("?entity")
        
        query = f"""
        PREFIX schema: <http://schema.org/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        
        SELECT (COUNT(DISTINCT ?value) as ?count)
        WHERE {{
            {entity_filter}
            {filter_clause}
            ?entity {property_iri_expanded} ?value .
            {value_filter}
        }}
        LIMIT {limit}
        """
        
        self.sparql.setQuery(query)
        results = self.sparql.query().convert()
        
        if results['results']['bindings']:
            return int(results['results']['bindings'][0]['count']['value'])
        return 0
    
    def get_top_values(self, dimension: Dict[str, Any],
                      repository_filter: Optional[Dict[str, str]] = None,
                      top_n: int = 10) -> List[Dict[str, Any]]:
        """
        Get top N values for a dimension with their counts.
        
        Returns list of dicts with 'value' and 'count' keys.
        """
        property_iri = dimension.get('property')
        property_iri_expanded = self._expand_property(property_iri)
        filter_expr = dimension.get('filter', '').strip()
        
        filter_clause = ""
        if repository_filter:
            prop = list(repository_filter.keys())[0]
            value = list(repository_filter.values())[0]
            prop_expanded = self._expand_property(prop)
            filter_clause = f"?entity {prop_expanded} <{value}> ."
        
        # Add filter expression if provided (applied to ?value)
        value_filter = f"?value {filter_expr} ." if filter_expr else ""
        
        entity_filter = self._get_entity_type_filter("?entity")
        
        query = f"""
        PREFIX schema: <http://schema.org/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        
        SELECT ?value (COUNT(DISTINCT ?entity) as ?count)
        WHERE {{
            {entity_filter}
            {filter_clause}
            ?entity {property_iri_expanded} ?value .
            {value_filter}
        }}
        GROUP BY ?value
        ORDER BY DESC(?count)
        LIMIT {top_n}
        """
        
        self.sparql.setQuery(query)
        results = self.sparql.query().convert()
        
        top_values = []
        for binding in results['results']['bindings']:
            value = binding['value']['value']
            count = int(binding['count']['value'])
            top_values.append({
                'value': value,
                'count': count
            })
        
        return top_values
    
    def introspect_properties(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Introspect the graph to discover all properties used on entities.
        
        Uses named graph (FROM clause) if available for efficiency on multi-ontology endpoints.
        
        Returns list of dicts with 'property', 'count', and 'sample_value' keys.
        """
        entity_filter = self._get_entity_type_filter()
        graph_clause = self._get_graph_clause()
        namespace_filter = self._get_namespace_filter(entity_var="?entity")
        
        query = f"""
        {graph_clause}SELECT ?property (COUNT(DISTINCT ?entity) as ?count) (SAMPLE(?value) as ?sample_value)
        WHERE {{
            {entity_filter}
            {namespace_filter}
            ?entity ?property ?value .
        }}
        GROUP BY ?property
        ORDER BY DESC(?count)
        LIMIT {limit}
        """
        
        self.sparql.setQuery(query)
        results = self.sparql.query().convert()
        
        properties = []
        for binding in results['results']['bindings']:
            prop_uri = binding['property']['value']
            count = int(binding['count']['value'])
            sample_value = binding.get('sample_value', {}).get('value', '')
            
            properties.append({
                'property': prop_uri,
                'count': count,
                'sample_value': sample_value
            })
        
        return properties
    
    def introspect_entity_types(self, limit: int = 50) -> List[str]:
        """
        Introspect the graph to discover all entity types.
        
        Uses named graph (FROM clause) if available for efficiency on multi-ontology endpoints.
        
        Returns list of type URIs.
        """
        graph_clause = self._get_graph_clause()
        namespace_filter = self._get_namespace_filter(entity_var="?s")
        
        query = f"""
        {graph_clause}SELECT DISTINCT ?type (COUNT(?s) as ?count)
        WHERE {{
            {namespace_filter}
            ?s a ?type .
        }}
        GROUP BY ?type
        ORDER BY DESC(?count)
        LIMIT {limit}
        """
        
        self.sparql.setQuery(query)
        results = self.sparql.query().convert()
        
        types = []
        for binding in results['results']['bindings']:
            type_uri = binding['type']['value']
            types.append(type_uri)
        
        return types
    
    def introspect_repository_properties(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Introspect to discover properties that link entities to repositories/catalogs.
        
        Returns list of dicts with 'property', 'count', and 'sample_catalog' keys.
        """
        entity_filter = self._get_entity_type_filter()
        
        query = f"""
        SELECT ?property (COUNT(DISTINCT ?entity) as ?count) (SAMPLE(?catalog) as ?sample_catalog)
        WHERE {{
            {entity_filter}
            ?entity ?property ?catalog .
            ?catalog a ?catalogType .
        }}
        GROUP BY ?property
        ORDER BY DESC(?count)
        LIMIT {limit}
        """
        
        self.sparql.setQuery(query)
        results = self.sparql.query().convert()
        
        repo_properties = []
        for binding in results['results']['bindings']:
            prop_uri = binding['property']['value']
            count = int(binding['count']['value'])
            sample_catalog = binding.get('sample_catalog', {}).get('value', '')
            
            repo_properties.append({
                'property': prop_uri,
                'count': count,
                'sample_catalog': sample_catalog
            })
        
        return repo_properties
    
    def introspect_identifier_predicates(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Introspect to discover predicates commonly used for identifiers.
        
        Checks for property names containing "id", "identifier", "xref", or known
        identifier namespaces (schema:identifier, dct:identifier, oboInOwl:hasDbXref, biolink:id).
        
        Returns list of dicts with 'property', 'count', and 'sample_value' keys.
        """
        entity_filter = self._get_entity_type_filter()
        graph_clause = self._get_graph_clause()
        
        # Known identifier namespaces
        known_id_namespaces = [
            "http://schema.org/identifier",
            "http://purl.org/dc/terms/identifier",
            "http://www.geneontology.org/formats/oboInOwl#hasDbXref",
            "https://w3id.org/biolink/vocab/id",
            "http://www.w3.org/2004/02/skos/core#exactMatch",
            "http://www.w3.org/2002/07/owl#sameAs"
        ]
        
        # Build filter for known namespaces
        namespace_filter = " || ".join([f"STR(?property) = \"{ns}\"" for ns in known_id_namespaces])
        
        query = f"""
        PREFIX schema: <http://schema.org/>
        PREFIX dct: <http://purl.org/dc/terms/>
        PREFIX oboInOwl: <http://www.geneontology.org/formats/oboInOwl#>
        PREFIX biolink: <https://w3id.org/biolink/vocab/>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        {graph_clause}
        SELECT ?property (COUNT(DISTINCT ?entity) as ?count) (SAMPLE(?value) as ?sample_value)
        WHERE {{
            {entity_filter}
            ?entity ?property ?value .
            FILTER (
                REGEX(LCASE(STR(?property)), "(id|identifier|xref|match|sameas)") ||
                ({namespace_filter})
            )
            FILTER (isLiteral(?value) || isIRI(?value))
        }}
        GROUP BY ?property
        ORDER BY DESC(?count)
        LIMIT {limit}
        """
        
        self.sparql.setQuery(query)
        results = self.sparql.query().convert()
        
        identifier_predicates = []
        for binding in results['results']['bindings']:
            prop_uri = binding['property']['value']
            count = int(binding['count']['value'])
            sample_value = binding.get('sample_value', {}).get('value', '')
            
            identifier_predicates.append({
                'property': prop_uri,
                'count': count,
                'sample_value': sample_value
            })
        
        return identifier_predicates
    
    def extract_identifier_patterns(self, predicate: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Extract identifier patterns from values of a given predicate.
        
        Queries for values of the predicate and extracts prefixes/patterns using regex:
        - GSE12345 → prefix: "GSE", pattern: ^GSE\\d+$
        - NCT00012345 → prefix: "NCT", pattern: ^NCT\\d+$
        - MONDO:0000001 → prefix: "MONDO", pattern: ^MONDO:\\d+$
        - HGNC:1234 → prefix: "HGNC", pattern: ^HGNC:\\d+$
        
        Args:
            predicate: Full IRI of the identifier predicate
            limit: Maximum number of values to sample
            
        Returns:
            List of dicts with 'prefix', 'pattern', 'example', 'count' keys
        """
        entity_filter = self._get_entity_type_filter()
        graph_clause = self._get_graph_clause()
        predicate_expanded = self._expand_property(predicate)
        
        query = f"""
        {graph_clause}
        SELECT ?value (COUNT(DISTINCT ?entity) as ?count)
        WHERE {{
            {entity_filter}
            ?entity {predicate_expanded} ?value .
            FILTER (isLiteral(?value) || isIRI(?value))
        }}
        GROUP BY ?value
        ORDER BY DESC(?count)
        LIMIT {limit}
        """
        
        self.sparql.setQuery(query)
        results = self.sparql.query().convert()
        
        # Pattern extraction regexes
        patterns = [
            (r'^(GSE)(\d+)$', 'GSE', r'^GSE\d+$'),
            (r'^(NCT)(\d+)$', 'NCT', r'^NCT\d+$'),
            (r'^(MONDO):(\d+)$', 'MONDO', r'^MONDO:\d+$'),
            (r'^(HGNC):(\d+)$', 'HGNC', r'^HGNC:\d+$'),
            (r'^(GO):(\d+)$', 'GO', r'^GO:\d+$'),
            (r'^(DOID):(\d+)$', 'DOID', r'^DOID:\d+$'),
            (r'^(HP):(\d+)$', 'HP', r'^HP:\d+$'),
            (r'^(CHEBI):(\d+)$', 'CHEBI', r'^CHEBI:\d+$'),
            (r'^(UniProtKB):([A-Z0-9]+)$', 'UniProtKB', r'^UniProtKB:[A-Z0-9]+$'),
            (r'^(PMID):(\d+)$', 'PMID', r'^PMID:\d+$'),
            (r'^(PMC):(\d+)$', 'PMC', r'^PMC\d+$'),
            # Generic patterns
            (r'^([A-Z]{2,}):(\d+)$', None, None),  # Two+ letter prefix with colon
            (r'^([A-Z]{2,})(\d+)$', None, None),   # Two+ letter prefix without colon
        ]
        
        pattern_counts: Dict[str, Dict[str, Any]] = {}
        
        for binding in results['results']['bindings']:
            value_str = binding['value']['value']
            count = int(binding['count']['value'])
            
            # Try to match against known patterns
            matched = False
            for pattern_regex, known_prefix, known_pattern in patterns:
                match = re.match(pattern_regex, value_str)
                if match:
                    if known_prefix:
                        prefix = known_prefix
                        pattern = known_pattern
                    else:
                        # Extract prefix from match
                        prefix = match.group(1)
                        # Generate pattern
                        if ':' in value_str:
                            pattern = f"^{prefix}:\\d+$"
                        else:
                            pattern = f"^{prefix}\\d+$"
                    
                    if prefix not in pattern_counts:
                        pattern_counts[prefix] = {
                            'prefix': prefix,
                            'pattern': pattern,
                            'example': value_str,
                            'count': 0
                        }
                    pattern_counts[prefix]['count'] += count
                    matched = True
                    break
            
            # If no pattern matched, try to extract a simple prefix
            if not matched:
                # Try to find a prefix-like pattern
                simple_match = re.match(r'^([A-Z]{2,})[:\-_]?(\d+|[A-Z0-9]+)', value_str)
                if simple_match:
                    prefix = simple_match.group(1)
                    if prefix not in pattern_counts:
                        pattern_counts[prefix] = {
                            'prefix': prefix,
                            'pattern': None,  # Unknown pattern
                            'example': value_str,
                            'count': 0
                        }
                    pattern_counts[prefix]['count'] += count
        
        # Convert to list and sort by count
        patterns_list = list(pattern_counts.values())
        patterns_list.sort(key=lambda x: x['count'], reverse=True)
        
        return patterns_list
    
    def generate_suggested_config(
        self,
        output_path: Optional[Path] = None,
        properties_limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Generate a suggested configuration based on introspection.
        
        Returns a dict that can be written to YAML.
        """
        print(f"Introspecting {self.graph_id} graph...")
        
        # Discover properties
        print("  Discovering properties...")
        properties = self.introspect_properties(limit=properties_limit)
        
        # Discover entity types
        print("  Discovering entity types...")
        entity_types = self.introspect_entity_types(limit=20)
        
        # Discover repository properties
        print("  Discovering repository properties...")
        repo_properties = self.introspect_repository_properties(limit=10)
        
        # Find most likely repo filter property
        repo_filter_property = self.repo_filter_property  # Use existing or default
        if repo_properties:
            # Use the most common repository property
            repo_filter_property = repo_properties[0]['property']
        
        # Build dimensions from top properties
        dimensions = []
        # Filter to properties that match common vocabularies (schema.org, etc.)
        common_properties = [p for p in properties if any(vocab in p['property'] for vocab in ['schema.org', 'w3.org', 'purl.org'])]
        
        for prop_info in common_properties[:10]:  # Top 10 properties
            prop_uri = prop_info['property']
            # Extract short name
            if 'schema.org' in prop_uri:
                prop_name = prop_uri.split('/')[-1] or prop_uri.split('#')[-1]
                short_name = f"schema:{prop_name}"
            elif '#' in prop_uri:
                prop_name = prop_uri.split('#')[-1]
                short_name = prop_uri
            else:
                prop_name = prop_uri.split('/')[-1] or prop_uri
                short_name = prop_uri
            
            dimensions.append({
                'name': prop_name.lower().replace(':', '_').replace('-', '_'),
                'property': short_name,
                'filter': ''  # Can be filled in manually
            })
        
        # Filter entity types to relevant ones
        relevant_entity_types = [
            et for et in entity_types 
            if any(keyword in et.lower() for keyword in ['dataset', 'catalog', 'data', 'entity', 'resource'])
        ]
        
        config = {
            'graph_id': self.graph_id,
            'endpoint': self.endpoint,
            'repo_filter_property': repo_filter_property,
            'dimensions': dimensions,
            'entity_types': relevant_entity_types[:5] if relevant_entity_types else self.entity_types[:1] if self.entity_types else [],
            'text_blurb': f"{self.graph_id} graph at {self.endpoint} - properties discovered via introspection"
        }
        
        if output_path:
            with open(output_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            print(f"  Suggested config written to {output_path}")
        
        return config
    
    @abstractmethod
    def get_repositories(self) -> List[Dict[str, str]]:
        """
        Detect repositories in the graph.
        
        Returns list of dicts with 'id', 'uri', and 'label' keys.
        Must be implemented by subclasses as repository detection
        logic varies by graph.
        """
        pass

