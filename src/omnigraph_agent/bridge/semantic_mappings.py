"""Semantic mappings for identifier types.

Groups identifier prefixes by semantic category (e.g., taxonomies, genes, diseases)
to enable cross-prefix matching and semantic understanding.
"""

from typing import Dict, List, Set, Optional
from enum import Enum


class IdentifierCategory(str, Enum):
    """Semantic categories for identifier types."""
    TAXONOMY = "taxonomy"
    GENE = "gene"
    DISEASE = "disease"
    CHEMICAL = "chemical"
    PROTEIN = "protein"
    PHENOTYPE = "phenotype"
    PUBLICATION = "publication"
    DATASET = "dataset"
    CLINICAL_TRIAL = "clinical_trial"
    GEO = "geo"
    UNKNOWN = "unknown"


# Mapping from identifier prefix to semantic category
IDENTIFIER_CATEGORIES: Dict[str, IdentifierCategory] = {
    # Taxonomies
    "NCBITaxon": IdentifierCategory.TAXONOMY,
    "ITIS": IdentifierCategory.TAXONOMY,
    "GBIF": IdentifierCategory.TAXONOMY,
    "UniProtKB": IdentifierCategory.TAXONOMY,  # UniProtKB taxon IDs (when used as taxonomy, e.g., uniprot.org/taxonomy/9606)
    
    # Genes
    "HGNC": IdentifierCategory.GENE,
    "Ensembl": IdentifierCategory.GENE,
    "MGI": IdentifierCategory.GENE,
    "ZFIN": IdentifierCategory.GENE,
    "FlyBase": IdentifierCategory.GENE,
    "WormBase": IdentifierCategory.GENE,
    "RGD": IdentifierCategory.GENE,
    
    # Diseases
    "MONDO": IdentifierCategory.DISEASE,
    "DOID": IdentifierCategory.DISEASE,
    "OMIM": IdentifierCategory.DISEASE,
    "Orphanet": IdentifierCategory.DISEASE,
    
    # Chemicals
    "CHEBI": IdentifierCategory.CHEMICAL,
    "ChEBI": IdentifierCategory.CHEMICAL,
    "PubChem": IdentifierCategory.CHEMICAL,
    "DrugBank": IdentifierCategory.CHEMICAL,
    
    # Proteins (UniProtKB is listed under TAXONOMY when used as taxon IDs)
    "UniProt": IdentifierCategory.PROTEIN,
    "Pfam": IdentifierCategory.PROTEIN,
    "InterPro": IdentifierCategory.PROTEIN,
    
    # Phenotypes
    "HP": IdentifierCategory.PHENOTYPE,
    "MP": IdentifierCategory.PHENOTYPE,
    "ZP": IdentifierCategory.PHENOTYPE,
    
    # Publications
    "PMID": IdentifierCategory.PUBLICATION,
    "PMC": IdentifierCategory.PUBLICATION,
    "DOI": IdentifierCategory.PUBLICATION,
    "arXiv": IdentifierCategory.PUBLICATION,
    
    # Datasets
    "GSE": IdentifierCategory.GEO,
    "GEO": IdentifierCategory.GEO,
    "SRA": IdentifierCategory.DATASET,
    "ENA": IdentifierCategory.DATASET,
    
    # Clinical Trials
    "NCT": IdentifierCategory.CLINICAL_TRIAL,
    "ISRCTN": IdentifierCategory.CLINICAL_TRIAL,
    
    # Ontologies
    "GO": IdentifierCategory.UNKNOWN,  # Gene Ontology - could be multiple categories
    "RO": IdentifierCategory.UNKNOWN,  # Relation Ontology
    "BFO": IdentifierCategory.UNKNOWN,  # Basic Formal Ontology
    "IAO": IdentifierCategory.UNKNOWN,  # Information Artifact Ontology
}


# Reverse mapping: category to list of prefixes
CATEGORY_TO_PREFIXES: Dict[IdentifierCategory, List[str]] = {}
for prefix, category in IDENTIFIER_CATEGORIES.items():
    if category not in CATEGORY_TO_PREFIXES:
        CATEGORY_TO_PREFIXES[category] = []
    CATEGORY_TO_PREFIXES[category].append(prefix)


