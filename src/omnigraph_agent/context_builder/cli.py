"""
CLI entrypoint for the context builder.

Planned command usage:
    python -m omnigraph_agent.context_builder.cli build nde

This command will:
1. Load config/nde.yaml
2. Perform schema-independent introspection
3. Generate:
   - dist/context/nde_global.json
   - dist/context/nde_<repo>.json for each repository
4. Write the JSON files to dist/context/
"""

import click
import yaml
from pathlib import Path
from typing import Optional
from .builder import ContextBuilder
from .graphs import get_graph_handler
from .sources import (
    discover_named_graphs,
    graph_uri_to_graph_id,
    build_ubergraph_ontology_config,
    load_ontology_list,
    get_frink_graph_list,
    build_frink_kg_config,
    DEFAULT_UBERGRAPH_ENDPOINT,
    UBERGRAPH_GRAPHS_PREFIX,
    ONTOLOGIES_TXT_URL,
)
from ..bridge.linkset_builder import LinksetBuilder
from ..bridge.batch_bridge_generator import BatchBridgeGenerator
from ..bridge.bridge_context_generator import BridgeContextGenerator
from ..bridge.graph_registry import GraphRegistry


@click.group()
def cli():
    """OmniGraph Context Builder - Generate JSON context files for knowledge graphs."""
    pass


@cli.command()
@click.argument('graph_id', type=str)
@click.option(
    '--output-dir',
    '-o',
    type=click.Path(path_type=Path),
    default=Path('dist/context'),
    help='Output directory for context files (default: dist/context)'
)
@click.option(
    '--format',
    'output_format',
    type=click.Choice(['json', 'yaml'], case_sensitive=False),
    default='json',
    help='Output format: json or yaml (default: json)'
)
def build(graph_id: str, output_dir: Path, output_format: str):
    """
    Build context files for a knowledge graph.
    
    GRAPH_ID: Graph identifier (e.g., 'nde')
    
    Examples:
        omnigraph-context-builder build nde
        omnigraph-context-builder build nde --format yaml
        python -m omnigraph_agent.context_builder.cli build nde --format yaml
    """
    click.echo(f"Building context files for graph: {graph_id}")
    click.echo(f"Output directory: {output_dir}")
    click.echo(f"Output format: {output_format}")
    
    try:
        builder = ContextBuilder(graph_id, output_dir, output_format=output_format)
        output_files = builder.build()
        
        click.echo(f"\n✓ Successfully generated {len(output_files)} context file(s):")
        for context_type, file_path in output_files.items():
            click.echo(f"  - {file_path} ({context_type})")
        
    except Exception as e:
        click.echo(f"✗ Error building context files: {e}", err=True)
        raise click.Abort()


