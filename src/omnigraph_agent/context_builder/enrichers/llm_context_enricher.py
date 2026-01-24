"""LLM context enricher for adding multi-hop query planning metadata."""

from typing import Dict, List, Optional, Any
from ..model.context_schema import (
    QueryPattern,
    CrossOntologyConnection,
    GlobalContext,
)


class LLMContextEnricher:
    """Enriches context with LLM-optimized metadata for multi-hop query planning."""
    
    # Domain to use case mappings
    DOMAIN_USE_CASES: Dict[str, List[str]] = {
        'biological_process': [
            "Biological process hierarchies and relationships",
            "Pathway analysis and systems biology",
            "Cross-species functional comparison",
        ],
        'molecular_function': [
            "Molecular function classification",
            "Enzyme activity lookup",
            "Protein function annotation",
        ],
        'cellular_component': [
            "Cellular component localization",
            "Subcellular structure relationships",
        ],
        'disease': [
            "Disease name resolution and standardization",
            "Disease classification and hierarchy",
            "Cross-referencing to clinical databases (OMIM, ICD, Orphanet)",
            "Disease-phenotype associations",
            "Rare disease lookup",
        ],
        'phenotype': [
            "Phenotype description",
            "Clinical feature annotation",
            "Phenotype-disease associations",
        ],
        'anatomy': [
            "Anatomical structure relationships",
            "Body part hierarchies",
        ],
        'gene': [
            "Gene function annotation and lookup",
            "Gene-disease associations",
        ],
        'taxonomy': [
            "Organism classification",
            "Species identification",
        ],
    }
    
    # Ontology-specific use cases (overrides domain-based)
    ONTOLOGY_USE_CASES: Dict[str, List[str]] = {
        'go': [
            "Gene function annotation and lookup",
            "Biological process hierarchies and relationships",
            "Molecular function classification",
            "Cellular component localization",
            "Pathway analysis and systems biology",
            "Cross-species functional comparison",
        ],
        'mondo': [
            "Disease name resolution and standardization",
            "Disease classification and hierarchy",
            "Cross-referencing to clinical databases (OMIM, ICD, Orphanet)",
            "Disease-phenotype associations",
            "Rare disease lookup",
        ],
        'hp': [
            "Phenotype description",
            "Clinical feature annotation",
            "Phenotype-disease associations",
        ],
        'ncbitaxon': [
            "Organism classification",
            "Species identification",
            "Taxonomic hierarchy traversal",
        ],
    }
    
    def infer_good_for(self, graph_id: str, domain: Optional[str] = None, obo_metadata: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        Infer use cases (good_for) from ontology domain and structure.
        
        Args:
            graph_id: Graph identifier
            domain: Domain classification from OBO Foundry
            obo_metadata: OBO Foundry metadata
            
        Returns:
            List of use case descriptions
        """
        # Check ontology-specific mappings first
        normalized_id = graph_id.lower()
        if normalized_id in self.ONTOLOGY_USE_CASES:
            return self.ONTOLOGY_USE_CASES[normalized_id]
        
        # Use domain-based inference
        if domain:
            domain_lower = domain.lower()
            for key, use_cases in self.DOMAIN_USE_CASES.items():
                if key in domain_lower:
                    return use_cases
        
        # Fallback: generic ontology use cases
        return [
            "Entity lookup and resolution",
            "Hierarchy traversal",
            "Cross-referencing to external databases",
        ]
    
    def extract_query_patterns(self, graph_id: str, query_hints: Optional[Dict[str, Any]] = None) -> List[QueryPattern]:
        """
        Extract common query patterns from ontology structure.
        
        Args:
            graph_id: Graph identifier
            query_hints: Existing query hints
            
        Returns:
            List of QueryPattern objects
        """
        patterns = []
        
        # Generic patterns for OBO ontologies
        if query_hints and query_hints.get('namespace_scope'):
            # namespace_scope is already "FILTER STRSTARTS(STR(?class), \"IRI\")"; use ?term for this pattern
            ns = query_hints['namespace_scope']
            sparql_hint = ns.replace('?class', '?term') if '?class' in ns else ns
            patterns.append(QueryPattern(
                pattern="Find all terms in namespace",
                description="Filter by namespace scope",
                sparql_hint=sparql_hint,
                note="Use namespace filter early to reduce result set"
            ))
        
        # Hierarchy traversal pattern
        patterns.append(QueryPattern(
            pattern="Find all child terms",
            description="Traverse hierarchy to find more specific terms",
            sparql_hint="?child rdfs:subClassOf+ ?parent .",
            note="Use property paths (rdfs:subClassOf+) for transitive hierarchies"
        ))
        
        # Label lookup pattern
        if query_hints and query_hints.get('label_property'):
            label_prop = query_hints['label_property']
            patterns.append(QueryPattern(
                pattern="Find labels for a term",
                description="Retrieve human-readable labels",
                sparql_hint=f"?term {label_prop} ?label .",
            ))
        
        # Cross-reference pattern
        patterns.append(QueryPattern(
            pattern="Find cross-references to external databases",
            description="Link to external databases (UniProt, Ensembl, etc.)",
            sparql_hint="?term oboInOwl:hasDbXref ?xref .",
        ))
        
        return patterns
    
    def discover_connections(self, graph_id: str, obo_metadata: Optional[Dict[str, Any]] = None) -> List[CrossOntologyConnection]:
        """
        Discover cross-ontology connections for multi-hop queries.
        
        Args:
            graph_id: Graph identifier
            obo_metadata: OBO Foundry metadata (includes imports/dependencies)
            
        Returns:
            List of CrossOntologyConnection objects
        """
        connections = []
        
        if not obo_metadata:
            return connections
        
        # Get imported ontologies
        imports = obo_metadata.get('imports', [])
        for imported_ont in imports:
            connections.append(CrossOntologyConnection(
                ontology=imported_ont.upper(),
                relationship_type="direct import",
                description=f"{graph_id.upper()} imports {imported_ont.upper()}",
                typical_hop_count=1,
            ))
        
        # Add known cross-ontology relationships based on ontology type
        normalized_id = graph_id.lower()
        
        if normalized_id == 'go':
            connections.extend([
                CrossOntologyConnection(
                    ontology="MONDO",
                    relationship_type="indirect via genes",
                    description="Disease-gene associations through shared gene annotations",
                    example_query="Find diseases associated with genes annotated with GO:0006915 (apoptosis)",
                    mechanism="External databases (e.g., DisGeNET) link genes to diseases; genes are annotated with GO terms",
                    typical_hop_count=2,
                    common_use_cases=[
                        "Find diseases linked to a specific biological process",
                        "Identify drugs targeting a pathway implicated in disease",
                    ],
                ),
                CrossOntologyConnection(
                    ontology="HP",
                    relationship_type="indirect via genes",
                    description="Phenotype-gene-function triangulation",
                    example_query="Find phenotypes associated with disruption of GO:0008150 (biological process)",
                    mechanism="Phenotypes (HP) are linked to genes via clinical/model organism data; genes are annotated with GO terms",
                    typical_hop_count=2,
                ),
            ])
        elif normalized_id == 'mondo':
            connections.extend([
                CrossOntologyConnection(
                    ontology="HP",
                    relationship_type="direct import",
                    description="Diseases are associated with phenotypes",
                    example_query="Find phenotypes associated with MONDO:0005015 (diabetes)",
                    mechanism="MONDO imports HP for disease-phenotype axioms",
                    typical_hop_count=1,
                ),
                CrossOntologyConnection(
                    ontology="GO",
                    relationship_type="indirect via genes",
                    description="Disease-gene-function associations",
                    example_query="Find biological processes disrupted in MONDO:0005015 (diabetes)",
                    mechanism="Gene-disease links + GO gene annotations",
                    typical_hop_count=2,
                ),
            ])
        elif normalized_id == 'hp':
            connections.extend([
                CrossOntologyConnection(
                    ontology="MONDO",
                    relationship_type="direct import",
                    description="Phenotypes are associated with diseases",
                    example_query="Find diseases associated with HP:0000001 (abnormality)",
                    mechanism="HP is imported by MONDO for disease-phenotype axioms",
                    typical_hop_count=1,
                ),
            ])
        
        return connections
    
    def enrich_context(self, context: GlobalContext, obo_metadata: Optional[Dict[str, Any]] = None) -> GlobalContext:
        """
        Enrich a GlobalContext with LLM-optimized metadata.
        
        Args:
            context: GlobalContext to enrich
            obo_metadata: Optional OBO Foundry metadata
            
        Returns:
            Enriched GlobalContext
        """
        # Infer good_for use cases
        domain = obo_metadata.get('domain') if obo_metadata else None
        good_for = self.infer_good_for(context.graph_id, domain, obo_metadata)
        
        # Extract query patterns
        query_hints_dict = context.query_hints.model_dump() if context.query_hints else {}
        query_patterns = self.extract_query_patterns(context.graph_id, query_hints_dict)
        
        # Discover cross-ontology connections
        connects_to = self.discover_connections(context.graph_id, obo_metadata)
        
        # Extract domains from OBO metadata
        domains = None
        if obo_metadata and obo_metadata.get('domain'):
            # Parse domain string into list
            domain_str = obo_metadata['domain']
            if domain_str:
                # Simple parsing - could be enhanced
                domains = [d.strip() for d in domain_str.split(',') if d.strip()]
        
        # Create enriched context (update existing context)
        context.good_for = good_for
        context.query_patterns = query_patterns if query_patterns else None
        context.connects_to = connects_to if connects_to else None
        context.domains = domains
        
        return context
