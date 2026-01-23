"""
Generic graph handlers for graphs that don't need custom logic.

These handlers work with just a config file and can be used for most
FRINK registry graphs without needing to create a custom handler class.
"""

from pathlib import Path
from typing import List, Dict, Optional
from .knowledge_graph import KnowledgeGraph
from .ontology import OntologyGraph


class GenericGraph(KnowledgeGraph):
    """
    Generic knowledge graph handler that works with any config file.
    
    Automatically detects repositories using the repo_filter_property
    from the config file. Use this for FRINK registry graphs that
    don't need custom logic.
    """
    
    def __init__(self, config_path: Optional[Path] = None, graph_id: Optional[str] = None):
        """
        Initialize generic graph handler with configuration.
        
        Args:
            config_path: Path to YAML config file (auto-discovered if graph_id provided)
            graph_id: Graph identifier (used to auto-discover config_path if not provided)
        """
        if config_path is None:
            if graph_id is None:
                raise ValueError("Either config_path or graph_id must be provided")
            # Auto-discover config path
            config_dir = Path(__file__).parent.parent / "config"
            config_path = config_dir / f"{graph_id}.yaml"
            if not config_path.exists():
                raise ValueError(f"Config file not found: {config_path}")
        super().__init__(config_path=config_path)
    
    def get_repositories(self) -> List[Dict[str, str]]:
        """
        Detect repositories by querying for distinct values of repo_filter_property.
        
        This is a generic implementation that works for most knowledge graphs.
        Returns list of dicts with 'id', 'uri', and 'label' keys.
        """
        # If no repo_filter_property is specified, return empty list (single-source graph)
        if not self.repo_filter_property or not self.repo_filter_property.strip():
            return []
        
        repo_prop = self._expand_property(self.repo_filter_property)
        query = f"""
        PREFIX schema: <http://schema.org/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        
        SELECT DISTINCT ?catalog ?label
        WHERE {{
            ?entity {repo_prop} ?catalog .
            OPTIONAL {{ ?catalog schema:name ?label . }}
            OPTIONAL {{ ?catalog rdfs:label ?label . }}
        }}
        ORDER BY ?label
        LIMIT 100
        """
        
        try:
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
        except Exception as e:
            # If repository detection fails, return empty list (treat as single-source graph)
            return []


class GenericOntologyGraph(OntologyGraph):
    """
    Generic ontology graph handler that works with any config file.
    
    Use this for ontologies that don't need custom logic.
    Ontologies are single-source and don't have repositories.
    """
    
    def __init__(self, config_path: Optional[Path] = None, graph_id: Optional[str] = None):
        """
        Initialize generic ontology handler with configuration.
        
        Args:
            config_path: Path to YAML config file (auto-discovered if graph_id provided)
            graph_id: Graph identifier (used to auto-discover config_path if not provided)
        """
        if config_path is None:
            if graph_id is None:
                raise ValueError("Either config_path or graph_id must be provided")
            # Auto-discover config path
            config_dir = Path(__file__).parent.parent / "config"
            config_path = config_dir / f"{graph_id}.yaml"
            if not config_path.exists():
                raise ValueError(f"Config file not found: {config_path}")
        super().__init__(config_path=config_path)

