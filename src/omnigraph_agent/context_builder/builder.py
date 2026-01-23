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
    RepositoryStats,
    IdentifierInfo,
    IdentifierPattern
)
from ..bridge.semantic_mappings import get_category, get_semantically_related_prefixes
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
        # Pass graph_id to generic handlers for auto-discovery
        try:
            self.graph = handler_cls(graph_id=graph_id)
        except TypeError:
            # Handler doesn't accept graph_id parameter, use default initialization
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
        try:
            total_datasets = self.graph.count_datasets()
        except Exception as e:
            print(f"    Warning: Failed to count datasets: {e}")
            total_datasets = 0
        
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
        
        # Introspect identifier information for bridge graph generation
        identifier_info = None
        try:
            print(f"  Introspecting identifier predicates for {self.graph_id}...")
            identifier_predicates = self.graph.introspect_identifier_predicates(limit=20)
            
            all_patterns = []
            predicates_list = []
            
            # Extract patterns from identifier predicates
            if identifier_predicates:
                # For ontologies, use smaller limit and fewer predicates to avoid timeouts
                from .graphs.ontology import OntologyGraph
                is_ontology = isinstance(self.graph, OntologyGraph)
                max_predicates = 5 if is_ontology else 10
                limit = 300 if is_ontology else 500
                
                for pred_info in identifier_predicates[:max_predicates]:  # Top N identifier predicates
                    pred_uri = pred_info['property']
                    
                    # Skip special ENTITY_IRI markers - these are handled separately
                    if pred_uri.startswith('ENTITY_IRI:'):
                        # Extract prefix from ENTITY_IRI:MONDO format
                        prefix = pred_uri.split(':', 1)[1] if ':' in pred_uri else None
                        if prefix:
                            # Create a pattern entry from entity IRI info
                            pattern_info = {
                                'prefix': prefix,
                                'pattern': None,  # Will be determined from sample
                                'example': pred_info.get('sample_value', ''),
                                'count': pred_info.get('count', 0),
                                'predicates': ['ENTITY_IRI']  # Special marker
                            }
                            
                            # Add semantic category
                            category = get_category(prefix)
                            pattern_info['semantic_category'] = category.value if category.value != 'unknown' else None
                            pattern_info['semantically_related_prefixes'] = get_semantically_related_prefixes(prefix)
                            
                            # Check if we already have this prefix
                            existing = next((p for p in all_patterns if isinstance(p, dict) and p.get('prefix') == prefix), None)
                            if existing:
                                existing['count'] = existing.get('count', 0) + pattern_info.get('count', 0)
                                if 'predicates' not in existing:
                                    existing['predicates'] = []
                                existing['predicates'].append('ENTITY_IRI')
                                existing['predicates'] = list(set(existing['predicates']))
                            else:
                                all_patterns.append(pattern_info)
                        continue
                    
                    predicates_list.append(pred_uri)
                    
                    # Extract patterns from this predicate
                    try:
                        patterns = self.graph.extract_identifier_patterns(pred_uri, limit=limit)
                        for pattern_info in patterns:
                            # pattern_info is a dict from extract_identifier_patterns
                            # Add the predicate to the pattern info
                            if 'predicates' not in pattern_info:
                                pattern_info['predicates'] = []
                            pattern_info['predicates'].append(pred_uri)
                            
                            # Add semantic category and related prefixes
                            prefix = pattern_info.get('prefix', '')
                            if prefix:
                                category = get_category(prefix)
                                pattern_info['semantic_category'] = category.value if category.value != 'unknown' else None
                                pattern_info['semantically_related_prefixes'] = get_semantically_related_prefixes(prefix)
                            
                            # Check if we already have this prefix (all_patterns contains dicts)
                            existing = next((p for p in all_patterns if isinstance(p, dict) and p.get('prefix') == pattern_info.get('prefix')), None)
                            if existing:
                                existing['count'] = existing.get('count', 0) + pattern_info.get('count', 0)
                                # Merge predicates list
                                if 'predicates' not in existing:
                                    existing['predicates'] = []
                                existing['predicates'].extend(pattern_info.get('predicates', []))
                                # Remove duplicates
                                existing['predicates'] = list(set(existing['predicates']))
                                # Merge semantically related prefixes
                                if 'semantically_related_prefixes' in pattern_info:
                                    if 'semantically_related_prefixes' not in existing:
                                        existing['semantically_related_prefixes'] = []
                                    existing['semantically_related_prefixes'].extend(pattern_info['semantically_related_prefixes'])
                                    existing['semantically_related_prefixes'] = list(set(existing['semantically_related_prefixes']))
                            else:
                                all_patterns.append(pattern_info)
                    except Exception as e:
                        print(f"    Warning: Failed to extract patterns from {pred_uri}: {e}")
                        continue
            
            # Also extract patterns from dimension values (e.g., MONDO in healthCondition, GSE in sameAs)
            print(f"  Extracting patterns from dimension values...")
            for dim_config in self.graph.dimensions:
                dim_property = dim_config.get('property', '')
                if not dim_property:
                    continue
                
                try:
                    # Get top values for this dimension
                    top_values = self.graph.get_top_values(dim_config, top_n=100)  # Get more values to find patterns
                    if not top_values:
                        continue
                    
                    # Extract identifier patterns from dimension values
                    # get_top_values returns list of dicts with 'value' and 'count' keys
                    dimension_patterns = {}
                    for tv in top_values:
                        # tv is a dict, not a TopValue object
                        value_str = str(tv.get('value', ''))
                        count = tv.get('count', 0)
                        
                        if not value_str:
                            continue
                        
                        # Try to extract identifier patterns from the value
                        import re
                        # Check for common identifier patterns
                        patterns_to_check = [
                            (r'^(GSE)(\d+)$', 'GSE'),
                            (r'^(NCT)(\d+)$', 'NCT'),
                            (r'^(MONDO):(\d+)$', 'MONDO'),
                            (r'^.*MONDO[:_](\d+)$', 'MONDO'),  # MONDO in IRI
                            (r'^(HGNC):(\d+)$', 'HGNC'),
                            (r'^(GO):(\d+)$', 'GO'),
                            (r'^(DOID):(\d+)$', 'DOID'),
                            (r'^(HP):(\d+)$', 'HP'),
                            (r'^(CHEBI):(\d+)$', 'CHEBI'),
                            (r'^(UniProtKB):([A-Z0-9]+)$', 'UniProtKB'),
                            (r'^(PMID):(\d+)$', 'PMID'),
                            (r'^(PMC)(\d+)$', 'PMC'),
                            (r'^(NCBITaxon):(\d+)$', 'NCBITaxon'),
                            (r'^.*NCBITaxon[:_](\d+)$', 'NCBITaxon'),  # NCBITaxon in IRI (e.g., NCBITaxon_9606)
                            (r'^.*uniprot\.org/taxonomy/(\d+)$', 'UniProtKB'),  # UniProtKB taxon in IRI (e.g., https://www.uniprot.org/taxonomy/9606)
                        ]
                        
                        for pattern_regex, known_prefix in patterns_to_check:
                            match = re.search(pattern_regex, value_str)
                            if match:
                                if known_prefix not in dimension_patterns:
                                    dimension_patterns[known_prefix] = {
                                        'prefix': known_prefix,
                                        'pattern': None,
                                        'example': value_str,
                                        'count': 0,
                                        'predicates': []
                                    }
                                dimension_patterns[known_prefix]['count'] += count
                                if dim_property not in dimension_patterns[known_prefix]['predicates']:
                                    dimension_patterns[known_prefix]['predicates'].append(dim_property)
                                break
                    
                    # Add dimension patterns to all_patterns
                    for prefix, pattern_info in dimension_patterns.items():
                        # Add semantic category
                        category = get_category(prefix)
                        pattern_info['semantic_category'] = category.value if category.value != 'unknown' else None
                        pattern_info['semantically_related_prefixes'] = get_semantically_related_prefixes(prefix)
                        
                        # Check if we already have this prefix
                        existing = next((p for p in all_patterns if isinstance(p, dict) and p.get('prefix') == prefix), None)
                        if existing:
                            existing['count'] = existing.get('count', 0) + pattern_info.get('count', 0)
                            # Merge predicates
                            if 'predicates' not in existing:
                                existing['predicates'] = []
                            existing['predicates'].extend(pattern_info.get('predicates', []))
                            existing['predicates'] = list(set(existing['predicates']))
                        else:
                            all_patterns.append(pattern_info)
                            
                except Exception as e:
                    # Silently continue - dimension might not have extractable patterns
                    continue
            
            if all_patterns:
                # Get top classes that use these identifiers
                top_classes = self.graph.entity_types[:5] if self.graph.entity_types else []
                
                # Convert dict patterns to IdentifierPattern objects
                pattern_objects = [IdentifierPattern(**p) if isinstance(p, dict) else p for p in all_patterns]
                
                identifier_info = IdentifierInfo(
                    predicates=predicates_list,
                    patterns=pattern_objects,
                    top_classes=top_classes
                )
                print(f"    Found {len(predicates_list)} identifier predicates, {len(all_patterns)} patterns")
        except Exception as e:
            print(f"    Warning: Failed to introspect identifier information: {e}")
        
        global_context = GlobalContext(
            graph_id=self.graph_id,
            endpoint=self.graph.endpoint,
            entity_types=self.graph.entity_types,
            prefixes=self.graph.get_prefixes(),
            dimensions=dimensions,
            text_blurb=self.graph.text_blurb,
            query_hints=query_hints,
            identifier_info=identifier_info
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