@cli.command('build-ubergraph')
@click.option(
    '--endpoint',
    default=DEFAULT_UBERGRAPH_ENDPOINT,
    help=f'Ubergraph SPARQL endpoint (default: {DEFAULT_UBERGRAPH_ENDPOINT})'
)
@click.option(
    '--output-dir',
    '-o',
    type=click.Path(path_type=Path),
    default=Path('dist/context'),
    help='Output directory for context files (default: dist/context)'
)
@click.option(
    '--format',
    'output_format',
    type=click.Choice(['json', 'yaml'], case_sensitive=False),
    default='json',
    help='Output format: json or yaml (default: json)'
)
@click.option(
    '--limit',
    type=int,
    default=2000,
    help='Maximum number of named graphs to discover and process (default: 2000)'
)
@click.option(
    '--skip-existing-config/--no-skip-existing-config',
    default=True,
    help='Skip graph_ids that already have a config file (default: on)'
)
@click.option(
    '--write-configs',
    is_flag=True,
    help='Write generated configs to config/ for hand-editing'
)
def build_ubergraph(
    endpoint: str,
    output_dir: Path,
    output_format: str,
    limit: int,
    skip_existing_config: bool,
    write_configs: bool,
):
    """
    Discover Ubergraph named graphs and generate context files for each.

    Queries the endpoint for GRAPH ?g { ?s ?p ?o }, keeps URIs under
    .../graphs/, and builds a minimal ontology config per graph_id.
    Ontologies produce only a global context file (no repositories).

    Examples:
        omnigraph-context-builder build-ubergraph
        omnigraph-context-builder build-ubergraph --limit 10 --format yaml
        omnigraph-context-builder build-ubergraph --write-configs
    """
    # Fetch at least 100 from the endpoint so we have a chance to see /graphs/ URIs
    # when limit is small (order is undefined; FILTER in SPARQL causes timeouts).
    discovery_limit = max(limit, 100)
    click.echo(f"Discovering named graphs at {endpoint} (fetch up to {discovery_limit}, process up to {limit})...")
    try:
        uris = discover_named_graphs(endpoint, limit=discovery_limit, uri_prefix=UBERGRAPH_GRAPHS_PREFIX)
    except Exception as e:
        click.echo(f"✗ Discovery failed: {e}", err=True)
        raise click.Abort()

    # Map URI -> graph_id, deduplicate, and cap at --limit
    seen: set = set()
    items: list = []
    for g_uri in uris:
        gid = graph_uri_to_graph_id(g_uri, UBERGRAPH_GRAPHS_PREFIX)
        if not gid or gid in seen:
            continue
        seen.add(gid)
        items.append((g_uri, gid))
        if len(items) >= limit:
            break

    if not items:
        click.echo("No Ubergraph /graphs/ named graphs found.")
        click.echo("Ubergraph may not expose those URIs via GRAPH ?g. Try: omnigraph-context-builder build-ubergraph-ontologies")
        return

    click.echo(f"Found {len(items)} graph(s). Building context files...")
    config_dir = Path(__file__).parent / "config"
    output_dir.mkdir(parents=True, exist_ok=True)
    ok, errs = 0, []

    for g_uri, gid in items:
        if skip_existing_config and (config_dir / f"{gid}.yaml").exists():
            click.echo(f"  [skip] {gid} (existing config)")
            continue
        cfg = build_ubergraph_ontology_config(gid, g_uri, endpoint)
        if write_configs:
            p = config_dir / f"{gid}.yaml"
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w") as f:
                yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
            click.echo(f"  [wrote config] {p}")
        try:
            builder = ContextBuilder(gid, output_dir, output_format=output_format, config=cfg)
            files = builder.build()
            for _k, path in files.items():
                click.echo(f"  ✓ {path.name}")
            ok += 1
        except Exception as e:
            errs.append((gid, str(e)))
            click.echo(f"  ✗ {gid}: {e}", err=True)

    click.echo(f"\nDone: {ok} built, {len(errs)} failed.")
    if errs:
        for gid, msg in errs:
            click.echo(f"  - {gid}: {msg}", err=True)
        raise click.Abort()


