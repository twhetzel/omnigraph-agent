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
- `repo_filter_property`: Set to `"rdf:type"` as a placeholder. Ontologies don't have repositories, so this isn't used.
- `entity_types`: For OBO ontologies, typically `http://www.w3.org/2002/07/owl#Class`. This represents the ontology classes you want to query.

#### Step 2: Create Graph Handler

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
        # Implement repository detection logic
        ...
```

**For Ontologies:**
Create `src/omnigraph_agent/context_builder/graphs/my_ontology.py`:
```python
from pathlib import Path
from typing import Optional
from .ontology import OntologyGraph

class MyOntologyGraph(OntologyGraph):
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "my_ontology.yaml"
        super().__init__(config_path=config_path)
```

#### Step 3: Register Graph Handler

Add to `src/omnigraph_agent/context_builder/graphs/__init__.py`:
```python
from .my_graph import MyGraphGraph
from .my_ontology import MyOntologyGraph

GRAPH_HANDLERS = {
    "nde": NDEGraph,
    "vbo": VBOGraph,
    "my_graph": MyGraphGraph,
    "my_ontology": MyOntologyGraph,
}
```

#### Step 4: Run Introspection (Optional)

```bash
python -m omnigraph_agent.context_builder.cli introspect my_graph --output suggested_my_graph.yaml
```

Review and update the suggested config, then move it to the config directory.

#### Step 5: Build Context Files

```bash
python -m omnigraph_agent.context_builder.cli build my_graph
```

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