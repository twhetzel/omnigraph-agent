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
from pathlib import Path
from .builder import ContextBuilder
from .graphs import get_graph_handler


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
    help='Output directory for JSON context files (default: dist/context)'
)
def build(graph_id: str, output_dir: Path):
    """
    Build context files for a knowledge graph.
    
    GRAPH_ID: Graph identifier (e.g., 'nde')
    
    Examples:
        omnigraph-context-builder build nde
        python -m omnigraph_agent.context_builder.cli build nde
    """
    click.echo(f"Building context files for graph: {graph_id}")
    click.echo(f"Output directory: {output_dir}")
    
    try:
        builder = ContextBuilder(graph_id, output_dir)
        output_files = builder.build()
        
        click.echo(f"\n✓ Successfully generated {len(output_files)} context file(s):")
        for context_type, file_path in output_files.items():
            click.echo(f"  - {file_path} ({context_type})")
        
    except Exception as e:
        click.echo(f"✗ Error building context files: {e}", err=True)
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


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == '__main__':
    main()