@cli.command('build-ubergraph-ontologies')
@click.option(
    '--ontologies-url',
    default=ONTOLOGIES_TXT_URL,
    help=f'URL of ontologies.txt (default: {ONTOLOGIES_TXT_URL})'
)
@click.option(
    '--ontologies-file',
    type=click.Path(path_type=Path, exists=True),
    default=None,
    help='Local ontologies.txt file (overrides --ontologies-url if set)'
)
@click.option(
    '--endpoint',
    default=DEFAULT_UBERGRAPH_ENDPOINT,
    help=f'Ubergraph SPARQL endpoint (default: {DEFAULT_UBERGRAPH_ENDPOINT})'
)
@click.option(
    '--output-dir',
    '-o',
    type=click.Path(path_type=Path),
    default=Path('dist/context'),
    help='Output directory for context files (default: dist/context)'
)
@click.option(
    '--format',
    'output_format',
    type=click.Choice(['json', 'yaml'], case_sensitive=False),
    default='json',
    help='Output format: json or yaml (default: json)'
)
@click.option(
    '--limit',
    type=int,
    default=2000,
    help='Maximum number of ontologies to process (default: 2000)'
)
@click.option(
    '--skip-existing-config/--no-skip-existing-config',
    default=True,
    help='Skip graph_ids that already have a config file (default: on)'
)
@click.option(
    '--write-configs',
    is_flag=True,
    help='Write generated configs to config/ for hand-editing'
)
def build_ubergraph_ontologies(
    ontologies_url: str,
    ontologies_file: Optional[Path],
    endpoint: str,
    output_dir: Path,
    output_format: str,
    limit: int,
    skip_existing_config: bool,
    write_configs: bool,
):
    """
    Build context files for Ubergraph ontologies from ontologies.txt.

    Reads ontology URLs from Ubergraph's ontologies.txt (or a local file),
    derives graph_id from each URL, and builds a minimal config using
    FROM <http://ubergraph.apps.renci.org/graphs/{graph_id}>.

    Examples:
        omnigraph-context-builder build-ubergraph-ontologies
        omnigraph-context-builder build-ubergraph-ontologies --limit 5 --format yaml
        omnigraph-context-builder build-ubergraph-ontologies --ontologies-file ./ontologies.txt
    """
    source = str(ontologies_file) if ontologies_file else ontologies_url
    click.echo(f"Loading ontology list from {source}...")
    try:
        items = load_ontology_list(source)
    except Exception as e:
        click.echo(f"✗ Failed to load ontology list: {e}", err=True)
        raise click.Abort()

    items = items[:limit]
    if not items:
        click.echo("No ontologies to process.")
        return

    click.echo(f"Found {len(items)} ontology/ies. Building context files...")
    config_dir = Path(__file__).parent / "config"
    output_dir.mkdir(parents=True, exist_ok=True)
    ok, errs = 0, []

    for gid, named_uri in items:
        if skip_existing_config and (config_dir / f"{gid}.yaml").exists():
            click.echo(f"  [skip] {gid} (existing config)")
            continue
        cfg = build_ubergraph_ontology_config(gid, named_uri, endpoint)
        if write_configs:
            p = config_dir / f"{gid}.yaml"
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w") as f:
                yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
            click.echo(f"  [wrote config] {p}")
        try:
            builder = ContextBuilder(gid, output_dir, output_format=output_format, config=cfg)
            files = builder.build()
            for _k, path in files.items():
                click.echo(f"  ✓ {path.name}")
            ok += 1
        except Exception as e:
            errs.append((gid, str(e)))
            click.echo(f"  ✗ {gid}: {e}", err=True)

    click.echo(f"\nDone: {ok} built, {len(errs)} failed.")
    if errs:
        for gid, msg in errs:
            click.echo(f"  - {gid}: {msg}", err=True)
        raise click.Abort()


@cli.command('build-frink')
@click.option(
    '--output-dir',
    '-o',
    type=click.Path(path_type=Path),
    default=Path('dist/context'),
    help='Output directory for context files (default: dist/context)'
)
@click.option(
    '--format',
    'output_format',
    type=click.Choice(['json', 'yaml'], case_sensitive=False),
    default='json',
    help='Output format: json or yaml (default: json)'
)
@click.option(
    '--limit',
    type=int,
    default=None,
    help='Maximum number of FRINK graphs to process (default: all)'
)
@click.option(
    '--write-configs',
    is_flag=True,
    help='Write generated configs to config/ for graphs that do not yet have one'
)
def build_frink(
    output_dir: Path,
    output_format: str,
    limit: Optional[int],
    write_configs: bool,
):
    """
    Build context files for FRINK registry knowledge graphs.

    Uses the FRINK registry list (https://frink.renci.org/registry/). For each
    graph, loads config from config/{graph_id}.yaml if it exists; otherwise
    builds a minimal config from the FRINK endpoint. Always builds (refreshes)
    context; use config files to customize nde, spoke-okn, etc.

    The same pattern can be reused for other knowledge-graph registries.

    Examples:
        omnigraph-context-builder build-frink --format json
        omnigraph-context-builder build-frink --limit 5 --write-configs
    """
    click.echo("Loading FRINK graph list...")
    try:
        items = get_frink_graph_list(limit=limit)
    except Exception as e:
        click.echo(f"✗ Failed to load FRINK graph list: {e}", err=True)
        raise click.Abort()

    if not items:
        click.echo("No FRINK graphs to process.")
        return

    config_dir = Path(__file__).parent / "config"
    output_dir.mkdir(parents=True, exist_ok=True)
    ok, errs = 0, []

    for gid, endpoint in items:
        config_path = config_dir / f"{gid}.yaml"
        if config_path.exists():
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
        else:
            cfg = build_frink_kg_config(gid, endpoint)
            if write_configs:
                config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(config_path, "w") as f:
                    yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
                click.echo(f"  [wrote config] {config_path}")
        try:
            builder = ContextBuilder(gid, output_dir, output_format=output_format, config=cfg)
            files = builder.build()
            for _k, path in files.items():
                click.echo(f"  ✓ {gid}: {path.name}")
            ok += 1
        except Exception as e:
            errs.append((gid, str(e)))
            click.echo(f"  ✗ {gid}: {e}", err=True)

    click.echo(f"\nDone: {ok} built, {len(errs)} failed.")
    if errs:
        for gid, msg in errs:
            click.echo(f"  - {gid}: {msg}", err=True)
        raise click.Abort()


