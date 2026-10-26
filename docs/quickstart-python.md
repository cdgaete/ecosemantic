# Quickstart: Python

`import ecosemantic as es` opens a workspace: the same tools a chatbot calls, as methods under the same names, over the same directories. Every write lands in the product system's change log under your name, and a page served over the same directories draws it as it lands.

```python
import ecosemantic as es

with es.open() as ws:
    db = ws.database("ecoinvent-3.12-cutoff")
    steel = db.search_processes("market for steel, low-alloyed", location="GLO").items[0]
    gwp = next(
        method
        for method in db.search_methods("IPCC 2021 climate change fossil").items
        if method.impact_method == "IPCC 2021"
        and method.impact_category == "climate change: fossil"
    )

    frame = ws.create_product_system("bicycle frame", database=db)
    tube = frame.create_process(
        "tube", "frame tube drawing", unit="kilogram", reference_product="frame tube"
    )
    frame.update_product_system(reference_process="tube")
    frame.set_parameters(parameters=[es.Parameter(name="scrap_rate", value=0.08)])
    tube.create_exchange(type="product", formula="1 + scrap_rate", input=steel)

    assert frame.validate_product_system().value.is_valid
    score = frame.calculate_impact(method_id=gwp.id).value.scores[0]
    print(score.value, score.unit)

    for hotspot in frame.contribution_analysis(
        by="process", method_id=gwp.id, top_n=5
    ).value.processes:
        print(f"{hotspot.fraction:6.1%}  {hotspot.name} [{hotspot.location}]")
```

- `es.open()` takes the data and systems directories your platform's EcoSemantic folder holds, the same the server takes; `es.open(data_dir=..., systems_dir=...)` names others.
- A search ranks its hits; read a hit's fields, as the method's `impact_method` and `impact_category` here, before taking it.
- A search hit, a process handle or a product system handle goes wherever a tool takes a ref.
- Each method answers what its tool answers, as typed objects: `.value` holds the result, and a write's answer also holds its log `entry` and the `consequences` it left.
- A refusal raises the typed error the tool names, from `ecosemantic.errors`.
- Waste sent to a treatment is a negative input of the treatment, whose production is negative; a negative input of a provider whose production is positive is a credit. Emissions and resources are `type="elementary"` exchanges on a flow from `db.search_elementary_flows`.

`help(es.Workspace)` lists the methods; the tools' descriptions, which an agent reads, describe each argument.
