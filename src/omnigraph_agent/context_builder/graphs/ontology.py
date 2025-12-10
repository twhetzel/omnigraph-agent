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
    
    def _introspect_namespace_properties(
        self,
        namespace_iri: str,
        namespace_prefix: str,
        id_extractor: callable,
        id_key: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Helper method to introspect properties within a specific namespace.
        
        Uses named graph (FROM clause) if available, otherwise falls back to
        namespace filtering for efficiency on multi-ontology endpoints like Ubergraph.
        
        Args:
            namespace_iri: Full namespace IRI to filter by (e.g., "http://www.geneontology.org/formats/oboInOwl#")
            namespace_prefix: SPARQL prefix declaration (e.g., "oboInOwl:")
            id_extractor: Function to extract ID from property URI (e.g., lambda uri: uri.split('#')[-1])
            id_key: Key name for the extracted ID in result dict (e.g., "short_name" or "ro_id")
            limit: Maximum number of properties to return
            
        Returns:
            List of dicts with 'property', 'count', and the specified id_key
        """
        entity_filter = self._get_entity_type_filter(entity_var="?class")
        graph_clause = self._get_graph_clause()  # FROM <graph_uri> if available
        namespace_filter = self._get_namespace_filter(entity_var="?class")  # FILTER by namespace if no named graph
        
        query = f"""
        PREFIX {namespace_prefix} <{namespace_iri}>
        {graph_clause}SELECT ?prop (COUNT(DISTINCT ?class) as ?count)
        WHERE {{
            {entity_filter}
            {namespace_filter}
            ?class ?prop ?value .
            FILTER STRSTARTS(STR(?prop), "{namespace_iri}")
        }}
        GROUP BY ?prop
        ORDER BY DESC(?count)
        LIMIT {limit}
        """
        
        self.sparql.setQuery(query)
        results = self.sparql.query().convert()
        
        properties = []
        for binding in results['results']['bindings']:
            prop_uri = binding['prop']['value']
            count = int(binding['count']['value'])
            extracted_id = id_extractor(prop_uri)
            
            properties.append({
                'property': prop_uri,
                id_key: extracted_id,
                'count': count
            })
        
        return properties
    
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
        return self._introspect_namespace_properties(
            namespace_iri="http://www.geneontology.org/formats/oboInOwl#",
            namespace_prefix="oboInOwl:",
            id_extractor=lambda uri: uri.split('#')[-1] if '#' in uri else uri.split('/')[-1],
            id_key="short_name",
            limit=limit
        )
    
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
        return self._introspect_namespace_properties(
            namespace_iri="http://purl.obolibrary.org/obo/RO_",
            namespace_prefix="RO:",
            id_extractor=lambda uri: uri.split('_')[-1] if '_' in uri else uri.split('/')[-1],
            id_key="ro_id",
            limit=limit
        )
    
    def introspect_axiom_annotations(self, limit: int = 15) -> List[Dict[str, Any]]:
        """
        Introspect to discover annotation properties used on owl:Axiom instances.
        
        This discovers what types of annotations are attached to axioms (e.g., 
        oboInOwl:hasDbXref on synonym axioms for provenance).
        
        Uses named graph (FROM clause) if available, otherwise falls back to
        namespace filtering for efficiency on multi-ontology endpoints like Ubergraph.
        
        Note: This query may timeout on large ontologies. Consider using a smaller
        limit or running on a subset of the ontology.
        
        Args:
            limit: Maximum number of annotation properties to return
            
        Returns:
            List of dicts with 'property', 'count', and 'short_name' keys
        """
        graph_clause = self._get_graph_clause()  # FROM <graph_uri> if available
        namespace_filter = self._get_namespace_filter(entity_var="?class")  # FILTER by namespace if no named graph
        
        query = f"""
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        {graph_clause}SELECT DISTINCT ?annot_prop (COUNT(DISTINCT ?axiom) as ?count)
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
    
    def introspect_owl_restrictions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Introspect to discover OWL restrictions that use OBO ontology properties.
        
        This discovers patterns like:
        - Gene associations: ?class rdfs:subClassOf [ owl:onProperty RO:0004003 ; owl:someValuesFrom ?gene ]
        - Disease-phenotype: ?class rdfs:subClassOf [ owl:onProperty RO:0002200 ; owl:someValuesFrom ?phenotype ]
        - Part-of: ?class rdfs:subClassOf [ owl:onProperty BFO:0000050 ; owl:someValuesFrom ?part ]
        - Any OBO ontology property used in restrictions
        
        Uses named graph (FROM clause) if available, otherwise falls back to
        namespace filtering for efficiency on multi-ontology endpoints like Ubergraph.
        
        Args:
            limit: Maximum number of restriction properties to return
            
        Returns:
            List of dicts with 'property', 'ontology_prefix', 'property_id', 'count', and 'restriction_type' keys
        """
        graph_clause = self._get_graph_clause()
        namespace_filter = self._get_namespace_filter(entity_var="?class")
        
        query = f"""
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        {graph_clause}SELECT ?obo_prop (COUNT(DISTINCT ?class) as ?count) (SAMPLE(?quantifier) as ?sample_quant)
        WHERE {{
            {namespace_filter}
            ?class rdfs:subClassOf ?restriction .
            ?restriction a owl:Restriction .
            ?restriction owl:onProperty ?obo_prop .
            OPTIONAL {{
                ?restriction ?quantifier ?value .
                FILTER(?quantifier IN (owl:someValuesFrom, owl:allValuesFrom, owl:hasValue, owl:cardinality, owl:minCardinality, owl:maxCardinality))
            }}
            FILTER (
                STRSTARTS(STR(?obo_prop), "http://purl.obolibrary.org/obo/") &&
                REGEX(STR(?obo_prop), "^http://purl.obolibrary.org/obo/[A-Z]+_[0-9]+")
            )
        }}
        GROUP BY ?obo_prop
        ORDER BY DESC(?count)
        LIMIT {limit}
        """
        
        try:
            self.sparql.setQuery(query)
            results = self.sparql.query().convert()
            
            restrictions = []
            for binding in results['results']['bindings']:
                prop_uri = binding['obo_prop']['value']
                count = int(binding['count']['value'])
                sample_quant = binding.get('sample_quant', {}).get('value', '')
                
                # Extract ontology prefix and property ID (e.g., "RO", "0004003" from "http://purl.obolibrary.org/obo/RO_0004003")
                # Pattern: http://purl.obolibrary.org/obo/{PREFIX}_{ID}
                if '/obo/' in prop_uri and '_' in prop_uri:
                    parts = prop_uri.split('/obo/')[-1].split('_', 1)
                    ontology_prefix = parts[0] if len(parts) > 0 else ''
                    property_id = parts[1] if len(parts) > 1 else ''
                else:
                    ontology_prefix = ''
                    property_id = ''
                
                # Determine restriction type based on quantifier
                restriction_type = 'someValuesFrom'  # default
                if sample_quant:
                    if 'someValuesFrom' in sample_quant or 'owl:someValuesFrom' in sample_quant:
                        restriction_type = 'someValuesFrom'
                    elif 'allValuesFrom' in sample_quant or 'owl:allValuesFrom' in sample_quant:
                        restriction_type = 'allValuesFrom'
                    elif 'hasValue' in sample_quant or 'owl:hasValue' in sample_quant:
                        restriction_type = 'hasValue'
                
                restrictions.append({
                    'property': prop_uri,
                    'ontology_prefix': ontology_prefix,
                    'property_id': property_id,
                    'count': count,
                    'restriction_type': restriction_type
                })
            
            return restrictions
        except Exception as e:
            # Query may timeout on large ontologies - return empty list
            print(f"  Warning: OWL restriction introspection timed out or failed: {e}")
            return []
    
    def _get_obo_pattern_name(self, ontology_prefix: str, property_id: str) -> Optional[str]:
        """
        Map common OBO ontology property IDs to semantic pattern names.
        
        Args:
            ontology_prefix: Ontology prefix (e.g., "RO", "BFO", "IAO")
            property_id: Property ID (e.g., "0004003", "0000050")
            
        Returns:
            Pattern name (e.g., "gene_association", "part_of") or None if unknown
        """
        # RO (Relations Ontology) property mappings
        if ontology_prefix == "RO":
            ro_pattern_map = {
                "0004003": "gene_association",  # has germline mutation
                "0002200": "phenotype_association",  # has phenotype
                "0003302": "drug_association",  # has drug
                "0003301": "treatment_association",  # has treatment
                "0003303": "disease_association",  # has disease
                "0002606": "part_of",  # part of
                "0002201": "located_in",  # located in
                "0002202": "has_part",  # has part
                "0002203": "has_quality",  # has quality
                "0002204": "inheres_in",  # inheres in
                "0002205": "bearer_of",  # bearer of
                "0002206": "has_characteristic",  # has characteristic
                "0002207": "has_disposition",  # has disposition
                "0002208": "realizes",  # realizes
                "0002209": "has_function",  # has function
                "0002210": "has_role",  # has role
                "0002211": "participates_in",  # participates in
                "0002212": "has_participant",  # has participant
                "0002213": "causes",  # causes
                "0002214": "caused_by",  # caused by
                "0002215": "precedes",  # precedes
                "0002216": "has_input",  # has input
                "0002217": "has_output",  # has output
                "0002218": "regulates",  # regulates
                "0002219": "negatively_regulates",  # negatively regulates
                "0002220": "positively_regulates",  # positively regulates
            }
            return ro_pattern_map.get(property_id)
        
        # BFO (Basic Formal Ontology) property mappings
        elif ontology_prefix == "BFO":
            bfo_pattern_map = {
                "0000050": "part_of",  # part of
                "0000051": "has_part",  # has part
                "0000066": "located_in",  # located in
                "0000068": "contains",  # contains
                "0000062": "preceded_by",  # preceded by
                "0000063": "precedes",  # precedes
                "0000067": "located_at",  # located at
                "0000069": "occupies",  # occupies
                "0000070": "occupies_spatial_region",  # occupies spatial region
                "0000071": "has_function",  # has function
                "0000072": "has_role",  # has role
                "0000073": "has_disposition",  # has disposition
                "0000074": "has_quality",  # has quality
                "0000075": "has_process_part",  # has process part
                "0000076": "has_continuant_part",  # has continuant part
                "0000077": "has_occurrent_part",  # has occurrent part
            }
            return bfo_pattern_map.get(property_id)
        
        # IAO (Information Artifact Ontology) property mappings
        elif ontology_prefix == "IAO":
            iao_pattern_map = {
                "0000136": "is_about",  # is about
                "0000137": "denotes",  # denotes
                "0000138": "represents",  # represents
                "0000139": "has_part",  # has part
                "0000140": "part_of",  # part of
            }
            return iao_pattern_map.get(property_id)
        
        # For other ontologies, return None (will use generic pattern name)
        return None
    
    def generate_query_hints(self) -> Optional[Dict[str, Any]]:
        """
        Generate query hints for ontology context files based on introspection.
        
        Returns:
            Dictionary with query hints or None if generation fails
        """
        from ..model.context_schema import QueryGenerationHints
        
        hints = {}
        
        # Generate namespace_scope from namespace_scope config or namespace
        if self.namespace_scope:
            hints['namespace_scope'] = f'FILTER STRSTARTS(STR(?class), "{self.namespace_scope}")'
        
        # Default reasoning mode for ontologies
        hints['reasoning_mode'] = "no entailment; use explicit patterns and property paths (e.g., rdfs:subClassOf*)"
        
        # Default to exclude obsoletes
        hints['exclude_obsoletes'] = True
        
        # Standard label and definition properties for OBO ontologies
        hints['label_property'] = "rdfs:label"
        hints['definition_property'] = "IAO:0000115"
        
        # Generate query patterns based on introspection
        query_patterns = {}
        
        # Try to introspect OBO annotations to build patterns
        try:
            obo_annotations = self.introspect_obo_annotations(limit=10)
            for ann in obo_annotations:
                short_name = ann.get('short_name', '')
                if short_name == 'hasExactSynonym':
                    query_patterns['axiom_annotated_synonym'] = (
                        "?class oboInOwl:hasExactSynonym ?syn . "
                        "?axiom a owl:Axiom ; owl:annotatedSource ?class ; "
                        "owl:annotatedProperty oboInOwl:hasExactSynonym ; owl:annotatedTarget ?syn ."
                    )
                    query_patterns['direct_synonym'] = "?class oboInOwl:hasExactSynonym ?syn ."
                elif short_name == 'hasDbXref':
                    query_patterns['axiom_annotated_xref'] = (
                        "?class oboInOwl:hasDbXref ?xref . "
                        "?axiom a owl:Axiom ; owl:annotatedSource ?class ; "
                        "owl:annotatedProperty oboInOwl:hasDbXref ; owl:annotatedTarget ?xref ."
                    )
                    query_patterns['direct_xref'] = "?class oboInOwl:hasDbXref ?xref ."
                elif short_name == 'inSubset':
                    query_patterns['in_subset'] = "?class oboInOwl:inSubset ?subset ."
        except Exception:
            # If introspection fails, use default patterns
            pass
        
        # Try to introspect relations (direct properties)
        try:
            relations = self.introspect_relations(limit=5)
            for rel in relations:
                ro_id = rel.get('ro_id', '')
                if ro_id:
                    # Add relation pattern using prefix (e.g., RO:0020105 for "related_to")
                    # Use RO: prefix if available, otherwise use full IRI
                    if ro_id.isdigit():
                        query_patterns['related_to'] = f"?class RO:{ro_id} ?related ."
                    else:
                        prop_uri = rel.get('property', '')
                        if prop_uri:
                            query_patterns['related_to'] = f"?class {prop_uri} ?related ."
        except Exception:
            pass
        
        # Try to introspect axiom annotations to find ontology-specific properties
        try:
            axiom_annotations = self.introspect_axiom_annotations(limit=20)
            # Extract ontology prefix from namespace_scope if available
            ontology_prefix = None
            if self.namespace_scope and "purl.obolibrary.org/obo/" in self.namespace_scope:
                parts = self.namespace_scope.split("/obo/")
                if len(parts) > 1:
                    ontology_prefix = parts[1].rstrip("_").upper()
            
            for ann in axiom_annotations:
                prop_uri = ann.get('property', '')
                short_name = ann.get('short_name', '')
                count = ann.get('count', 0)
                
                # Check if this property is from the ontology's own namespace
                if ontology_prefix and prop_uri.startswith(f"http://purl.obolibrary.org/obo/{ontology_prefix}_"):
                    # Extract property ID
                    if f"{ontology_prefix}_" in prop_uri:
                        prop_id = prop_uri.split(f"{ontology_prefix}_")[-1]
                        # Generate pattern for ontology-specific axiom annotation
                        pattern_name = f"{ontology_prefix.lower()}_axiom_{prop_id}"
                        pattern = (
                            f"?class ?prop ?value . "
                            f"?axiom a owl:Axiom ; owl:annotatedSource ?class ; "
                            f"owl:annotatedProperty {ontology_prefix}:{prop_id} ; owl:annotatedTarget ?value ."
                        )
                        query_patterns[pattern_name] = pattern
                        
                        # Also add direct pattern if it's commonly used
                        if count > 10:  # Threshold for direct pattern
                            direct_pattern_name = f"{ontology_prefix.lower()}_{prop_id}"
                            query_patterns[direct_pattern_name] = f"?class {ontology_prefix}:{prop_id} ?value ."
        except Exception as e:
            # If introspection fails, continue without axiom annotation patterns
            print(f"  Warning: Failed to process axiom annotations: {e}")
            pass
        
        # Try to introspect OWL restrictions (axiomatized patterns)
        try:
            restrictions = self.introspect_owl_restrictions(limit=20)
            for restriction in restrictions:
                ontology_prefix = restriction.get('ontology_prefix', '')
                property_id = restriction.get('property_id', '')
                restriction_type = restriction.get('restriction_type', 'someValuesFrom')
                
                if ontology_prefix and property_id:
                    # Get semantic pattern name if available
                    pattern_name = self._get_obo_pattern_name(ontology_prefix, property_id)
                    
                    # Generate appropriate SPARQL pattern based on restriction type
                    if restriction_type == 'someValuesFrom':
                        # Most common: someValuesFrom (e.g., gene associations)
                        var_name = pattern_name.split('_')[0] if pattern_name else 'related'
                        # Use ontology prefix in pattern (e.g., RO:0004003, BFO:0000050)
                        pattern = f"?class rdfs:subClassOf [ a owl:Restriction ; owl:onProperty {ontology_prefix}:{property_id} ; owl:someValuesFrom ?{var_name} ] ."
                        
                        if pattern_name:
                            query_patterns[pattern_name] = pattern
                        else:
                            # Generic pattern name using ontology prefix
                            query_patterns[f'{ontology_prefix.lower()}_{property_id}'] = pattern
                    elif restriction_type == 'allValuesFrom':
                        var_name = pattern_name.split('_')[0] if pattern_name else 'related'
                        pattern = f"?class rdfs:subClassOf [ a owl:Restriction ; owl:onProperty {ontology_prefix}:{property_id} ; owl:allValuesFrom ?{var_name} ] ."
                        
                        if pattern_name:
                            query_patterns[f'{pattern_name}_all'] = pattern
                        else:
                            query_patterns[f'{ontology_prefix.lower()}_all_{property_id}'] = pattern
                    elif restriction_type == 'hasValue':
                        var_name = pattern_name.split('_')[0] if pattern_name else 'value'
                        pattern = f"?class rdfs:subClassOf [ a owl:Restriction ; owl:onProperty {ontology_prefix}:{property_id} ; owl:hasValue ?{var_name} ] ."
                        
                        if pattern_name:
                            query_patterns[f'{pattern_name}_value'] = pattern
                        else:
                            query_patterns[f'{ontology_prefix.lower()}_value_{property_id}'] = pattern
        except Exception as e:
            # If introspection fails, continue without restriction patterns
            print(f"  Warning: Failed to generate restriction patterns: {e}")
            pass
        
        if query_patterns:
            hints['query_patterns'] = query_patterns
        
        # Default behaviors
        hints['default_behaviors'] = {
            "consider_descendants": True,
            "sort_results": True,
            "use_distinct": True
        }
        
        # Output rules
        hints['output_rules'] = {
            "extension_mode_token": "EXTENSION_MODE",
            "extension_mode_format": "plain_text_no_backticks",
            "normal_mode_format": "fenced_code_block_sparql"
        }
        
        try:
            return QueryGenerationHints(**hints).model_dump(exclude_none=True)
        except Exception as e:
            print(f"  Warning: Failed to generate query hints: {e}")
            return None