@cli.command()
@click.argument('graph_id', type=str)
@click.option(
    '--output',
    '-o',
    type=click.Path(path_type=Path),
    help='Output path for suggested config YAML file (optional)'
)
@click.option(
    '--properties-limit',
    type=int,
    default=50,
    help='Maximum number of properties to discover (default: 50)'
)
def introspect(graph_id: str, output: Path, properties_limit: int):
    """
    Introspect a knowledge graph to discover properties and generate suggested config.
    
    GRAPH_ID: Graph identifier (e.g., 'nde')
    
    Examples:
        omnigraph-context-builder introspect nde
        omnigraph-context-builder introspect nde --output suggested_config.yaml
    """
    click.echo(f"Introspecting graph: {graph_id}")
    
    try:
        handler_cls = get_graph_handler(graph_id)
        graph = handler_cls()
        
        # Run introspection
        config = graph.generate_suggested_config(
            output_path=output,
            properties_limit=properties_limit,
        )
        
        if not output:
            # Print summary if no output file specified
            click.echo("\n✓ Introspection complete!")
            click.echo(f"\nDiscovered {len(config['dimensions'])} dimensions")
            click.echo(f"Discovered {len(config['entity_types'])} entity types")
            click.echo(f"Suggested repo_filter_property: {config['repo_filter_property']}")
            click.echo("\nTop properties:")
            for dim in config['dimensions'][:5]:
                click.echo(f"  - {dim['property']} ({dim['name']})")
        
    except Exception as e:
        click.echo(f"✗ Error during introspection: {e}", err=True)
        raise click.Abort()


@cli.group()
def bridge():
    """Bridge graph generation commands."""
    pass


@bridge.command()
@click.argument('source_graph_id', type=str)
@click.argument('target_graph_id', type=str)
@click.option(
    '--context-dir',
    type=click.Path(path_type=Path),
    default=Path('dist/context'),
    help='Directory containing context JSON files (default: dist/context)'
)
@click.option(
    '--output-dir',
    '-o',
    type=click.Path(path_type=Path),
    default=Path('dist/bridge/linksets'),
    help='Output directory for linkset RDF files (default: dist/bridge/linksets)'
)
def generate(source_graph_id: str, target_graph_id: str, context_dir: Path, output_dir: Path):
    """
    Generate linksets between two specific graphs.
    
    SOURCE_GRAPH_ID: Source graph identifier (e.g., 'nde')
    TARGET_GRAPH_ID: Target graph identifier (e.g., 'bioproject')
    
    Examples:
        omnigraph-context-builder bridge generate nde bioproject
    """
    click.echo(f"Generating linksets: {source_graph_id} → {target_graph_id}")
    
    source_context_path = context_dir / f"{source_graph_id}_global.json"
    target_context_path = context_dir / f"{target_graph_id}_global.json"
    
    if not source_context_path.exists():
        click.echo(f"✗ Source context file not found: {source_context_path}", err=True)
        raise click.Abort()
    
    if not target_context_path.exists():
        click.echo(f"✗ Target context file not found: {target_context_path}", err=True)
        raise click.Abort()
    
    try:
        builder = LinksetBuilder(source_context_path, target_context_path)
        shared_keys = builder.find_shared_join_keys()
        
        if not shared_keys:
            click.echo("✗ No shared join keys found between these graphs", err=True)
            raise click.Abort()
        
        click.echo(f"Found shared join keys: {', '.join(shared_keys)}")
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for join_key_prefix in shared_keys:
            click.echo(f"  Generating linkset for {join_key_prefix}...")
            linkset_graph = builder.build_linkset(join_key_prefix)
            
            linkset_filename = f"{source_graph_id}__{target_graph_id}-{join_key_prefix.lower()}.ttl"
            linkset_path = output_dir / linkset_filename
            
            linkset_graph.serialize(destination=str(linkset_path), format='turtle')
            click.echo(f"    ✓ Generated {linkset_filename}")
        
        click.echo(f"\n✓ Successfully generated {len(shared_keys)} linkset(s)")
    
    except Exception as e:
        click.echo(f"✗ Error generating linksets: {e}", err=True)
        raise click.Abort()


