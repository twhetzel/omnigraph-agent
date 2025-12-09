"""
NDE-specific graph logic for context building.

Handles:
- Repository detection (by schema:includedInDataCatalog)
- NDE-specific query patterns
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
from .base import BaseGraph


class NDEGraph(BaseGraph):
    """NDE graph handler for context building."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize NDE graph handler with configuration."""
        if config_path is None:
            # Default to config in package
            config_path = Path(__file__).parent.parent / "config" / "nde.yaml"
        
        super().__init__(config_path=config_path)
    
    def get_repositories(self) -> List[Dict[str, str]]:
        """
        Detect repositories by querying for distinct values of repo_filter_property.
        
        Returns list of dicts with 'id', 'uri', and 'label' keys.
        """
        repo_prop = self._expand_property(self.repo_filter_property)
        query = f"""
        PREFIX schema: <http://schema.org/>
        
        SELECT DISTINCT ?catalog ?label
        WHERE {{
            ?dataset {repo_prop} ?catalog .
            OPTIONAL {{ ?catalog schema:name ?label . }}
        }}
        ORDER BY ?label
        """
        
        self.sparql.setQuery(query)
        results = self.sparql.query().convert()
        
        repositories = []
        for binding in results['results']['bindings']:
            catalog_uri = binding['catalog']['value']
            # Extract repository ID from URI (e.g., last segment or domain)
            repo_id = self._extract_repo_id(catalog_uri)
            label = binding.get('label', {}).get('value', repo_id)
            
            repositories.append({
                'id': repo_id,
                'uri': catalog_uri,
                'label': label
            })
        
        return repositories
