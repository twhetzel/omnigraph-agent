"""
Minimal v1 JSON schema for graph context files.

Defines the structure for:
- Global context files (nde_global.json)
- Repository-specific context files (nde_<repo>.json)
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class Dimension(BaseModel):
    """A dimension (property/predicate) in the knowledge graph."""
    name: str = Field(..., description="Property name/IRI")
    coverage: float = Field(..., ge=0.0, le=1.0, description="Fraction of datasets with this dimension")
    approx_distinct_values: Optional[int] = Field(None, description="Approximate number of distinct values")
    top_values: Optional[List[Dict[str, Any]]] = Field(None, description="Top values with counts")


class GlobalContext(BaseModel):
    """Global graph context schema."""
    graph_id: str = Field(..., description="Graph identifier (e.g., 'nde')")
    endpoint: str = Field(..., description="SPARQL endpoint URL")
    entity_types: List[str] = Field(default_factory=list, description="Main entity types in the graph")
    dimensions: List[Dimension] = Field(default_factory=list, description="Available dimensions")
    text_blurb: Optional[str] = Field(None, description="Human-readable description of the graph")


class DimensionOverride(BaseModel):
    """Repository-specific dimension overrides."""
    coverage: Optional[float] = Field(None, ge=0.0, le=1.0)
    approx_distinct_values: Optional[int] = None
    top_values: Optional[List[Dict[str, Any]]] = None


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
    text_blurb: Optional[str] = Field(None, description="Human-readable description of the repository")