@bridge.command()
@click.option(
    '--context-dir',
    type=click.Path(path_type=Path),
    default=Path('dist/context'),
    help='Directory containing context JSON files (default: dist/context)'
)
@click.option(
    '--output-dir',
    '-o',
    type=click.Path(path_type=Path),
    default=Path('dist/bridge/linksets'),
    help='Output directory for linkset RDF files (default: dist/bridge/linksets)'
)
def generate_all(context_dir: Path, output_dir: Path):
    """
    Generate linksets for all graph pairs with shared join keys.
    
    Examples:
        omnigraph-context-builder bridge generate-all
    """
    click.echo("Generating linksets for all graph pairs...")
    
    try:
        generator = BatchBridgeGenerator(context_dir, output_dir)
        generated_files = generator.generate_all_linksets(verbose=True)
        
        click.echo(f"\n✓ Successfully generated {len(generated_files)} linkset file(s)")
    
    except Exception as e:
        click.echo(f"✗ Error generating linksets: {e}", err=True)
        raise click.Abort()


@bridge.command()
@click.option(
    '--context-dir',
    type=click.Path(path_type=Path),
    default=Path('dist/context'),
    help='Directory containing context JSON files (default: dist/context)'
)
def discover(context_dir: Path):
    """
    Discover which graph pairs share join keys (without generating).
    
    Examples:
        omnigraph-context-builder bridge discover
    """
    click.echo("Discovering graph pairs with shared join keys...")
    
    try:
        registry = GraphRegistry(context_dir)
        pairs_with_keys = registry.find_pairs_with_shared_join_keys(include_semantic=True)
        
        if not pairs_with_keys:
            click.echo("No graph pairs with shared join keys found")
            return
        
        click.echo(f"\nFound {len(pairs_with_keys)} graph pair(s) with shared join keys:\n")
        
        for source_id, target_id, exact_keys, semantic_keys in pairs_with_keys:
            click.echo(f"  {source_id} → {target_id}")
            if exact_keys:
                click.echo(f"    Exact matches: {', '.join(exact_keys)}")
            if semantic_keys:
                click.echo(f"    Semantic matches: {', '.join(semantic_keys)} (different prefixes, same category)")
            click.echo()
    
    except Exception as e:
        click.echo(f"✗ Error discovering pairs: {e}", err=True)
        raise click.Abort()


@bridge.command()
@click.option(
    '--context-dir',
    type=click.Path(path_type=Path),
    default=Path('dist/context/bridge'),
    help='Directory containing bridge context JSON files (default: dist/context/bridge)'
)
def list(context_dir: Path):
    """
    List available bridge contexts.
    
    Examples:
        omnigraph-context-builder bridge list
    """
    click.echo("Available bridge contexts:")
    
    try:
        index_file = context_dir / "index.json"
        if index_file.exists():
            import json
            with open(index_file, 'r') as f:
                index_data = json.load(f)
            
            click.echo(f"\nTotal bridges: {index_data.get('total_bridges', 0)}")
            click.echo(f"Total linksets: {index_data.get('total_linksets', 0)}\n")
            
            for bridge in index_data.get('bridges', []):
                click.echo(f"  {bridge['source']} → {bridge['target']} ({bridge['file']})")
        else:
            # List individual bridge files
            bridge_files = sorted(context_dir.glob("*.json"))
            if not bridge_files:
                click.echo("  No bridge contexts found")
            else:
                for bridge_file in bridge_files:
                    if bridge_file.name != "index.json":
                        click.echo(f"  {bridge_file.stem}")
    
    except Exception as e:
        click.echo(f"✗ Error listing bridges: {e}", err=True)
        raise click.Abort()


