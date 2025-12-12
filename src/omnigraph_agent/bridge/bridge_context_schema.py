"""Pydantic models for bridge context JSON files."""

from typing import List
from pydantic import BaseModel, Field


class LinksetSummary(BaseModel):
    """Summary statistics for a linkset."""
    join_key_type: str = Field(..., description="Join key type (e.g., 'GSE_ID', 'MONDO_ID')")
    num_links: int = Field(..., ge=0, description="Number of links in this linkset")
    min_confidence: float = Field(..., ge=0.0, le=1.0, description="Minimum confidence score")
    max_confidence: float = Field(..., ge=0.0, le=1.0, description="Maximum confidence score")
    linkset_iri: str = Field(..., description="IRI of the linkset")


class BridgeContext(BaseModel):
    """Bridge context schema for a graph pair."""
    source_graph: str = Field(..., description="Source graph endpoint URL")
    target_graph: str = Field(..., description="Target graph endpoint URL")
    source_graph_id: str = Field(..., description="Source graph identifier (e.g., 'nde')")
    target_graph_id: str = Field(..., description="Target graph identifier (e.g., 'bioproject')")
    linksets: List[LinksetSummary] = Field(
        default_factory=list,
        description="List of linksets between the two graphs"
    )


