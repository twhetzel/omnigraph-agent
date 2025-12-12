# OmniGraph Agent

## Installation

### Using uv (Recommended)

Set up the Python environment using `uv` as the package manager:

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create a virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install the package in editable mode
uv pip install -e .
```

### Using pip (Alternative)

Install the package in editable mode for local development:

```bash
pip install -e .
```

This will install all dependencies specified in `pyproject.toml` and allow you to modify the code without reinstalling.

## Graph Context Builder (OmniGraph)

The `context_builder` module generates JSON context files describing the structure and dimensions of knowledge graphs and ontologies.

### Building Context Files

#### For Knowledge Graphs (e.g., NDE)

Knowledge graphs contain instance data, entities, and relationships. Some knowledge graphs (like NDE) organize data into multiple repositories/catalogs.

**Note:** In NDE, a "repository" refers to a data catalog that aggregates datasets. Examples:
- **ImmPort** — immunological data repository
- **Vivli** — clinical research data repository
- **Zenodo** — general research data repository
- **Project Tycho** — epidemiological data repository

```bash
# Build all context files for a knowledge graph
python -m omnigraph_agent.context_builder.cli build nde
```

**Outputs:**
- `dist/context/nde_global.json` - Global graph context
- `dist/context/nde_<repository>.json` - Repository-specific context files (if the graph has repositories, e.g., `nde_immport.json`)
- For knowledge graphs without repositories, only the global context file is generated

#### For Ontologies (e.g., VBO, MONDO)

Ontologies define class hierarchies, relationships, and axioms. They are single-source knowledge structures:

```bash
# Build context file for an ontology
python -m omnigraph_agent.context_builder.cli build vbo
```

**Outputs:**
- `dist/context/vbo_global.json` - Global ontology context (no repository-specific files)

### Introspection

Discover properties and structure of a graph/ontology:

```bash
# Introspect a graph to discover properties and generate suggested config
python -m omnigraph_agent.context_builder.cli introspect nde --output suggested_nde.yaml

# For ontologies, discover OBO annotations and relations
python -m omnigraph_agent.context_builder.cli introspect vbo --output suggested_vbo.yaml
```

### Creating Context Files for New Graphs/Ontologies

#### Step 1: Create Configuration File

Create a YAML config file in `src/omnigraph_agent/context_builder/config/`:

**For Knowledge Graphs:**
```yaml
graph_id: "my_graph"
endpoint: "https://example.com/sparql"
repo_filter_property: "schema:includedInDataCatalog"  # Property that links entities to repositories/catalogs
entity_types:
  - "http://schema.org/Dataset"  # Main entity types in your graph (e.g., Dataset, Person, Organization)
dimensions: []  # Will be populated via introspection
text_blurb: "Description of your knowledge graph"
```

**Configuration fields:**
- `repo_filter_property`: The RDF property that links entities to repositories/catalogs within the SPARQL endpoint (e.g., `schema:includedInDataCatalog` for NDE). The context builder uses this property to:
  - Discover repositories by querying for distinct values of this property
  - Filter SPARQL queries to scope results to a specific repository when building repository-specific context files
  - Example: In NDE, `schema:includedInDataCatalog` links Dataset entities to DataCatalog entities (ImmPort, Vivli, etc.)
- `entity_types`: List of RDF types (full IRIs) that represent the main entities in your graph. These are used to filter queries and discover properties. Common examples: `http://schema.org/Dataset`, `http://schema.org/Person`, `http://schema.org/Organization`.

**For Ontologies:**
```yaml
graph_id: "my_ontology"
endpoint: "https://ubergraph.apps.renci.org/sparql"
repo_filter_property: "rdf:type"  # Placeholder - ontologies don't use repository filters
entity_types:
  - "http://www.w3.org/2002/07/owl#Class"  # Typically owl:Class for OBO ontologies
dimensions: []  # Will be populated via introspection
text_blurb: "Description of your ontology"
```

**Configuration fields:**
- `repo_filter_property`: Set to `""` (empty string) for ontologies. Ontologies don't have repositories, so this isn't used.
- `entity_types`: For OBO ontologies, typically `http://www.w3.org/2002/07/owl#Class`. This represents the ontology classes you want to query.

#### Step 2: Build Context Files (Generic Handler)

**The system now includes generic handlers that work automatically!** For most graphs, you can skip creating custom handler classes. The system will:

- **Auto-detect** your config file
- **Use `GenericGraph`** for knowledge graphs (when `repo_filter_property` is set)
- **Use `GenericOntologyGraph`** for ontologies (when `repo_filter_property` is empty)

Simply run:

