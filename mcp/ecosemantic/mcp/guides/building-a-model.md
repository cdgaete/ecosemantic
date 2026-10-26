# Building a model through the tools

A product system is a graph of foreground processes over one background database. Build it in the order below. Every write answers with its log entry and the consequences it left, and `validate_product_system` says what is still missing.

## Checklist

1. `list_databases` names the databases; choose one. Its `elementary_flows` names the database the flow refs carry.
2. `search_processes`, `search_elementary_flows` and `search_methods` find each input, each emission or resource, and the method. Pass on the `ref` a hit carries, verbatim, as a JSON object, never as a string holding JSON. `location` is matched as an exact code; `list_vocabulary` gives the spellings a filter takes.
3. `create_product_system` on that database.
4. `create_process` for each foreground process, down to the tier where a choice is made: a fuel, a supplier, a recipe. Each writes its production exchange.
5. `update_product_system` with `reference_process`: the process whose product, one unit of it, is the functional unit.
6. `set_parameters` before any formula names a parameter.
7. `create_exchange` for each input, emission and resource, with an amount or a formula. A negative input of a waste treatment, whose production is negative, sends waste to it; a negative input of a provider whose production is positive is a credit. An alternative supplier is an ordinary process whose amount a parameter sets.
8. `validate_product_system` until it reports valid, then calculate.

## Worked example: a widget on the fixture database

The fixture database is the synthetic background the package's tests install. A widget takes a frame, which takes 2.4 kg of steel; the frame's mass is a parameter.

```json
{"tool": "search_processes", "arguments": {"database": "fixture", "query": "steel"}}
```

```json
{"tool": "search_methods", "arguments": {"database": "fixture", "query": "climate change"}}
```

```json
{"tool": "create_product_system", "arguments": {"name": "widget", "database": "fixture"}}
```

```json
{"tool": "create_process", "arguments": {"product_system_id": "{system}", "code": "widget", "name": "widget assembly", "unit": "unit", "reference_product": "widget"}}
```

```json
{"tool": "create_process", "arguments": {"product_system_id": "{system}", "code": "frame", "name": "frame production", "unit": "kilogram", "reference_product": "frame"}}
```

```json
{"tool": "update_product_system", "arguments": {"product_system_id": "{system}", "reference_process": "widget"}}
```

```json
{"tool": "set_parameters", "arguments": {"product_system_id": "{system}", "parameters": [{"name": "frame_mass", "value": 0.25, "unit": "kilogram"}]}}
```

```json
{"tool": "create_exchange", "arguments": {"product_system_id": "{system}", "code": "widget", "type": "product", "formula": "frame_mass", "input": {"kind": "foreground", "code": "frame"}}}
```

```json
{"tool": "create_exchange", "arguments": {"product_system_id": "{system}", "code": "frame", "type": "product", "amount": 2.4, "input": "{hit:steel}"}}
```

```json
{"tool": "validate_product_system", "arguments": {"product_system_id": "{system}"}}
```

```json
{"tool": "calculate_impact", "arguments": {"product_system_id": "{system}", "method_id": "{method:climate change}"}, "expect": {"path": "value.scores.0.value", "equals": 1.668}}
```

The widget scores 1.668 kg CO2-Eq: its 0.25 kg of frame takes 0.6 kg of steel, at 2.78 kg CO2-Eq a kilogram. `{system}` stands for the id `create_product_system` answered, `{hit:steel}` for the `ref` of the first hit of the search for steel, and `{method:climate change}` for the id of the first method that search found.
