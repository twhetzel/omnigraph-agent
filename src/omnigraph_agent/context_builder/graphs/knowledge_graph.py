"""
Base class for knowledge graph handlers.

Knowledge graphs contain datasets from multiple repositories/catalogs
(e.g., NDE with ImmPort, Vivli, etc.).
"""

from abc import abstractmethod
from typing import List, Dict
from .base import BaseGraph


class KnowledgeGraph(BaseGraph):
    """Base class for knowledge graph handlers."""
    
    @abstractmethod
    def get_repositories(self) -> List[Dict[str, str]]:
        """
        Detect and return repositories/catalogs in the knowledge graph.
        
        Returns:
            List of dicts with 'id', 'uri', and 'label' keys
        """
        pass

