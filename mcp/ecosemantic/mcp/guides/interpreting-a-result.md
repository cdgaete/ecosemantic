# Interpreting a result through contribution and inventory

A score is one number; reading it means saying where it comes from. Decompose it three ways and read the inventory under it before stating a conclusion.

## Checklist

1. `calculate_impact` gives the score under a method (`method_id` from `search_methods`) or a whole family (`impact_method` from `list_vocabulary`).
2. `contribution_analysis` with `by="process"` ranks the processes whose own exchanges carry the score; `top_n` bounds the list.
3. `contribution_analysis` with `by="path"` follows the supply chain from the functional unit; `max_level`, `max_nodes` and `cutoff` bound the tree. A credit is a child with a negative score.
4. `contribution_analysis` with `by="flow"` ranks the elementary flows behind the score.
5. `calculate_inventory` pages every elementary flow of the system, filtered by `compartment` or `query`. Amounts at or below the answer's `floor` are float64 residue, set aside and counted in `dropped`.
6. State each claim with the decomposition that shows it: a share is a process's or a flow's score over the total, under the method named.

## Worked example: a bottle on the fixture database

A bottle takes 0.4 kg of glass and 0.05 t·km of lorry transport, and its own process emits 0.02 kg of fossil carbon dioxide.

```json
{"tool": "search_processes", "arguments": {"database": "fixture", "query": "glass"}}
```

```json
{"tool": "search_processes", "arguments": {"database": "fixture", "query": "lorry"}}
```

```json
{"tool": "search_elementary_flows", "arguments": {"database": "fixture", "query": "carbon dioxide"}}
```

```json
{"tool": "search_methods", "arguments": {"database": "fixture", "query": "climate change"}}
```

```json
{"tool": "create_product_system", "arguments": {"name": "bottle", "database": "fixture"}}
```

```json
{"tool": "create_process", "arguments": {"product_system_id": "{system}", "code": "bottle", "name": "bottle making", "unit": "unit", "reference_product": "bottle"}}
```

```json
{"tool": "update_product_system", "arguments": {"product_system_id": "{system}", "reference_process": "bottle"}}
```

```json
{"tool": "create_exchange", "arguments": {"product_system_id": "{system}", "code": "bottle", "type": "product", "amount": 0.4, "input": "{hit:glass}"}}
```

```json
{"tool": "create_exchange", "arguments": {"product_system_id": "{system}", "code": "bottle", "type": "product", "amount": 0.05, "input": "{hit:lorry}"}}
```

```json
{"tool": "create_exchange", "arguments": {"product_system_id": "{system}", "code": "bottle", "type": "elementary", "amount": 0.02, "input": "{hit:carbon dioxide}"}}
```

```json
{"tool": "calculate_impact", "arguments": {"product_system_id": "{system}", "method_id": "{method:climate change}"}, "expect": {"path": "value.scores.0.value", "equals": 0.945}}
```

```json
{"tool": "contribution_analysis", "arguments": {"product_system_id": "{system}", "by": "process", "method_id": "{method:climate change}", "top_n": 5}, "expect": {"path": "value.processes.0.fraction", "equals": 0.6349206349206349}}
```

```json
{"tool": "contribution_analysis", "arguments": {"product_system_id": "{system}", "by": "path", "method_id": "{method:climate change}", "max_level": 3}, "expect": {"path": "value.root.score", "equals": 0.945}}
```

```json
{"tool": "contribution_analysis", "arguments": {"product_system_id": "{system}", "by": "flow", "method_id": "{method:climate change}"}, "expect": {"path": "value.flows.0.fraction", "equals": 1.0}}
```

```json
{"tool": "calculate_inventory", "arguments": {"product_system_id": "{system}", "compartment": "air"}}
```

The bottle scores 0.945 kg CO2-Eq. By process, the glass's electricity carries 0.6 of it, 63.5 %; the glass furnace's own carbon dioxide 0.32, the bottle's own 0.02 and the lorry's 0.005. The path tree's root is the same 0.945, and by flow fossil carbon dioxide carries all of it, since the fixture's glass, lorry and electricity emit no methane. `{system}` stands for the id `create_product_system` answered, `{hit:…}` for the `ref` of the first hit of the search for that term, and `{method:climate change}` for the id of the first method that search found.