# Known cross-prefix mappings (e.g., UniProt taxon ↔ NCBITaxon)
# These represent semantic relationships across different identifier systems
CROSS_PREFIX_MAPPINGS: Dict[str, List[str]] = {
    # Taxonomy mappings (cross-system taxonomic identifiers)
    "NCBITaxon": ["UniProtKB", "ITIS", "GBIF"],  # NCBITaxon can map to other taxonomy systems
    "UniProtKB": ["NCBITaxon"],  # UniProt taxon IDs can map to NCBITaxon
    "ITIS": ["NCBITaxon"],
    "GBIF": ["NCBITaxon"],
    
    # Gene mappings (cross-system gene identifiers)
    "HGNC": ["Ensembl", "MGI", "ZFIN", "FlyBase", "WormBase", "RGD"],
    "Ensembl": ["HGNC", "MGI"],
    "MGI": ["HGNC", "Ensembl"],
    "ZFIN": ["HGNC"],
    "FlyBase": ["HGNC"],
    "WormBase": ["HGNC"],
    "RGD": ["HGNC"],
    
    # Disease mappings (cross-system disease identifiers)
    "MONDO": ["DOID", "OMIM", "Orphanet"],
    "DOID": ["MONDO", "OMIM"],
    "OMIM": ["MONDO", "DOID"],
    "Orphanet": ["MONDO"],
    
    # Publication mappings
    "PMID": ["PMC", "DOI"],
    "PMC": ["PMID", "DOI"],
    "DOI": ["PMID", "PMC"],
}


def get_category(prefix: str) -> IdentifierCategory:
    """
    Get the semantic category for an identifier prefix.
    
    Args:
        prefix: Identifier prefix (e.g., "NCBITaxon", "HGNC")
    
    Returns:
        IdentifierCategory or UNKNOWN if not found
    """
    return IDENTIFIER_CATEGORIES.get(prefix, IdentifierCategory.UNKNOWN)


def get_semantically_related_prefixes(prefix: str) -> List[str]:
    """
    Get prefixes that are semantically related to the given prefix.
    
    This includes:
    1. Prefixes in the same category
    2. Prefixes with known cross-mappings
    
    Args:
        prefix: Identifier prefix
    
    Returns:
        List of related prefixes
    """
    related = set()
    
    # Get category
    category = get_category(prefix)
    if category != IdentifierCategory.UNKNOWN:
        # Add all prefixes in the same category
        related.update(CATEGORY_TO_PREFIXES.get(category, []))
    
    # Add cross-mapped prefixes
    if prefix in CROSS_PREFIX_MAPPINGS:
        related.update(CROSS_PREFIX_MAPPINGS[prefix])
    
    # Remove self
    related.discard(prefix)
    
    return list(related)


def are_semantically_related(prefix1: str, prefix2: str) -> bool:
    """
    Check if two identifier prefixes are semantically related.
    
    Args:
        prefix1: First identifier prefix
        prefix2: Second identifier prefix
    
    Returns:
        True if they're in the same category or have a known mapping
    """
    if prefix1 == prefix2:
        return True
    
    # Check if same category
    cat1 = get_category(prefix1)
    cat2 = get_category(prefix2)
    if cat1 != IdentifierCategory.UNKNOWN and cat1 == cat2:
        return True
    
    # Check cross-mappings
    if prefix1 in CROSS_PREFIX_MAPPINGS and prefix2 in CROSS_PREFIX_MAPPINGS[prefix1]:
        return True
    if prefix2 in CROSS_PREFIX_MAPPINGS and prefix1 in CROSS_PREFIX_MAPPINGS[prefix2]:
        return True
    
    return False


def get_category_description(category: IdentifierCategory) -> str:
    """Get a human-readable description of a category."""
    descriptions = {
        IdentifierCategory.TAXONOMY: "Taxonomic identifiers (species, organisms)",
        IdentifierCategory.GENE: "Gene identifiers",
        IdentifierCategory.DISEASE: "Disease identifiers",
        IdentifierCategory.CHEMICAL: "Chemical compound identifiers",
        IdentifierCategory.PROTEIN: "Protein identifiers",
        IdentifierCategory.PHENOTYPE: "Phenotype identifiers",
        IdentifierCategory.PUBLICATION: "Publication identifiers",
        IdentifierCategory.DATASET: "Dataset identifiers",
        IdentifierCategory.CLINICAL_TRIAL: "Clinical trial identifiers",
        IdentifierCategory.GEO: "Gene Expression Omnibus identifiers",
        IdentifierCategory.UNKNOWN: "Unknown or unclassified identifiers",
    }
    return descriptions.get(category, "Unknown category")

