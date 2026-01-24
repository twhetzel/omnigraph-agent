# YAML Context Format Specification

## Overview

The omnigraph-agent supports generating context files in both JSON and YAML formats. YAML is recommended for ontologies as it's more human-readable and easier to integrate with context packs.

## Usage

```bash
# Generate YAML context
python -m omnigraph_agent.context_builder.cli build go --format yaml

# Generate JSON context (default)
python -m omnigraph_agent.context_builder.cli build go --format json
```

## Output Structure

The YAML output structure is identical to JSON, just in YAML format. Both formats contain the same information.

### Basic Structure

```yaml
graph_id: go
endpoint: https://ubergraph.apps.renci.org/sparql
entity_types:
  - http://www.w3.org/2002/07/owl#Class
dimensions: []
prefixes:
  schema: http://schema.org/
  rdf: http://www.w3.org/1999/02/22-rdf-syntax-ns#
text_blurb: "Gene Ontology at Ubergraph"
query_hints:
  namespace_scope: "http://purl.obolibrary.org/obo/GO_"
  reasoning_mode: "Use property paths for hierarchy traversal"
identifier_info:
  predicates:
    - http://www.geneontology.org/formats/oboInOwl#hasDbXref
  patterns: []
  top_classes: []
```

### OBO Foundry Metadata (for OBO ontologies)

When building contexts for OBO ontologies (GO, MONDO, HP, etc.), the system automatically fetches and includes metadata from the OBO Foundry registry:

```yaml
obo_foundry_metadata:
  id: go
  title: "Gene Ontology"
  description: "The Gene Ontology (GO) provides a framework and set of concepts for describing the functions of gene products from all organisms."
  homepage: "http://geneontology.org/"
  license: "CC BY 4.0"
  contact: "go-discuss@geneontology.org"
  domain: "biological systems"
  imports:
    - RO
```

### LLM-Optimized Fields

For ontologies, the system automatically enriches contexts with fields optimized for LLM-powered multi-hop query planning:

#### `good_for` Field

List of use cases the ontology is useful for:

```yaml
good_for:
  - "Gene function annotation and lookup"
  - "Biological process hierarchies and relationships"
  - "Molecular function classification"
  - "Cellular component localization"
  - "Pathway analysis and systems biology"
  - "Cross-species functional comparison"
```

#### `query_patterns` Field

Common SPARQL query patterns with examples:

```yaml
query_patterns:
  - pattern: "Find all child terms"
    description: "Traverse hierarchy to find more specific terms"
    sparql_hint: "?child rdfs:subClassOf+ ?parent ."
    note: "Use property paths (rdfs:subClassOf+) for transitive hierarchies"
  - pattern: "Find labels for a term"
    description: "Retrieve human-readable labels"
    sparql_hint: "?term rdfs:label ?label ."
  - pattern: "Find cross-references to external databases"
    description: "Link to external databases (UniProt, Ensembl, etc.)"
    sparql_hint: "?term oboInOwl:hasDbXref ?xref ."
```

#### `connects_to` Field

Cross-ontology connections for multi-hop queries:

```yaml
connects_to:
  - ontology: MONDO
    relationship_type: "indirect via genes"
    description: "Disease-gene associations through shared gene annotations"
    example_query: "Find diseases associated with genes annotated with GO:0006915 (apoptosis)"
    mechanism: "External databases (e.g., DisGeNET) link genes to diseases; genes are annotated with GO terms"
    typical_hop_count: 2
    common_use_cases:
      - "Find diseases linked to a specific biological process"
      - "Identify drugs targeting a pathway implicated in disease"
  - ontology: HP
    relationship_type: "indirect via genes"
    description: "Phenotype-gene-function triangulation"
    example_query: "Find phenotypes associated with disruption of GO:0008150 (biological process)"
    mechanism: "Phenotypes (HP) are linked to genes via clinical/model organism data; genes are annotated with GO terms"
    typical_hop_count: 2
```

#### `domains` Field

Domain classifications:

```yaml
domains:
  - biological_process
  - molecular_function
  - cellular_component
  - gene_annotation
```

## OBO Foundry Integration

The system automatically:
1. Downloads the OBO Foundry registry YAML from `https://obofoundry.org/registry/ontologies.yml`
2. Caches the registry locally (refreshed weekly)
3. Matches ontology IDs (case-insensitive)
4. Merges OBO metadata with introspection results

**Cached registry location:** `~/.cache/omnigraph_agent/obo_foundry/ontologies.yml`

## LLM Enrichment

The LLM context enricher automatically:
1. Infers `good_for` use cases from ontology domain and structure
2. Extracts common query patterns from ontology structure
3. Discovers cross-ontology connections from imports and known relationships
4. Extracts domain classifications from OBO Foundry metadata

**Supported ontologies with pre-configured connections:**
- GO (Gene Ontology)
- MONDO (Monarch Disease Ontology)
- HP (Human Phenotype Ontology)
- NCBITaxon (NCBI Taxonomy)

## Format Comparison

| Feature | JSON | YAML |
|---------|------|------|
| Human readability | Low | High |
| Machine parsing | Excellent | Good |
| File size | Smaller | Slightly larger |
| Integration with context packs | Good | Excellent |
| Manual editing | Difficult | Easy |

## Examples

### Example 1: Generate YAML for GO

```bash
python -m omnigraph_agent.context_builder.cli build go --format yaml
```

Output: `dist/context/go_global.yaml`

### Example 2: Generate YAML for MONDO

```bash
python -m omnigraph_agent.context_builder.cli build mondo --format yaml
```

Output: `dist/context/mondo_global.yaml` (includes OBO metadata and LLM fields)

### Example 3: Generate JSON (backward compatible)

```bash
python -m omnigraph_agent.context_builder.cli build nde --format json
# or simply (JSON is default)
python -m omnigraph_agent.context_builder.cli build nde
```

Output: `dist/context/nde_global.json`

## Integration with OKN-WOBD

The YAML format is designed to integrate seamlessly with the OKN-WOBD context pack loader. The enriched metadata fields (`good_for`, `query_patterns`, `connects_to`) enable GPT-4o to make intelligent routing decisions for multi-hop queries across multiple knowledge graphs.

## References

- [OBO Foundry Registry](https://obofoundry.org/registry/)
- [OKN-WOBD Repository](https://github.com/SuLab/OKN-WOBD)
- [Issue #8: YAML Output and LLM Metadata](https://github.com/twhetzel/omnigraph-agent/issues/8)
