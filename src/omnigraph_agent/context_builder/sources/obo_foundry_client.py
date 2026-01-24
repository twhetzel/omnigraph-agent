"""OBO Foundry registry client for fetching ontology metadata."""

import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.request import urlopen
from datetime import datetime, timedelta


OBO_FOUNDRY_REGISTRY_URL = "https://obofoundry.org/registry/ontologies.yml"
CACHE_DURATION_DAYS = 7


class OBOfoundryClient:
    """Client for fetching and caching OBO Foundry registry metadata."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize OBO Foundry client.
        
        Args:
            cache_dir: Directory to cache registry data (default: .cache/obo_foundry)
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "omnigraph_agent" / "obo_foundry"
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.cache_dir / "ontologies.yml"
        self.metadata_cache: Dict[str, Dict[str, Any]] = {}
    
    def _is_cache_valid(self) -> bool:
        """Check if cached registry file is still valid."""
        if not self.registry_file.exists():
            return False
        
        # Check if cache is older than CACHE_DURATION_DAYS
        cache_age = datetime.now() - datetime.fromtimestamp(self.registry_file.stat().st_mtime)
        return cache_age < timedelta(days=CACHE_DURATION_DAYS)
    
    def _download_registry(self) -> Dict[str, Any]:
        """Download OBO Foundry registry YAML."""
        try:
            with urlopen(OBO_FOUNDRY_REGISTRY_URL, timeout=30) as response:
                registry_data = yaml.safe_load(response.read())
            
            # Cache the registry
            with open(self.registry_file, 'w') as f:
                yaml.dump(registry_data, f, default_flow_style=False)
            
            return registry_data
        except Exception as e:
            print(f"  Warning: Failed to download OBO Foundry registry: {e}")
            # Try to use cached version if available
            if self.registry_file.exists():
                print(f"  Using cached registry from {self.registry_file}")
                with open(self.registry_file, 'r') as f:
                    return yaml.safe_load(f)
            return {}
    
    def _load_registry(self) -> Dict[str, Any]:
        """Load OBO Foundry registry (from cache or download)."""
        if self._is_cache_valid():
            try:
                with open(self.registry_file, 'r') as f:
                    return yaml.safe_load(f)
            except Exception:
                pass
        
        # Cache invalid or missing, download fresh
        return self._download_registry()
    
    def _normalize_ontology_id(self, ontology_id: str) -> str:
        """
        Normalize ontology ID for matching.
        
        Handles variations like:
        - "go" -> "go"
        - "GO" -> "go"
        - "mondo" -> "mondo"
        - "MONDO" -> "mondo"
        """
        return ontology_id.lower().strip()
    
    def get_ontology_metadata(self, ontology_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for an ontology from OBO Foundry registry.
        
        Args:
            ontology_id: Ontology identifier (e.g., 'go', 'mondo', 'hp')
        
        Returns:
            Dictionary with OBO Foundry metadata or None if not found
        """
        # Check cache first
        normalized_id = self._normalize_ontology_id(ontology_id)
        if normalized_id in self.metadata_cache:
            return self.metadata_cache[normalized_id]
        
        # Load registry
        registry = self._load_registry()
        if not registry or 'ontologies' not in registry:
            return None
        
        # Find matching ontology
        for ontology in registry.get('ontologies', []):
            obo_id = self._normalize_ontology_id(ontology.get('id', ''))
            if obo_id == normalized_id:
                # Extract relevant metadata
                raw_products = ontology.get('products', [])
                products = [
                    p.get('id', str(p)) if isinstance(p, dict) else str(p)
                    for p in raw_products
                ] if raw_products else None

                metadata = {
                    'id': ontology.get('id'),
                    'title': ontology.get('title'),
                    'description': ontology.get('description'),
                    'homepage': ontology.get('homepage'),
                    'license': ontology.get('license', {}).get('label') if isinstance(ontology.get('license'), dict) else ontology.get('license'),
                    'contact': ontology.get('contact', {}).get('label') if isinstance(ontology.get('contact'), dict) else ontology.get('contact'),
                    'domain': ontology.get('domain'),
                    'products': products,
                    'dependencies': ontology.get('dependencies', []),
                    'imports': [dep.get('id') for dep in ontology.get('dependencies', []) if isinstance(dep, dict) and dep.get('type') == 'imports' and dep.get('id')],
                }
                
                # Cache it
                self.metadata_cache[normalized_id] = metadata
                return metadata
        
        return None
    
    def get_all_ontologies(self) -> Dict[str, Dict[str, Any]]:
        """
        Get metadata for all ontologies in the registry.
        
        Returns:
            Dictionary mapping ontology ID to metadata
        """
        registry = self._load_registry()
        if not registry or 'ontologies' not in registry:
            return {}
        
        all_metadata = {}
        for ontology in registry.get('ontologies', []):
            obo_id = ontology.get('id', '').lower()
            if obo_id:
                metadata = self.get_ontology_metadata(obo_id)
                if metadata:
                    all_metadata[obo_id] = metadata
        
        return all_metadata
