"""Graph handlers registry."""

from typing import Dict, Type

from .nde import NDEGraph

# Map graph_id to handler class for easy extensibility
GRAPH_HANDLERS: Dict[str, Type] = {
    "nde": NDEGraph,
}


def get_graph_handler(graph_id: str):
    """Return the graph handler class for the given graph_id."""
    handler_cls = GRAPH_HANDLERS.get(graph_id)
    if handler_cls is None:
        raise ValueError(f"Unknown graph_id: {graph_id}")
    return handler_cls

