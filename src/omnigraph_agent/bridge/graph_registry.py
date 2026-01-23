"""Graph registry for managing FRINK registry graphs."""

import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from ..context_builder.model.context_schema import GlobalContext
from .semantic_mappings import are_semantically_related, get_category


class GraphRegistry:
    """Manages graph registry and context file loading."""
    
    # List of known FRINK registry graphs (can be extended)
    FRINK_GRAPHS = [
        "nde",
        "biobricks-aopwiki",
        "biobricks-ice",
        "biobricks-mesh",
        "biobricks-pubchem-annotations",
        "biobricks-tox21",
        "biobricks-toxcast",
        "biohealth",
        "climatemodelskg",
        "dreamkg",
        "fiokg",
        "geoconnex",
        "hydrologykg",
        "identifier-mappings",
        "nasa-gesdisc-kg",
        "nikg",
        "ruralkg",
        "sawgraph",
        "scales",
        "securechainkg",
        "semopenalex",
        "sockg",
        "spatialkg",
        "spoke-genelab",
        "spoke-okn",
        "sudokn",
        "ubergraph",
        "ufokn",
        "wikidata",
        "wildlifekn",
    ]
    
    def __init__(self, context_dir: Path):
        """
        Initialize graph registry.
        
        Args:
            context_dir: Directory containing context JSON files
        """
        self.context_dir = context_dir
    
    def list_available_graphs(self) -> List[str]:
        """
        List all graphs that have context files available.
        
        Includes both FRINK registry graphs and any other graphs with context files
        (e.g., ontologies like mondo, vbo).
        
        Returns:
            List of graph IDs
        """
        available = []
        
        # First, check FRINK registry graphs
        for graph_id in self.FRINK_GRAPHS:
            context_file = self.context_dir / f"{graph_id}_global.json"
            if context_file.exists():
                available.append(graph_id)
        
        # Also discover any other context files (e.g., ontologies)
        for context_file in self.context_dir.glob("*_global.json"):
            graph_id = context_file.stem.replace('_global', '')
            if graph_id not in available:
                available.append(graph_id)
        
        return sorted(available)
    
    def load_context(self, graph_id: str) -> Optional[GlobalContext]:
        """
        Load context file for a graph.
        
        Args:
            graph_id: Graph identifier
        
        Returns:
            GlobalContext or None if not found
        """
        context_file = self.context_dir / f"{graph_id}_global.json"
        if not context_file.exists():
            return None
        
        with open(context_file, 'r') as f:
            data = json.load(f)
            return GlobalContext(**data)
    
    def get_graph_pairs(self) -> List[tuple]:
        """
        Get all possible graph pairs.
        
        Returns:
            List of (source_graph_id, target_graph_id) tuples
        """
        available = self.list_available_graphs()
        pairs = []
        for i, source in enumerate(available):
            for target in available[i+1:]:
                pairs.append((source, target))
        return pairs
    
    def find_pairs_with_shared_join_keys(self, include_semantic: bool = True) -> List[Tuple[str, str, List[str], List[str]]]:
        """
        Find graph pairs that share at least one join key type.
        
        Args:
            include_semantic: If True, also include pairs with semantically related identifiers
                            (e.g., UniProt taxon and NCBITaxon)
        
        Returns:
            List of (source_graph_id, target_graph_id, [exact_shared_keys], [semantic_shared_keys]) tuples
        """
        pairs_with_keys = []
        available = self.list_available_graphs()
        
        for i, source_id in enumerate(available):
            source_context = self.load_context(source_id)
            if not source_context or not source_context.identifier_info:
                continue
            
            source_prefixes = {p.prefix: p for p in source_context.identifier_info.patterns}
            
            for target_id in available[i+1:]:
                target_context = self.load_context(target_id)
                if not target_context or not target_context.identifier_info:
                    continue
                
                target_prefixes = {p.prefix: p for p in target_context.identifier_info.patterns}
                
                # Find exact matches
                exact_shared = list(source_prefixes.keys() & target_prefixes.keys())
                
                # Find semantically related matches
                semantic_shared = []
                if include_semantic:
                    for source_prefix, source_pattern in source_prefixes.items():
                        for target_prefix, target_pattern in target_prefixes.items():
                            if source_prefix != target_prefix:
                                # Check if semantically related
                                if are_semantically_related(source_prefix, target_prefix):
                                    # Use source prefix as the canonical one
                                    semantic_shared.append(source_prefix)
                
                if exact_shared or semantic_shared:
                    # Deduplicate semantic matches
                    semantic_keys = list(set(semantic_shared))
                    pairs_with_keys.append((source_id, target_id, exact_shared, semantic_keys))
        
        return pairs_with_keys

