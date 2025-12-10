"""
Minimal v1 JSON schema for graph context files.

Defines the structure for:
- Global context files (nde_global.json)
- Repository-specific context files (nde_<repo>.json)
- Ontology context files (with query generation hints)
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class TopValue(BaseModel):
    """Top value entry for a dimension."""
    value: Any = Field(..., description="The value (IRI or literal)")
    count: int = Field(..., ge=0, description="Number of entities with this value")


class QueryGenerationHints(BaseModel):
    """Hints and rules for LLM query generation."""
    namespace_scope: Optional[str] = Field(
        None, 
        description="SPARQL FILTER pattern to restrict results to namespace (e.g., 'FILTER STRSTARTS(STR(?class), \"http://purl.obolibrary.org/obo/MONDO_\")')"
    )
    reasoning_mode: Optional[str] = Field(
        None,
        description="Reasoning assumptions (e.g., 'no entailment', 'use explicit patterns and property paths')"
    )
    exclude_obsoletes: Optional[bool] = Field(
        None,
        description="Whether to exclude obsoleted/deprecated entities (e.g., owl:deprecated true)"
    )
    label_property: Optional[str] = Field(
        None,
        description="Property to use for labels (e.g., 'rdfs:label')"
    )
    definition_property: Optional[str] = Field(
        None,
        description="Property to use for definitions (e.g., 'IAO:0000115')"
    )
    query_patterns: Optional[Dict[str, str]] = Field(
        None,
        description="Common query patterns as templates (e.g., axiom patterns, gene associations)"
    )
    default_behaviors: Optional[Dict[str, Any]] = Field(
        None,
        description="Default query behaviors (e.g., {'consider_descendants': True, 'sort_results': True})"
    )
    output_rules: Optional[Dict[str, Any]] = Field(
        None,
        description="Output formatting rules (e.g., extension mode handling, code block formatting)"
    )


class Dimension(BaseModel):
    """A dimension (property/predicate) in the knowledge graph."""
    name: str = Field(..., description="Property name/IRI")
    coverage: float = Field(..., ge=0.0, le=1.0, description="Fraction of datasets with this dimension")
    approx_distinct_values: Optional[int] = Field(None, description="Approximate number of distinct values")
    top_values: Optional[List[TopValue]] = Field(None, description="Top values with counts")


class GlobalContext(BaseModel):
    """Global graph context schema."""
    graph_id: str = Field(..., description="Graph identifier (e.g., 'nde')")
    endpoint: str = Field(..., description="SPARQL endpoint URL")
    entity_types: List[str] = Field(default_factory=list, description="Main entity types in the graph")
    dimensions: List[Dimension] = Field(default_factory=list, description="Available dimensions")
    prefixes: Dict[str, str] = Field(default_factory=dict, description="Prefix to IRI mappings used in this context")
    text_blurb: Optional[str] = Field(None, description="Human-readable description of the graph")
    query_hints: Optional[QueryGenerationHints] = Field(
        None,
        description="Optional hints and rules for LLM query generation (useful for ontologies)"
    )


class DimensionOverride(BaseModel):
    """Repository-specific dimension overrides."""
    coverage: Optional[float] = Field(None, ge=0.0, le=1.0)
    approx_distinct_values: Optional[int] = None
    top_values: Optional[List[TopValue]] = None


class RepositoryStats(BaseModel):
    """Statistics for a repository."""
    total_datasets: Optional[int] = None
    total_triples: Optional[int] = None


class RepositoryContext(BaseModel):
    """Repository-specific context schema."""
    graph_id: str = Field(..., description="Graph identifier (e.g., 'nde')")
    source_id: str = Field(..., description="Repository/source identifier (e.g., 'immport', 'vivli')")
    inherits_from: str = Field(..., description="Reference to global context (e.g., 'nde_global')")
    repository_filter: Dict[str, str] = Field(..., description="Filter properties to identify this repository")
    dimension_overrides: Dict[str, DimensionOverride] = Field(
        default_factory=dict,
        description="Repository-specific dimension overrides"
    )
    stats: Optional[RepositoryStats] = Field(None, description="Repository statistics")
    prefixes: Dict[str, str] = Field(default_factory=dict, description="Prefix to IRI mappings used in this context")
    text_blurb: Optional[str] = Field(None, description="Human-readable description of the repository")
    query_hints: Optional[QueryGenerationHints] = Field(
        None,
        description="Optional repository-specific query hints (overrides global hints if present)"
    )