```bash
python -m omnigraph_agent.context_builder.cli build my_graph
```

The generic handlers will:
- Automatically detect repositories using the `repo_filter_property` from your config
- Work with any SPARQL endpoint
- Handle both knowledge graphs and ontologies

**Custom Handlers (Optional)**

If you need custom logic (e.g., special repository detection), you can still create a custom handler:

**For Knowledge Graphs:**
Create `src/omnigraph_agent/context_builder/graphs/my_graph.py`:
```python
from pathlib import Path
from typing import List, Dict, Optional
from .knowledge_graph import KnowledgeGraph

class MyGraphGraph(KnowledgeGraph):
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "my_graph.yaml"
        super().__init__(config_path=config_path)
    
    def get_repositories(self) -> List[Dict[str, str]]:
        # Custom repository detection logic
        ...
```

Then register it in `src/omnigraph_agent/context_builder/graphs/__init__.py`:
```python
from .my_graph import MyGraphGraph

GRAPH_HANDLERS = {
    "nde": NDEGraph,
    "vbo": VBOGraph,
    "my_graph": MyGraphGraph,  # Custom handler takes precedence
}
```

#### Step 3: Run Introspection (Optional)

```bash
python -m omnigraph_agent.context_builder.cli introspect my_graph --output suggested_my_graph.yaml
```

Review and update the suggested config, then move it to the config directory.

#### Step 4: Build Context Files

```bash
python -m omnigraph_agent.context_builder.cli build my_graph
```

**That's it!** With the generic handler system, you only need to create a config file. The system will automatically discover and use the appropriate handler.

### Context File Structure

Context files include:
- **Graph metadata**: `graph_id`, `endpoint`, `entity_types`
- **Dimensions**: Properties with coverage, distinct values, top values
- **Prefixes**: Prefix to IRI mappings
- **Query hints** (for ontologies): Namespace scope, reasoning mode, query patterns

### Output Location

All context files are written to `dist/context/` and can be consumed by:
- OmniGraph Agent for NL→SPARQL generation
- SPARQL Chrome extension for query generation

## Bridge Graph System

The bridge graph system generates cross-graph links between entities in different FRINK registry graphs using shared identifiers (e.g., GSE, NCT, MONDO, HGNC).

### Overview

Bridge graphs enable querying across multiple knowledge graphs by:
1. **Discovering shared identifiers**: Automatically finds identifier patterns (GSE, NCT, MONDO, etc.) that appear in multiple graphs
2. **Generating linksets**: Creates RDF linksets that connect entities across graphs based on matching identifier values
3. **Providing bridge context**: Generates JSON summaries of available cross-graph joins

### Prerequisites

Before generating bridge graphs, ensure you have context files for the graphs you want to link:

```bash
# Generate context files for all graphs you want to link
python -m omnigraph_agent.context_builder.cli build nde
python -m omnigraph_agent.context_builder.cli build mondo
# ... build contexts for other graphs
```

### Generating Linksets

#### Single Graph Pair

Generate linksets between two specific graphs:

```bash
# Generate linksets between NDE and another graph
python -m omnigraph_agent.context_builder.cli bridge generate nde bioproject
```

This will:
- Find shared identifier patterns (e.g., GSE, MONDO, NCT)
- Query both graphs for entities with matching identifiers
- Generate RDF linkset files in `dist/bridge/linksets/`

**Outputs:**
- `dist/bridge/linksets/nde__bioproject-gse.ttl` - Linkset for GSE IDs
- `dist/bridge/linksets/nde__bioproject-mondo.ttl` - Linkset for MONDO IDs
- etc.

#### All Graph Pairs

Generate linksets for all graph pairs with shared join keys:

```bash
# Generate linksets for all pairs
python -m omnigraph_agent.context_builder.cli bridge generate-all
```

This automatically:
- Discovers all graph pairs that share identifier patterns
- Generates linksets only for pairs with actual shared keys
- Skips pairs without overlap

### Discovering Shared Join Keys

Discover which graph pairs can be linked (without generating):

```bash
# Discover pairs with shared join keys
python -m omnigraph_agent.context_builder.cli bridge discover
```

**Output:**
```
Found 15 graph pair(s) with shared join keys:

  nde → bioproject
    Shared keys: GSE, MONDO, NCT

  nde → spoke-okn
    Shared keys: MONDO, HGNC

  ...
```

### Bridge Context Files

Generate JSON summaries of linksets for easy querying:

```bash
# Generate bridge context JSON files
python -m omnigraph_agent.context_builder.cli bridge generate-contexts
```

