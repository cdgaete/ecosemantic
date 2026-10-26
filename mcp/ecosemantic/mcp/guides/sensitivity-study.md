# A sensitivity study through parameters, cases and scenarios

A sensitivity study asks how a result moves when a choice moves. Put each choice where it acts, as a parameter, and compare variants in one call, so they share one seed and one method.

## Checklist

1. `set_parameters` holds the choices: a literal value for each lever, a formula for each quantity that follows from them.
2. A formula on the exchange where the choice acts. An alternative supplier is an ordinary process whose amount a share parameter sets: `demand * (1 - share)` from one, `demand * share` from the other.
3. A case, in `set_parameters`' `cases`, sets literal parameters to other values. It is part of the model and never goes stale.
4. A scenario, `create_scenario`, overrides parameters or exchanges — an amount, a multiplier, or a product input's provider — pinned to the system's hash. After any later edit, `rebase_scenario` before naming it. A case and a scenario never share a name.
5. `calculate_impact` with `variants` scores the base and each named case or scenario, with each variant's delta from the base.
6. `calculate_impact` with `monte_carlo` adds the uncertainty: the median, its 95 % interval and the 2.5th and 97.5th percentiles, and each variant's delta as the median of paired differences. Up to 200 draws answer inline; `start_monte_carlo` runs more as a background run that `get_run` follows.

## Worked example: a tray on the fixture database

A tray weighs 1 kg, of aluminium and of polyethylene by a share parameter. A case moves the share; a scenario halves the tray's mass.

```json
{"tool": "search_processes", "arguments": {"database": "fixture", "query": "aluminium"}}
```

```json
{"tool": "search_processes", "arguments": {"database": "fixture", "query": "polyethylene"}}
```

```json
{"tool": "search_methods", "arguments": {"database": "fixture", "query": "climate change"}}
```

```json
{"tool": "create_product_system", "arguments": {"name": "tray", "database": "fixture"}}
```

```json
{"tool": "create_process", "arguments": {"product_system_id": "{system}", "code": "tray", "name": "tray forming", "unit": "unit", "reference_product": "tray"}}
```

```json
{"tool": "update_product_system", "arguments": {"product_system_id": "{system}", "reference_process": "tray"}}
```

```json
{"tool": "set_parameters", "arguments": {"product_system_id": "{system}", "parameters": [{"name": "tray_mass", "value": 1.0, "unit": "kilogram"}, {"name": "plastic_share", "value": 0.0}], "cases": [{"name": "plastic tray", "values": {"plastic_share": 1.0}}]}}
```

```json
{"tool": "create_exchange", "arguments": {"product_system_id": "{system}", "code": "tray", "type": "product", "formula": "tray_mass * (1 - plastic_share)", "input": "{hit:aluminium}"}}
```

```json
{"tool": "create_exchange", "arguments": {"product_system_id": "{system}", "code": "tray", "type": "product", "formula": "tray_mass * plastic_share", "input": "{hit:polyethylene}"}}
```

```json
{"tool": "create_scenario", "arguments": {"product_system_id": "{system}", "name": "light tray", "overrides": [{"kind": "parameter", "name": "tray_mass", "value": 0.5}]}}
```

```json
{"tool": "calculate_impact", "arguments": {"product_system_id": "{system}", "method_id": "{method:climate change}", "variants": ["plastic tray", "light tray"]}, "expect": {"path": "value.variants.0.deltas.0", "equals": -11.5}}
```

```json
{"tool": "calculate_impact", "arguments": {"product_system_id": "{system}", "method_id": "{method:climate change}", "variants": ["plastic tray"], "monte_carlo": {"n": 50, "seed": 7}}, "expect": {"path": "value.scores.0.value", "equals": 16.5}}
```

The aluminium tray scores 16.5 kg CO2-Eq: 15 kWh of electricity and 1.5 kg of carbon dioxide a kilogram of aluminium. The plastic tray's delta is −11.5, polyethylene's 5 against aluminium's 16.5, and the light tray's −8.25, half the mass. Under Monte Carlo the base keeps its 16.5 as the score, with the samples' median and intervals beside it. `{system}` stands for the id `create_product_system` answered, `{hit:…}` for the `ref` of the first hit of the search for that term, and `{method:climate change}` for the id of the first method that search found.
