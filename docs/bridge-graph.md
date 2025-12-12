# Bridge Graph System Documentation

## Purpose

The bridge graph system enables cross-graph querying by creating explicit links between entities in different FRINK registry graphs. These links are based on:

1. **Exact identifier matches**: Identical identifier prefixes (e.g., both graphs use GSE, MONDO)
2. **Semantic identifier matches**: Different prefixes that refer to the same semantic concept (e.g., NCBITaxon ↔ UniProtKB for taxonomies, HGNC ↔ Ensembl for genes)

This semantic matching enables the NL→SPARQL system to understand that queries about "taxonomies", "genes", or "diseases" can work across graphs even when they use different identifier systems.

## Architecture

```
┌─────────────────────┐
│ Context Files       │  (identifier_info)
│  - nde_global.json  │
│  - mondo_global.json│
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Linkset Builder     │  (finds shared keys, generates RDF)
│  - Match entities   │
│  - Create links     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Bridge Graph RDF    │
│  - Linksets          │
│  - LinkAssertions   │
└─────────────────────┘
```

## Schema Reference

### Core Classes

- **wobd-bridge:LinkAssertion**: A single assertion linking a source node to a target node
- **wobd-bridge:JoinKeyType**: Category of identifier used for joining (e.g., GSE_ID, MONDO_ID)
- **wobd-bridge:BridgeGraph**: Dataset containing linksets

### Core Properties

- **wobd-bridge:sourceNode**: Source entity IRI
- **wobd-bridge:targetNode**: Target entity IRI
- **wobd-bridge:sourceGraph**: Source graph endpoint
- **wobd-bridge:targetGraph**: Target graph endpoint
- **wobd-bridge:joinKeyType**: Type of identifier used (e.g., wobd-bridge:GSE_ID)
- **wobd-bridge:joinKeyValue**: Normalized identifier value
- **wobd-bridge:confidence**: Confidence score (0.0-1.0)
- **wobd-bridge:inLinkset**: Linkset this assertion belongs to

### VOID Integration

Linksets use VOID vocabulary:
- **void:Linkset**: Groups link assertions between two datasets
- **void:subjectsTarget**: Source dataset
- **void:objectsTarget**: Target dataset
- **void:linkPredicate**: Predicate used for linking (typically owl:sameAs)

## Usage Examples

### Basic Workflow

1. **Generate context files** (with identifier information):
   ```bash
   python -m omnigraph_agent.context_builder.cli build nde
   python -m omnigraph_agent.context_builder.cli build mondo
   ```

2. **Discover shared join keys**:
   ```bash
   python -m omnigraph_agent.context_builder.cli bridge discover
   ```

3. **Generate linksets**:
   ```bash
   python -m omnigraph_agent.context_builder.cli bridge generate nde mondo
   ```

4. **Generate bridge context JSON**:
   ```bash
   python -m omnigraph_agent.context_builder.cli bridge generate-contexts
   ```

### Batch Processing

Generate linksets for all graph pairs:

```bash
python -m omnigraph_agent.context_builder.cli bridge generate-all
```

This will:
- Automatically discover all pairs with shared join keys
- Generate linksets only for pairs with actual overlap
- Skip pairs without shared identifiers

## SPARQL Query Examples

### Example 1: Find Linked Entities

Find all NDE datasets linked to MONDO diseases:

```sparql
PREFIX wobd-bridge: <https://wobd.org/bridge#>
PREFIX schema: <http://schema.org/>

SELECT ?nde_dataset ?mondo_disease ?mondo_id
WHERE {
    # Query NDE graph
    SERVICE <https://frink.apps.renci.org/nde/sparql> {
        ?nde_dataset a schema:Dataset .
        ?nde_dataset schema:healthCondition ?mondo_id .
    }
    
    # Use bridge to find matching MONDO entity
    ?link wobd-bridge:sourceNode ?nde_dataset ;
          wobd-bridge:targetNode ?mondo_disease ;
          wobd-bridge:joinKeyValue ?mondo_id ;
          wobd-bridge:joinKeyType wobd-bridge:MONDO_ID .
    
    # Query MONDO graph
    SERVICE <https://ubergraph.apps.renci.org/sparql> {
        ?mondo_disease rdfs:label ?label .
        FILTER (STRSTARTS(STR(?mondo_disease), "http://purl.obolibrary.org/obo/MONDO_"))
    }
}
```

