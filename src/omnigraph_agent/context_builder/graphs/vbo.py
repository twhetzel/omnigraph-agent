"""
VBO-specific graph logic for context building.
"""

from pathlib import Path
from typing import Optional
from .ontology import OntologyGraph


class VBOGraph(OntologyGraph):
    """VBO graph handler for context building."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize VBO graph handler with configuration."""
        if config_path is None:
            # Default to config in package
            config_path = Path(__file__).parent.parent / "config" / "vbo.yaml"
        
        super().__init__(config_path=config_path)