**Outputs:**
- `dist/context/bridge/nde__bioproject.json` - Bridge context for NDE → bioproject
- `dist/context/bridge/index.json` - Global index of all bridges

**Bridge context structure:**
```json
{
  "source_graph": "https://frink.apps.renci.org/nde/sparql",
  "target_graph": "https://frink.example.org/bioproject",
  "source_graph_id": "nde",
  "target_graph_id": "bioproject",
  "linksets": [
    {
      "join_key_type": "GSE_ID",
      "num_links": 10234,
      "min_confidence": 1.0,
      "max_confidence": 1.0,
      "linkset_iri": "https://wobd.org/bridge/linkset/nde__bioproject-gse"
    }
  ]
}
```

### Listing Available Bridges

List all available bridge contexts:

```bash
# List available bridges
python -m omnigraph_agent.context_builder.cli bridge list
```

### Viewing Bridge Summary

View detailed summary of links between two graphs:

```bash
# View summary of NDE → bioproject bridge
python -m omnigraph_agent.context_builder.cli bridge summary nde bioproject
```

### Using Bridge Graphs in SPARQL Queries

Bridge graphs enable federated queries across multiple graphs. Example:

```sparql
PREFIX wobd-bridge: <https://wobd.org/bridge#>
PREFIX void: <http://rdfs.org/ns/void#>

# Find all NDE datasets linked to bioproject entities via GSE IDs
SELECT ?nde_dataset ?bioproject_entity ?gse_id
WHERE {
    # Query NDE graph
    SERVICE <https://frink.apps.renci.org/nde/sparql> {
        ?nde_dataset a schema:Dataset .
        ?nde_dataset schema:identifier ?gse_id .
        FILTER (STRSTARTS(STR(?gse_id), "GSE"))
    }
    
    # Use bridge graph to find matching bioproject entity
    ?link wobd-bridge:sourceNode ?nde_dataset ;
          wobd-bridge:targetNode ?bioproject_entity ;
          wobd-bridge:joinKeyValue ?gse_id ;
          wobd-bridge:joinKeyType wobd-bridge:GSE_ID .
    
    # Query bioproject graph
    SERVICE <https://frink.example.org/bioproject> {
        ?bioproject_entity a biolink:Bioproject .
    }
}
```

### Supported Join Key Types

The system automatically recognizes these identifier patterns:
- **GSE_ID**: GEO Series identifiers (GSE12345)
- **NCT_ID**: ClinicalTrials.gov identifiers (NCT00012345)
- **MONDO_ID**: MONDO disease ontology (MONDO:0000001)
- **HGNC_ID**: HGNC gene identifiers (HGNC:1234)
- **GO_ID**: Gene Ontology (GO:0008150)
- **DOID_ID**: Disease Ontology (DOID:4)
- **HP_ID**: Human Phenotype Ontology (HP:0000001)
- **CHEBI_ID**: ChEBI (CHEBI:15365)
- **UniProtKB_ID**: UniProt Knowledgebase (UniProtKB:P12345)
- **PMID_ID**: PubMed (PMID:12345678)
- **PMC_ID**: PubMed Central (PMC123456)

Additional patterns are automatically discovered from context files.

### Semantic Matching

The bridge system includes a **semantic mapping layer** that understands when different identifier prefixes refer to the same semantic concept:

**Taxonomies**: NCBITaxon, UniProtKB (taxon), ITIS, GBIF
- Example: A graph using `NCBITaxon:9606` (human) can link to another using `UniProtKB` taxon IDs

**Genes**: HGNC, Ensembl, MGI, ZFIN, FlyBase, WormBase, RGD
- Example: A graph using `HGNC:1100` can link to another using `Ensembl:ENSG00000139618`

**Diseases**: MONDO, DOID, OMIM, Orphanet
- Example: A graph using `MONDO:0000001` can link to another using `DOID:4`

**Publications**: PMID, PMC, DOI
- Example: A graph using `PMID:12345678` can link to another using `PMC:123456`

When generating linksets, the system will:
1. **Exact matches**: Link entities with identical identifier prefixes (e.g., both use GSE)
2. **Semantic matches**: Link entities with semantically related identifiers (e.g., NCBITaxon ↔ UniProtKB taxon)

This enables the NL→SPARQL system to understand that queries about "taxonomies" or "species" can work across graphs even when they use different identifier systems.

### FRINK Registry Graphs

The bridge system supports all graphs in the FRINK registry, including:
- NDE (NIAID Data Ecosystem)
- protookn graphs (biobricks-*, biohealth, spoke-okn, etc.)
- Ontologies (mondo, vbo, ubergraph, etc.)

See [FRINK Registry](https://frink.renci.org/registry/) for the complete list.