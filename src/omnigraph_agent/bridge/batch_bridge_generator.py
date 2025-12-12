"""Batch bridge generator for processing all graph pairs."""

import json
from pathlib import Path
from typing import List, Dict, Tuple
from .graph_registry import GraphRegistry
from .linkset_builder import LinksetBuilder


class BatchBridgeGenerator:
    """Generates linksets for all graph pairs with shared join keys."""
    
    def __init__(self, context_dir: Path, output_dir: Path):
        """
        Initialize batch bridge generator.
        
        Args:
            context_dir: Directory containing context JSON files
            output_dir: Directory to write linkset RDF files
        """
        self.context_dir = context_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.registry = GraphRegistry(context_dir)
    
    def discover_all_linksets(self, include_semantic: bool = True) -> List[Tuple[str, str, List[str], List[str]]]:
        """
        Discover all graph pairs that share join keys.
        
        Args:
            include_semantic: If True, also include pairs with semantically related identifiers
        
        Returns:
            List of (source_graph, target_graph, [exact_shared_keys], [semantic_shared_keys]) tuples
        """
        return self.registry.find_pairs_with_shared_join_keys(include_semantic=include_semantic)
    
    def generate_all_linksets(self, verbose: bool = True) -> Dict[str, Path]:
        """
        Generate linksets for all graph pairs with shared join keys.
        
        Args:
            verbose: Whether to print progress messages
        
        Returns:
            Dict mapping linkset identifier to output file path
        """
        pairs_with_keys = self.discover_all_linksets(include_semantic=True)
        
        if verbose:
            print(f"Found {len(pairs_with_keys)} graph pairs with shared join keys")
        
        generated_files = {}
        
        for source_id, target_id, exact_keys, semantic_keys in pairs_with_keys:
            all_keys = exact_keys + semantic_keys
            if verbose:
                key_info = []
                if exact_keys:
                    key_info.append(f"exact: {', '.join(exact_keys)}")
                if semantic_keys:
                    key_info.append(f"semantic: {', '.join(semantic_keys)}")
                print(f"\nProcessing {source_id} → {target_id} ({'; '.join(key_info)})")
            
            source_context_path = self.context_dir / f"{source_id}_global.json"
            target_context_path = self.context_dir / f"{target_id}_global.json"
            
            if not source_context_path.exists() or not target_context_path.exists():
                if verbose:
                    print(f"  Warning: Context files not found, skipping")
                continue
            
            try:
                builder = LinksetBuilder(source_context_path, target_context_path)
                
                # Generate linkset for each shared join key (exact and semantic)
                for join_key_prefix in all_keys:
                    try:
                        if verbose:
                            print(f"  Generating linkset for {join_key_prefix}...")
                        
                        linkset_graph = builder.build_linkset(join_key_prefix)
                        
                        # Write to file
                        linkset_filename = f"{source_id}__{target_id}-{join_key_prefix.lower()}.ttl"
                        linkset_path = self.output_dir / linkset_filename
                        
                        linkset_graph.serialize(destination=str(linkset_path), format='turtle')
                        
                        # Count links
                        link_count = len(list(linkset_graph.triples((None, None, None)))) // 9  # Approximate
                        
                        if verbose:
                            print(f"    Generated {linkset_filename} ({link_count} links)")
                        
                        linkset_id = f"{source_id}__{target_id}-{join_key_prefix.lower()}"
                        generated_files[linkset_id] = linkset_path
                    
                    except Exception as e:
                        if verbose:
                            print(f"    Error generating linkset for {join_key_prefix}: {e}")
                        continue
            
            except Exception as e:
                if verbose:
                    print(f"  Error processing {source_id} → {target_id}: {e}")
                continue
        
        if verbose:
            print(f"\n✓ Generated {len(generated_files)} linkset files")
        
        return generated_files

