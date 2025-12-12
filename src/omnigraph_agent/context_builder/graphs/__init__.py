"""Graph handlers registry."""

from pathlib import Path
from typing import Dict, Type, Optional

from .nde import NDEGraph
from .vbo import VBOGraph
from .mondo import MONDOGraph
from .generic import GenericGraph, GenericOntologyGraph

# Map graph_id to handler class for easy extensibility
GRAPH_HANDLERS: Dict[str, Type] = {
    "nde": NDEGraph,
    "vbo": VBOGraph,
    "mondo": MONDOGraph,
}


def get_graph_handler(graph_id: str):
    """
    Return the graph handler class for the given graph_id.
    
    If no specific handler is registered, tries to auto-discover:
    1. Check if a config file exists
    2. Determine if it's an ontology (no repo_filter_property) or knowledge graph
    3. Return appropriate generic handler
    
    Args:
        graph_id: Graph identifier (e.g., 'nde', 'spoke-okn')
        
    Returns:
        Graph handler class
        
    Raises:
        ValueError: If graph_id is unknown and no config file exists
    """
    # Check if specific handler is registered
    handler_cls = GRAPH_HANDLERS.get(graph_id)
    if handler_cls is not None:
        return handler_cls
    
    # Auto-discover: check if config file exists
    config_dir = Path(__file__).parent.parent / "config"
    config_path = config_dir / f"{graph_id}.yaml"
    
    if config_path.exists():
        # Load config to determine if it's an ontology or knowledge graph
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # If no repo_filter_property or it's empty, treat as ontology
        repo_filter = config.get('repo_filter_property', '').strip()
        if not repo_filter:
            return GenericOntologyGraph
        else:
            return GenericGraph
    
    raise ValueError(f"Unknown graph_id: {graph_id}. No handler registered and no config file found at {config_path}")