@bridge.command()
@click.argument('source_graph_id', type=str)
@click.argument('target_graph_id', type=str)
@click.option(
    '--context-dir',
    type=click.Path(path_type=Path),
    default=Path('dist/context/bridge'),
    help='Directory containing bridge context JSON files (default: dist/context/bridge)'
)
def summary(source_graph_id: str, target_graph_id: str, context_dir: Path):
    """
    Show summary of available joins between two graphs.
    
    SOURCE_GRAPH_ID: Source graph identifier (e.g., 'nde')
    TARGET_GRAPH_ID: Target graph identifier (e.g., 'bioproject')
    
    Examples:
        omnigraph-context-builder bridge summary nde bioproject
    """
    bridge_file = context_dir / f"{source_graph_id}__{target_graph_id}.json"
    
    if not bridge_file.exists():
        click.echo(f"✗ Bridge context not found: {bridge_file}", err=True)
        click.echo("  Run 'bridge generate' first to create linksets", err=True)
        raise click.Abort()
    
    try:
        import json
        from ..bridge.bridge_context_schema import BridgeContext
        
        with open(bridge_file, 'r') as f:
            data = json.load(f)
            bridge_context = BridgeContext(**data)
        
        click.echo(f"Bridge: {source_graph_id} → {target_graph_id}")
        click.echo(f"Source: {bridge_context.source_graph}")
        click.echo(f"Target: {bridge_context.target_graph}")
        click.echo(f"\nLinksets ({len(bridge_context.linksets)}):")
        
        for linkset in bridge_context.linksets:
            click.echo(f"\n  Join Key: {linkset.join_key_type}")
            click.echo(f"    Links: {linkset.num_links}")
            click.echo(f"    Confidence: {linkset.min_confidence:.2f} - {linkset.max_confidence:.2f}")
            click.echo(f"    IRI: {linkset.linkset_iri}")
    
    except Exception as e:
        click.echo(f"✗ Error reading bridge context: {e}", err=True)
        raise click.Abort()


@bridge.command()
@click.option(
    '--linkset-dir',
    type=click.Path(path_type=Path),
    default=Path('dist/bridge/linksets'),
    help='Directory containing linkset RDF files (default: dist/bridge/linksets)'
)
@click.option(
    '--context-dir',
    type=click.Path(path_type=Path),
    default=Path('dist/context'),
    help='Directory containing graph context JSON files (default: dist/context)'
)
@click.option(
    '--output-dir',
    '-o',
    type=click.Path(path_type=Path),
    default=Path('dist/context/bridge'),
    help='Output directory for bridge context JSON files (default: dist/context/bridge)'
)
def generate_contexts(linkset_dir: Path, context_dir: Path, output_dir: Path):
    """
    Generate bridge context JSON files from linkset RDF files.
    
    Examples:
        omnigraph-context-builder bridge generate-contexts
    """
    click.echo("Generating bridge context files...")
    
    try:
        generator = BridgeContextGenerator(linkset_dir, context_dir, output_dir)
        generated_files = generator.generate_all_bridge_contexts(verbose=True)
        
        # Generate index
        index_file = generator.generate_index()
        click.echo(f"\n✓ Generated index: {index_file}")
        click.echo(f"✓ Successfully generated {len(generated_files)} bridge context file(s)")
    
    except Exception as e:
        click.echo(f"✗ Error generating bridge contexts: {e}", err=True)
        raise click.Abort()


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == '__main__':
    main()
