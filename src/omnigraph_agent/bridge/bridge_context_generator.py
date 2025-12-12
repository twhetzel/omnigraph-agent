"""Bridge context generator for creating JSON summaries of linksets."""

import json
from pathlib import Path
from typing import Dict, List, Optional
from rdflib import Graph
from rdflib.namespace import RDF

from .bridge_context_schema import BridgeContext, LinksetSummary
from .graph_registry import GraphRegistry

WOBDBRIDGE = "https://wobd.org/bridge#"


class BridgeContextGenerator:
    """Generates bridge context JSON files from linkset RDF files."""
    
    def __init__(self, linkset_dir: Path, context_dir: Path, output_dir: Path):
        """
        Initialize bridge context generator.
        
        Args:
            linkset_dir: Directory containing linkset RDF files
            context_dir: Directory containing graph context JSON files
            output_dir: Directory to write bridge context JSON files
        """
        self.linkset_dir = linkset_dir
        self.context_dir = context_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.registry = GraphRegistry(context_dir)
    
    def generate_bridge_context(self, source_id: str, target_id: str) -> Optional[BridgeContext]:
        """
        Generate bridge context for a graph pair.
        
        Args:
            source_id: Source graph identifier
            target_id: Target graph identifier
        
        Returns:
            BridgeContext or None if no linksets found
        """
        # Load graph contexts
        source_context = self.registry.load_context(source_id)
        target_context = self.registry.load_context(target_id)
        
        if not source_context or not target_context:
            return None
        
        # Find all linkset files for this pair
        linkset_files = list(self.linkset_dir.glob(f"{source_id}__{target_id}-*.ttl"))
        
        if not linkset_files:
            return None
        
        linksets = []
        
        for linkset_file in linkset_files:
            try:
                # Parse linkset file
                g = Graph()
                g.parse(str(linkset_file), format='turtle')
                
                # Extract linkset IRI and statistics
                linkset_iri = None
                link_count = 0
                confidences = []
                
                # Find linkset IRI (subject of type void:Linkset)
                for s, p, o in g.triples((None, RDF.type, None)):
                    if str(o).endswith("#Linkset") or "void:Linkset" in str(o):
                        linkset_iri = str(s)
                        break
                
                if not linkset_iri:
                    # Try to extract from filename
                    linkset_iri = f"https://wobd.org/bridge/linkset/{linkset_file.stem}"
                
                # Count link assertions and collect confidences
                # Find all LinkAssertion instances (subjects with type wobd-bridge:LinkAssertion)
                
                link_assertions = set()
                for s, p, o in g.triples((None, RDF.type, None)):
                    if str(o) == f"{WOBDBRIDGE}LinkAssertion" or str(o).endswith("#LinkAssertion"):
                        link_assertions.add(s)
                        link_count += 1
                
                # Collect confidences from link assertions
                for link_assertion in link_assertions:
                    for s, p, o in g.triples((link_assertion, None, None)):
                        if str(p).endswith("#confidence") or "confidence" in str(p):
                            try:
                                confidences.append(float(str(o)))
                            except (ValueError, TypeError):
                                pass
                
                # Extract join key type from filename
                filename = linkset_file.stem
                # Format: source__target-joinkey
                parts = filename.split('-', 1)
                if len(parts) == 2:
                    join_key_prefix = parts[1].upper()
                    join_key_type = f"{join_key_prefix}_ID"
                else:
                    join_key_type = "UNKNOWN"
                
                # Calculate confidence range
                min_confidence = min(confidences) if confidences else 1.0
                max_confidence = max(confidences) if confidences else 1.0
                
                linksets.append(LinksetSummary(
                    join_key_type=join_key_type,
                    num_links=link_count,
                    min_confidence=min_confidence,
                    max_confidence=max_confidence,
                    linkset_iri=linkset_iri
                ))
            
            except Exception as e:
                print(f"  Warning: Failed to process {linkset_file}: {e}")
                continue
        
        if not linksets:
            return None
        
        return BridgeContext(
            source_graph=source_context.endpoint,
            target_graph=target_context.endpoint,
            source_graph_id=source_id,
            target_graph_id=target_id,
            linksets=linksets
        )
    
    def generate_all_bridge_contexts(self, verbose: bool = True) -> Dict[str, Path]:
        """
        Generate bridge context files for all graph pairs with linksets.
        
        Args:
            verbose: Whether to print progress messages
        
        Returns:
            Dict mapping bridge identifier to output file path
        """
        # Find all unique graph pairs from linkset filenames
        linkset_files = list(self.linkset_dir.glob("*.ttl"))
        
        graph_pairs = set()
        for linkset_file in linkset_files:
            # Format: source__target-joinkey.ttl
            filename = linkset_file.stem
            if '__' in filename:
                parts = filename.split('__', 1)
                if len(parts) == 2:
                    source_id = parts[0]
                    target_part = parts[1].split('-', 1)[0]
                    graph_pairs.add((source_id, target_part))
        
        if verbose:
            print(f"Found {len(graph_pairs)} graph pairs with linksets")
        
        generated_files = {}
        
        for source_id, target_id in graph_pairs:
            if verbose:
                print(f"Generating bridge context for {source_id} → {target_id}...")
            
            bridge_context = self.generate_bridge_context(source_id, target_id)
            
            if bridge_context:
                output_file = self.output_dir / f"{source_id}__{target_id}.json"
                
                with open(output_file, 'w') as f:
                    json.dump(bridge_context.model_dump(exclude_none=True), f, indent=2)
                
                if verbose:
                    print(f"  Generated {output_file.name} ({len(bridge_context.linksets)} linksets)")
                
                bridge_id = f"{source_id}__{target_id}"
                generated_files[bridge_id] = output_file
        
        return generated_files
    
    def generate_index(self) -> Path:
        """
        Generate global bridge index file.
        
        Returns:
            Path to index file
        """
        bridge_files = [f for f in self.output_dir.glob("*.json") if f.name != "index.json"]
        
        bridges = []
        total_linksets = 0
        
        for bridge_file in bridge_files:
            try:
                with open(bridge_file, 'r') as f:
                    data = json.load(f)
                    bridge_context = BridgeContext(**data)
                    
                    bridges.append({
                        "source": bridge_context.source_graph_id,
                        "target": bridge_context.target_graph_id,
                        "file": bridge_file.name
                    })
                    
                    total_linksets += len(bridge_context.linksets)
            
            except Exception as e:
                print(f"  Warning: Failed to process {bridge_file}: {e}")
                continue
        
        index_data = {
            "bridges": sorted(bridges, key=lambda x: (x["source"], x["target"])),
            "total_bridges": len(bridges),
            "total_linksets": total_linksets
        }
        
        index_file = self.output_dir / "index.json"
        with open(index_file, 'w') as f:
            json.dump(index_data, f, indent=2)
        
        return index_file


