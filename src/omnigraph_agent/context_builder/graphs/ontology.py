"""
Base class for ontology graph handlers.

Ontologies are single-source knowledge structures (e.g., MONDO, VBO)
that don't have multiple data repositories/catalogs.
"""

from typing import List, Dict, Any, Optional
from .base import BaseGraph


class OntologyGraph(BaseGraph):
    """Base class for ontology graph handlers."""
    
    def get_repositories(self) -> List[Dict[str, str]]:
        """
        Ontologies are single-source and don't have data repositories.
        Returns empty list.
        """
        return []
    
    def introspect_obo_annotations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Introspect to discover OBO annotation properties used in the ontology.
        
        Discovers properties from the oboInOwl namespace (e.g., hasExactSynonym,
        hasDbXref, inSubset) that are commonly used for ontology annotations.
        
        Args:
            limit: Maximum number of properties to return
            
        Returns:
            List of dicts with 'property', 'count', and 'short_name' keys
        """
        entity_filter = self._get_entity_type_filter()
        
        query = f"""
        PREFIX oboInOwl: <http://www.geneontology.org/formats/oboInOwl#>
        
        SELECT ?prop (COUNT(DISTINCT ?class) as ?count)
        WHERE {{
            {entity_filter}
            ?class ?prop ?value .
            FILTER STRSTARTS(STR(?prop), "http://www.geneontology.org/formats/oboInOwl#")
        }}
        GROUP BY ?prop
        ORDER BY DESC(?count)
        LIMIT {limit}
        """
        
        self.sparql.setQuery(query)
        results = self.sparql.query().convert()
        
        annotations = []
        for binding in results['results']['bindings']:
            prop_uri = binding['prop']['value']
            count = int(binding['count']['value'])
            # Extract short name (e.g., "hasExactSynonym" from full IRI)
            short_name = prop_uri.split('#')[-1] if '#' in prop_uri else prop_uri.split('/')[-1]
            
            annotations.append({
                'property': prop_uri,
                'short_name': short_name,
                'count': count
            })
        
        return annotations
    
    def introspect_relations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Introspect to discover relation properties (RO properties) used in the ontology.
        
        Discovers properties from the RO (Relations Ontology) namespace that are
        used to relate ontology classes.
        
        Args:
            limit: Maximum number of relations to return
            
        Returns:
            List of dicts with 'property', 'count', and 'ro_id' keys
        """
        entity_filter = self._get_entity_type_filter()
        
        query = f"""
        PREFIX RO: <http://purl.obolibrary.org/obo/RO_>
        
        SELECT ?prop (COUNT(DISTINCT ?class) as ?count)
        WHERE {{
            {entity_filter}
            ?class ?prop ?value .
            FILTER STRSTARTS(STR(?prop), "http://purl.obolibrary.org/obo/RO_")
        }}
        GROUP BY ?prop
        ORDER BY DESC(?count)
        LIMIT {limit}
        """
        
        self.sparql.setQuery(query)
        results = self.sparql.query().convert()
        
        relations = []
        for binding in results['results']['bindings']:
            prop_uri = binding['prop']['value']
            count = int(binding['count']['value'])
            # Extract RO ID (e.g., "0020105" from "http://purl.obolibrary.org/obo/RO_0020105")
            ro_id = prop_uri.split('_')[-1] if '_' in prop_uri else prop_uri.split('/')[-1]
            
            relations.append({
                'property': prop_uri,
                'ro_id': ro_id,
                'count': count
            })
        
        return relations
    
    def introspect_axiom_annotations(self, limit: int = 15) -> List[Dict[str, Any]]:
        """
        Introspect to discover annotation properties used on owl:Axiom instances.
        
        This discovers what types of annotations are attached to axioms (e.g., 
        oboInOwl:hasDbXref on synonym axioms for provenance).
        
        Note: This query may timeout on large ontologies. Consider using a smaller
        limit or running on a subset of the ontology.
        
        Args:
            limit: Maximum number of annotation properties to return
            
        Returns:
            List of dicts with 'property', 'count', and 'short_name' keys
        """
        # Use namespace scope if available in config
        namespace_filter = ""
        if hasattr(self, 'graph_id') and self.graph_id:
            # Try to infer namespace from graph_id (e.g., "vbo" -> "VBO_")
            namespace_iri = f"http://purl.obolibrary.org/obo/{self.graph_id.upper()}_"
            namespace_filter = f'FILTER STRSTARTS(STR(?class), "{namespace_iri}")'
        
        query = f"""
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        
        SELECT DISTINCT ?annot_prop (COUNT(DISTINCT ?axiom) as ?count)
        WHERE {{
            ?axiom a owl:Axiom .
            ?axiom owl:annotatedSource ?class .
            {namespace_filter}
            ?axiom ?annot_prop ?value .
            FILTER(?annot_prop != owl:annotatedSource && 
                   ?annot_prop != owl:annotatedProperty && 
                   ?annot_prop != owl:annotatedTarget)
        }}
        GROUP BY ?annot_prop
        ORDER BY DESC(?count)
        LIMIT {limit}
        """
        
        try:
            self.sparql.setQuery(query)
            results = self.sparql.query().convert()
            
            annotations = []
            for binding in results['results']['bindings']:
                prop_uri = binding['annot_prop']['value']
                count = int(binding['count']['value'])
                # Extract short name
                short_name = prop_uri.split('#')[-1] if '#' in prop_uri else prop_uri.split('/')[-1]
                
                annotations.append({
                    'property': prop_uri,
                    'short_name': short_name,
                    'count': count
                })
            
            return annotations
        except Exception as e:
            # Query may timeout on large ontologies - return empty list
            print(f"  Warning: Axiom annotation introspection timed out or failed: {e}")
            return []

