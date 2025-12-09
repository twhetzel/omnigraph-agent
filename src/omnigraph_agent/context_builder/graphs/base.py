"""
Base graph handler for context building.

Provides general SPARQL query functionality and introspection methods
that can be used across different knowledge graphs.
"""

import yaml
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional
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
            # Multiple entity types - use UNION
            union_parts = " UNION ".join([f"{{ {entity_var} a <{et}> . }}" for et in self.entity_types])
            return union_parts
    
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
    
    def get_repository_filter(self, repo_id: str, repo_uri: str) -> Dict[str, str]:
        """Generate repository filter dictionary for a specific repository."""
        return {
            self.repo_filter_property: repo_uri
        }
    
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
        
        # Use first entity type (typically the main entity type like Dataset)
        # For NDE, this is Dataset, not DataCatalog
        if self.entity_types:
            main_entity_type = self.entity_types[0]
            entity_filter = f"?entity a <{main_entity_type}> ."
        else:
            entity_filter = "?entity a ?type ."
        
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
        
        # Use first entity type for counting
        if self.entity_types:
            main_entity_type = self.entity_types[0]
            entity_filter = f"?entity a <{main_entity_type}> ."
        else:
            entity_filter = "?entity a ?type ."
        
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
        
        # Use first entity type for counting
        if self.entity_types:
            main_entity_type = self.entity_types[0]
            entity_filter = f"?entity a <{main_entity_type}> ."
        else:
            entity_filter = "?entity a ?type ."
        
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
        
        # Use first entity type for counting
        if self.entity_types:
            main_entity_type = self.entity_types[0]
            entity_filter = f"?entity a <{main_entity_type}> ."
        else:
            entity_filter = "?entity a ?type ."
        
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
        
        Returns list of dicts with 'property', 'count', and 'sample_value' keys.
        """
        entity_filter = self._get_entity_type_filter()
        
        query = f"""
        SELECT ?property (COUNT(DISTINCT ?entity) as ?count) (SAMPLE(?value) as ?sample_value)
        WHERE {{
            {entity_filter}
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
        
        Returns list of type URIs.
        """
        query = f"""
        SELECT DISTINCT ?type (COUNT(?s) as ?count)
        WHERE {{
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
    
    def generate_suggested_config(self, output_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Generate a suggested configuration based on introspection.
        
        Returns a dict that can be written to YAML.
        """
        print(f"Introspecting {self.graph_id} graph...")
        
        # Discover properties
        print("  Discovering properties...")
        properties = self.introspect_properties(limit=50)
        
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