### Example 2: Count Links by Join Key Type

Count how many links exist for each join key type:

```sparql
PREFIX wobd-bridge: <https://wobd.org/bridge#>

SELECT ?join_key_type (COUNT(*) as ?link_count)
WHERE {
    ?link a wobd-bridge:LinkAssertion .
    ?link wobd-bridge:joinKeyType ?join_key_type .
}
GROUP BY ?join_key_type
ORDER BY DESC(?link_count)
```

### Example 3: Find High-Confidence Links

Find links with confidence >= 0.9:

```sparql
PREFIX wobd-bridge: <https://wobd.org/bridge#>

SELECT ?source ?target ?join_key_value ?confidence
WHERE {
    ?link wobd-bridge:sourceNode ?source ;
          wobd-bridge:targetNode ?target ;
          wobd-bridge:joinKeyValue ?join_key_value ;
          wobd-bridge:confidence ?confidence .
    FILTER (?confidence >= 0.9)
}
LIMIT 100
```

## Extending Join Key Vocabulary

To add support for new identifier types:

1. **Add to RDF schema** (`src/omnigraph_agent/bridge/wobd_bridge_schema.ttl`):
   ```turtle
   wobd-bridge:NEW_ID a wobd-bridge:JoinKeyType, skos:Concept ;
       skos:inScheme wobd-bridge:JoinKeyScheme ;
       skos:prefLabel "New Identifier Type" .
   ```

2. **Add to mapping** (`src/omnigraph_agent/bridge/linkset_builder.py`):
   ```python
   JOIN_KEY_MAPPING = {
       ...
       'NEW': WOBDBRIDGE.NEW_ID,
   }
   ```

3. **Add pattern extraction** (`src/omnigraph_agent/context_builder/graphs/base.py`):
   ```python
   patterns = [
       ...
       (r'^(NEW)(\d+)$', 'NEW', r'^NEW\d+$'),
   ]
   ```

## Performance Considerations

### Large-Scale Generation

When generating linksets for many graph pairs:

1. **Use batch generation**: More efficient than individual pairs
2. **Monitor query limits**: Some endpoints may have rate limits
3. **Cache results**: Linksets don't change unless source graphs change
4. **Incremental updates**: Only regenerate linksets when needed

### Query Performance

- Bridge graphs are designed to be small (only link metadata)
- Use SERVICE clauses for federated queries
- Consider materializing frequently-used linksets

## File Structure

```
dist/
├── context/
│   ├── nde_global.json          (with identifier_info)
│   ├── mondo_global.json        (with identifier_info)
│   └── bridge/
│       ├── index.json           (global bridge index)
│       └── nde__mondo.json      (bridge context)
│
└── bridge/
    └── linksets/
        ├── nde__mondo-gse.ttl   (GSE linkset)
        └── nde__mondo-mondo.ttl (MONDO linkset)
```

## Troubleshooting

### No Shared Join Keys Found

- Ensure context files include `identifier_info`
- Check that both graphs have identifier patterns
- Verify identifier patterns are correctly extracted

### Linkset Generation Fails

- Check SPARQL endpoint accessibility
- Verify context files are valid JSON
- Check for query timeout issues

### Low Link Counts

- Verify identifier normalization is working
- Check that identifier patterns match between graphs
- Ensure entity type filters are appropriate

## References

- [VOID Vocabulary](http://vocab.deri.ie/void)
- [PROV Ontology](https://www.w3.org/TR/prov-o/)
- [FRINK Registry](https://frink.renci.org/registry/)
