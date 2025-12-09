# omnigraph-agent

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

The `context_builder` module generates JSON context files describing the structure and dimensions of knowledge graphs (starting with NDE).

### Usage

```bash
python -m omnigraph_agent.context_builder.cli build nde
```

### Outputs

Outputs are written to:
- `dist/context/nde_global.json` - Global graph context
- `dist/context/nde_<resource>.json` - Repository-specific context files

These JSON files can be consumed by the OmniGraph Agent and the SPARQL Chrome extension for NL→SPARQL generation.