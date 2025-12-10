"""
Orchestrates introspection → JSON generation for graph contexts.

Coordinates between graph handlers and schema models to generate
context files for global and repository-specific views.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from .model.context_schema import (
    GlobalContext,
    RepositoryContext,
    Dimension,
    DimensionOverride,
    RepositoryStats
)
from .graphs import get_graph_handler
from .graphs.base import APPROX_DISTINCT_THRESHOLD


class ContextBuilder:
    """Orchestrates context file generation."""
    
    def __init__(self, graph_id: str, output_dir: Path):
        """
        Initialize context builder.
        
        Args:
            graph_id: Graph identifier (e.g., 'nde')
            output_dir: Directory to write JSON files
        """
        self.graph_id = graph_id
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load graph handler via registry/factory
        handler_cls = get_graph_handler(graph_id)
        self.graph = handler_cls()
    
    def build(self) -> Dict[str, Path]:
        """
        Build all context files (global + repositories).
        
        Returns:
            Dict mapping context type to output file path
        """
        output_files = {}
        
        # Build global context
        global_path = self.build_global()
        output_files['global'] = global_path
        
        # Build repository contexts
        repositories = self.graph.get_repositories()
        for repo in repositories:
            repo_path = self.build_repository(repo)
            output_files[repo['id']] = repo_path
        
        return output_files
    
    def build_global(self) -> Path:
        """Build global context file."""
        dimensions = []
        
        # Introspect each dimension
        for dim_config in self.graph.dimensions:
            coverage = self.graph.get_dimension_coverage(dim_config)
            distinct_count = self.graph.get_distinct_values_count(dim_config)
            top_values = self.graph.get_top_values(dim_config, top_n=10)
            
            dimension = Dimension(
                name=dim_config.get('property', dim_config['name']),
                coverage=coverage,
                approx_distinct_values=distinct_count if distinct_count < APPROX_DISTINCT_THRESHOLD else None,
                top_values=top_values if top_values else None
            )
            dimensions.append(dimension)
        
        # Count total datasets
        total_datasets = self.graph.count_datasets()
        
        # Get query hints: from config if present, or auto-generate for ontologies
        query_hints = None
        if hasattr(self.graph, 'config') and 'query_hints' in self.graph.config:
            from .model.context_schema import QueryGenerationHints
            query_hints = QueryGenerationHints(**self.graph.config['query_hints'])
        elif hasattr(self.graph, 'generate_query_hints'):
            # Auto-generate query hints for ontology graphs
            hints_dict = self.graph.generate_query_hints()
            if hints_dict:
                from .model.context_schema import QueryGenerationHints
                query_hints = QueryGenerationHints(**hints_dict)
        
        global_context = GlobalContext(
            graph_id=self.graph_id,
            endpoint=self.graph.endpoint,
            entity_types=self.graph.entity_types,
            prefixes=self.graph.get_prefixes(),
            dimensions=dimensions,
            text_blurb=self.graph.text_blurb,
            query_hints=query_hints
        )
        
        # Write JSON file
        output_path = self.output_dir / f"{self.graph_id}_global.json"
        with open(output_path, 'w') as f:
            json.dump(global_context.model_dump(exclude_none=True), f, indent=2)
        
        return output_path
    
    def build_repository(self, repo: Dict[str, str]) -> Path:
        """Build repository-specific context file."""
        repo_id = repo['id']
        repo_uri = repo['uri']
        repo_filter = self.graph.get_repository_filter(repo_id, repo_uri)
        
        # Get repository stats
        total_datasets = self.graph.count_datasets(repo_filter)
        stats = RepositoryStats(total_datasets=total_datasets)
        
        # Build dimension overrides
        dimension_overrides = {}
        
        for dim_config in self.graph.dimensions:
            dim_name = dim_config['name']
            
            # Get repository-specific values
            coverage = self.graph.get_dimension_coverage(dim_config, repo_filter)
            distinct_count = self.graph.get_distinct_values_count(dim_config, repo_filter)
            top_values = self.graph.get_top_values(dim_config, repo_filter, top_n=10)
            
            # Only include override if it differs significantly from global
            # For now, include all overrides
            override = DimensionOverride(
                coverage=coverage,
                approx_distinct_values=distinct_count if distinct_count < APPROX_DISTINCT_THRESHOLD else None,
                top_values=top_values if top_values else None
            )
            dimension_overrides[dim_name] = override
        
        repository_context = RepositoryContext(
            graph_id=self.graph_id,
            source_id=repo_id,
            inherits_from=f"{self.graph_id}_global",
            repository_filter=repo_filter,
            dimension_overrides=dimension_overrides,
            stats=stats,
            prefixes=self.graph.get_prefixes(),
            text_blurb=f"Context for {repo.get('label', repo_id)} repository"
        )
        
        # Write JSON file
        output_path = self.output_dir / f"{self.graph_id}_{repo_id}.json"
        with open(output_path, 'w') as f:
            json.dump(repository_context.model_dump(exclude_none=True), f, indent=2)
        
        return output_path

