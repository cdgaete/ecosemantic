# Changelog

Each release names what it adds, changes and removes, newest first.

## 0.1.24

- Opening a product system shows its General information beside the graph. Select the system name to return to General information, or a pinned process chip to open that process.
- The inspector can be maximised. Results open on the right, and input and output rows expand in place. Selecting a process opens its details; selecting the canvas dismisses the inspector.
- Automatic graph placement bounds its search and routes connectors clear of graph text. With `only_if_better`, `arrange_graph` saves a release of selected cards or agent holds only if the resulting drawing scores lower; otherwise the stored drawing stands.

- The page's graph and inspector name what each action changes. A card's menu leaves out the destination already shown and reads *Show process activity* and *Center card*, with a pointer at its card; choosing the card already inspected keeps its page. The inspector reads *Not provided* for a missing value, one sentence for an empty section and *Loading…* for a value on its way; *Pin process for quick access* and *Pinned*, which unpins; a process's tabs under its title; and, below 768 px, *Back to graph* and a shorter sheet behind *Show more graph*. A supplier followed from *Inputs/Outputs* offers *Back to* the process it came from, at the exchange followed. The calculation controls read *Open result*, *Run again* and *New calculation…*, and below 768 px the build line holds *Open result* and a labelled menu. The `own` badge stands clear of the selection outline, and `⋯` stays on the canvas toolbar's first row.
- `graph_layout` and `arrange_graph` take `detail`: `full` answers the arrangement with its text map, and `drawing` the same arrangement with `map` null. Every arrangement carries `kind`, each trouble names the `exchange_ids` of its arrows, and a map over the cell limit is refused naming `detail="drawing"`.
- `graph_layout` takes `detail="amounts"`: without `card` it answers every card's activity, and with `card` that card's rows of scaled amounts, each exchange's id, name, amount and unit, in pages of 30 and 15 with their totals and a `next_cursor`, without placing, routing or scoring a card; `card` and `cursor` are refused under `drawing` and `full`.
- `graph_layout` answers a compact read by default: the score, the bounds, the scaling, how many troubles of each kind and how many cards each placer holds, the card rows and the issues heaviest first, in pages of 10 cards and 3 issues with their totals and a `next_cursor`; `card` or `exchange_id` focuses on that card or arrow, with 5 routes and 3 issues a page, and `detail="full"` answers the arrangement with its map.
- **Breaking:** `graph_layout` and `arrange_graph` both answer compact replies by default, and `detail="full"` answers the `Arrangement` with its map. A compact write answers whether it saved, the variant, the score before and after, where 0 means nothing is wrong, how many troubles of each kind the drawing now carries, the cards whose place, hold or placer differs from the drawing before, each with its x, y, held and placed_by on both sides and the cards the call named first, and the issues the call added and resolved, each with its kind, cards and exchange ids, heaviest first, in one page of 6 changed cards, 2 added and 2 resolved with their totals; where a view is served it carries the product system's page link, and `release_all`, which reads no stored layout, answers null for the score before, the changed cards and the two differences.
- The server's instructions, the `graph_layout` and `arrange_graph` descriptions and the guides on building a model and on interpreting a result say to arrange the drawing last, once the model and its results are settled, and in a subagent or a separate session when the client has one, bringing back only the score, the troubles left and the page link; `graph_layout` stays the read for scaled amounts when a check needs them.
- A drag the store refuses puts the card back where the layout holds it and the canvas toolbar shows the refusal's message, so a move the store did not keep never looks saved.
- A placement records who put it there: `Spot`, `Placement` and the page's types carry `placed_by`, `person` for a card dragged on the page whatever is signed in and `agent` for a call over MCP, the Python API placing as its workspace's actor. A stored layout without it reads as `None`, and a card placed again at the coordinates it already holds keeps the placer it recorded, so an agent sending every card again takes none of a person's holds.
- The arrangement, its routes, troubles and map are drawn off the event loop, so a drawing that takes a second leaves every other tool call and page request of the process free to run.
- `arrange_graph` holds its product system's lock across the read and the write, so two moves made at once keep both, and `put_layout` refuses a layout computed from a read the store has moved past with a `conflict` saying to read it again. A stored layout this version cannot read answers `unavailable` naming no path, with `arrange_graph` and `release_all` as its remedy: that call reads no stored layout and writes the layout again.
- `arrange_graph` refuses a placement that names a card the drawing lacks, a code named twice, a release that names nothing drawn or held, coordinates that are not finite or lie beyond ±100,000, and a drawing over 500,000 cells; nothing a refused call computed is saved, and a layout the store holds already is not written again.
- `TELEMETRY.md` states how long a count is kept as an upper bound alone, at most 731 days and 1 hour, since the collector's operator may delete counts sooner.

## 0.1.23

- **Security.** Versions 0.1.22 and earlier let a caller reach files on the engine's computer, and each way is closed:
  - A call through the bridge or across the network named any path. It is refused `export_product_system`, `import_product_system`, `export_tables`, `import_tables` and `install_database` with a `package`, over MCP and on the page's install route, and the refusal is recorded. A call on the engine's computer names paths as it did, and a page elsewhere still downloads, returns and uploads.
  - A request that a proxy or a tunnel on the engine's computer forwarded counted as made on that computer. Where it says that it forwards, the request is one from across the network, which names no path and enters or reads no account: a loopback peer's request that carries `Forwarded`, `Via`, `X-Real-IP`, `X-Client-IP`, `True-Client-IP`, `X-Original-Forwarded-For` or one starting `X-Forwarded-`, `CF-` or `Tailscale-`. A proxy or port forward that adds none of these still counts as that computer (`SECURITY.md`).
  - `export_product_system` and `export_tables` declared themselves read-only and write over files. Each declares that it writes and may destroy, so a client that runs read-only tools unasked asks first, and the activity records each as a write.
  - The page's *Run again* ran a recorded export again at the path whoever recorded it chose. It runs again no call that names a path.
  - A content hash given to `get_parameters`, to the page's parameters route or as a link's `at_hash` was joined into a file path, so it read a product system's version from outside its store. A text that is no content hash names no version and is `not_found`.
  - An id from an installed openLCA zip was joined into a file path, so a write of a product system naming it landed outside the package. Such an id is refused as `invalid` before the package is touched.
  - `BRIDGE_EXTENSION` and `reach` are in `ecosemantic.mcp.reach`, and `refuse_remote_path` in `ecosemantic.mcp.host` is the rule of a path.
- Telemetry can send this computer's country, and only after a yes typed at a terminal: `ecosemantic init` and `ecosemantic telemetry on` ask, showing the two letters. It is the time zone's country, or the region setting's on Windows, never read from an address, and none is sent where none is found. `ecosemantic telemetry off` withdraws the yes, `ecosemantic telemetry` and `doctor` show the country and whether it is sent, and the first-start notice is shown once more to an install that was told before the country existed. The counts are described as pseudonymous, since their install identifier stays the same.
- One process serves several signed-in people. `build_server` and `build_view` take a `Callers`, which answers the context of each request's caller from the request's ASGI scope and follows the stores it serves while the view runs. A `ServerContext` is the `Callers` of a server with one caller, so `build_server(context)` and `build_view(context, server)` work as they do. A host keeps one context for each store and answers `for_person(person)` of it. A caller the host does not know, and a host's context that names no person, are refused on every tool, handshake and route.
- An MCP session answers the credential that opened it. A host that serves people over MCP sets `scope["user"]` to the MCP SDK's `AuthenticatedUser`, whose token's subject is the person's id, and a person's handshake or tool call without it is refused. The host mounts the endpoint stateful, FastMCP's default, and passes no `graph`, which is one port for every caller.
- A write names the signed-in person. An agent's actor carries `on_behalf_of`, the page's write names the person whatever the browser sends, a recorded call carries `person`, and the trail of a log entry follows one agent for one person. A record without a person has the shape it had. An engine at 0.1.22 or earlier reads a log that holds `on_behalf_of` and drops the field from the whole log when it next writes it.
- A signed-in person does not reach the host's machine: `export_product_system`, `import_product_system`, `export_tables`, `import_tables`, `install_database` and `cancel_install` are refused, as are the openLCA upload and the account routes. The page's downloads and returns serve them.
- An agent named `view` is refused over MCP on every server, the local one included, and every call over MCP is counted. The name is the page's.
- `ecosemantic.events.following` follows one store's writes, runs and installs for as long as it is entered. A store that cannot be followed stops the view's start with its error.
- The helpers under the builders change shape: each tool module's `register` takes the server alone, `bound` and `serialised` take the function alone, `InProgress` carries the context and the origin, `recorded` takes no context, `Introducing` and `Recorder` take a `Callers`, and `uploaded` answers the text a form states in place of an actor. The server's own `instructions` carry no page link, which each caller reads at the handshake.
- `contribution_analysis` takes `by="stage"`, which splits a score over the life-cycle stages the processes' `life_cycle_stage` metadata names, in the order a walk from the functional unit meets them, processes of no stage last. A stage holds each of its processes' own part, its direct emissions and each input's cumulative score, a linked system counts to the stage of the process that takes it, and the stages sum to the total or the call is refused. A split is written as a table too.
- `contribution_analysis` and `calculate_inventory` take `variant`, which names a case or a scenario to decompose or to list in place of the base, and a decomposition's link opens its own page under that variant.
- The arrangement gives each life-cycle stage a band of columns of its own, the functional unit's at the right. `graph_layout` answers each stage's regions and names a supplier of no stage that several stages share, and its map marks them. A system without stages is arranged as before.
- The page shows a band on the canvas with the latest calculation, scored on the current model: its method, its category and its cases. The canvas and an open result hold one case, which the address sets. Each card shows its own part of the band's result.
- The page draws each stage as a box in its colour with its share of the band's result, colours the Sankey's bands by stage, shows a result split by stage on a page of its own and groups the navigation pane by the stages. An open result docks under the graph with its tabs at the top.
- pydantic 2.12 or later is required.

## 0.1.22

- Every database is read into one canonical shape when it is installed, and a database installed by an earlier version is refused, naming the reinstall, so each installed database is installed again after this update. A method names its family, its category and its indicator. An elementary flow sits in one compartment of a closed vocabulary (air, water, soil, immaterial, natural resource, economic, inventory indicator) with one sub-compartment. A CAS number is a valid number or none, other text kept as `cas_as_published`. Every location a process names is held under the name its release gives it, a process its publisher located nowhere at `UNSTATED`, and each exchange carries its supplier's location beside its name. A bundle that does not fit is refused, naming each misfit and how many rows carry it.
- Each release is built as EcoSemantic's revision of it, with its recorded corrections applied and carried in the bundle's manifest, and a database names its revision beside its version.
- A method family's normalisation and weighting sets are read into the catalog, and an impact answers one total for each weighting set of the family, normalised and weighted as openLCA applies a set, with the notice that a weighted total rests on value choices; a variant's total carries its delta from the base. The page shows the totals under the categories.
- A parameter with a literal value takes a distribution centred on it. Each Monte Carlo draw draws every uncertain parameter, of the system and of each system it links, and evaluates the formulas that read it, the base and the variants on one draw's numbers. A distribution is refused unless it is centred on its parameter's value or its exchange's amount, and an exchange whose formula reads an uncertain parameter is refused a distribution of its own. The tables and the openLCA package carry a parameter's distribution.
- A lognormal and a normal take an optional `minimum` and `maximum`, kept by drawing again outside them; a run that cannot draw within them is refused, naming the exchange, the parameter or the background activity.
- A Monte Carlo's stop rule counts a category whose draws are equal as met and leaves out one whose median is indistinguishable from zero, naming both and the category that held the run longest, and an adaptive run takes an `n_min` of at least 6. A run states, for parameters, foreground exchanges and background exchanges, how many there are, how many carry a distribution and how many it drew.
- An exchange takes its amount beside its formula when the formula evaluates to it, so an exchange as a read answers it is written back unchanged.
- A scenario's swapped supplier is resolved as an exchange's supplier is, one in another unit is refused, and the exchange is named after it when the scenario applies.
- `calculate_inventory` takes `side`, which pages the inputs and the outputs apart, and `order`, by `compartment` or by falling `amount`.
- A share of a total of 0 is answered as none, and the page draws it as a dash.
- A return from openLCA or from the tables that changes nothing writes no log entry and says so, and `import_tables` refuses a folder that changes nothing.
- A listing counts its rows, keeps name order under a filter and answers the page that holds an item. In the page's explorer each column scrolls on its own, the open item's row is marked on the page that holds it, a filter says how many rows it keeps, tables page forward and back, and an opened item opens the tree at its place. The section bar carries a search field that reads the datasets, the elementary flows or the impact methods of the whole database. The navigation folds and counts each database, and the palette reaches every database.
- The explorer, an open result and a simulation each open in a sheet over the graph, which stays drawn behind it at the view it had. A button on the name island, a close button, `Esc` and a click outside the sheet leave it for the address it was opened from.
- A background input on a card, or a provider on a process's Inputs/Outputs page, opens its dataset beside the graph, with its suppliers opening there too and a link to it in the explorer.
- The inspector takes the width its left edge is dragged to, between 320 px and four fifths of the window, and leaves a button that shows it again while it is closed. The build timeline folds to its header. The canvas toolbar docks at the top centre beside the system's name, and its grip moves it anywhere over the graph. A card's menu stands on the chosen process.
- The calculation form takes a method and, under it, all its categories or one, and opens on the method and the category of the latest calculation. *Calculate again*, beside *Calculate* on the canvas, runs the latest calculation again on the current model in one click.
- The pages beside the canvas read the system under the state the canvas shows and name it. The impact table names its columns, results open on the category last chosen, the Monte Carlo fields say what they do, and the inventory names its dominant process. Every download is named by the server after its system and its content. An agent's trail lists its writes and folds the reads between them into one counted line.
- The page's calls run the registered tools in the server's own process, the home page reads its rows in one request and a process's elementary flows in one, a listing's filter sends its request once typing pauses for 300 ms, and the event stream refetches each key once a frame.

## 0.1.21

- The page explores a database: it opens one and browses its processes by classification, its elementary flows by compartment and sub-compartment, its impact methods with each indicator's characterization factors, its units and its locations. The navigation lists each database's sections, and the search and dataset pages are part of the explorer. The view serves it through eight routes under `/api/databases/{name}/`, which read the inventory and search ports of the request's context and nothing else, so a context that serves a caller only its own databases limits what the explorer shows.
- The inventory port reads a database's counts, its classification schemes and their values, the flows each sub-compartment holds and an indicator's characterization factors, and the search port browses processes by classification and flows by compartment, each with an optional filter.
- A classification tree names the ISIC Rev.4 divisions and groups a database leaves unnamed from the structure the United Nations Statistics Division publishes, which `ecosemantic-core` carries unchanged in `ecosemantic/ports/data/isic_rev4_english_structure.csv`; each distribution's `NOTICE` names its source and `PROVENANCE.md` records its hash.
- The page has two themes, Light, which it opens in, and Dark, both drawn in the system's fonts, and the top bar carries a button that turns Dark on and off. A theme a browser kept under the names Cobalt, EcoSemantic or openLCA opens in Light, Dark and Light. The page carries no fonts, so its third-party notices list none.
- The graph takes the window under floating islands: the dock, the system's name, the inspector and the navigation sheet, with the toolbar, the zoom and the minimap floating beside them, and the build running along the bottom; below 768 px the graph takes the screen. Fit the graph shows the whole drawing clear of every island. A selected card is marked by a dashed outline beside its change ring and carries a toolbar of what can be done with it, and the legend states the three marks. Esc closes the inspector sheet and the canvas tools.
- `calculate_impact` answers the demand it scored in `demand`: the one given, or a unit of the reference process. Its summary carries it, and the page names each result's target from it. `DemandItem` is defined in `ecosemantic.model.refs`, and `ecosemantic.DemandItem` names it.
- `contribution_analysis` by process and by flow answers in `cut` the signed totals of the scores the list leaves out, `below_score` and `unlisted_score`, so the rows listed plus both make the total; the page's Process results ends with its rest and total rows.
- `ecosemantic compute` takes `--variants NAME` once for each scenario or case, and a result's address carries each variant as a `variants` parameter of its own, so a variant whose name holds a comma is scored under its whole name.
- The page words each request kind and its effect, names systems of one name apart by a short id, and shows a call's arguments in the timeline without JSON; the timeline's entry for `arrange_graph` names the cards a person placed, and the accounts screen leads back to the page.

## 0.1.20

- An impact answer names each method once, in `methods`, and each score, each variant's score and each Monte Carlo category names its method by `method_id`, as `gating_method` does; a contribution answer names its method in `method`, and its `total` names it by `method_id`. A score carried its method's whole record, which a family of 25 categories with two variants answered 75 times. The page, the in-chat panel and a result folder read a method from the answer that lists it, and a run stored by an earlier release reads as it did.
- `calculate_impact` and `get_run` answer each Monte Carlo category with its summary and a histogram of twenty bins, and take `samples` to answer every draw in the histogram's place, as the Python API's two methods do, where an answer carried every draw of every category. The page asks for the draws and draws its histograms from them.
- The in-chat panel of `calculate_impact` writes each category's figures under a Monte Carlo, with the 95 % interval of the median, and draws its bars from the histogram, where it read an interval of the mean no answer carries and drew nothing.
- An ecoinvent build carries each dataset's comment and classifications from the release's files: the general comment with the included activities, the geography, the technology and the time period, and the classifications of the activity and of its reference product. `get_background_process` answers them for a database installed from such a build, where every ecoinvent dataset answered neither. A build keeps its fingerprint, so a database installed again serves the product systems it served.
- A lognormal's `loc` and `scale` read back as they were written, where a `scale` of 0.1823 came back as 0.18230000000000007 after the next write.
- `get_parameters` and `set_parameters` answer a product system's parameters in the order they were written, where the order changed from one call to the next.
- `install_database` refuses a draft its source cannot take, and a `version` or a `system_model` its source does not offer, naming the ones it offers, before it asks for the account the source needs.
- A tool's `limit` declares its minimum of 1 in the tool's schema, and a scenario's exchange override declares a `background` or a `foreground` input alone, where the schema listed the `system` and `elementary_flow` inputs the tool refuses.
- `arrange_graph` leaves the reference card where its column put it when its middle height would cover a card held there, where it drew the reference over the held card.
- Reading a product system or cancelling a run the store does not hold leaves no lock file, deleting a product system or its runs removes their lock files, and a server removes at its start the lock files of the systems, runs and installs it does not hold, where each left a `.lock` file in the data directory.
- A refused string argument is quoted in the refusal, cut to 60 characters; a database the store lacks is named without the data directory's path; and a one-word query that matches nothing is told to try another word, or the start of one followed by `*`.

## 0.1.18

- `list_runs` answers each run without its result, which `get_run` answers, where a listing carried every sample of every run.
- A row of `contribution_analysis` by flow carries its `sub_compartment`, on the page and in a contribution run's `contributions.csv` as well, so two flows of one name and compartment read apart.
- `search_elementary_flows` finds a flow by its CAS number whether the number's first group is written bare or padded with zeros to six digits, as ecoinvent writes it: `124-38-9` and `000124-38-9` find the same flows.
- A search that finds nothing under a filter value the database's vocabulary lacks says so and names the vocabulary that lists the values the filter takes: a `location` or a `unit` of `search_processes`, a `compartment` or a `sub_compartment` of `search_elementary_flows`, and a `compartment` of `calculate_inventory`.
- An `impact_method` no family carries is refused with the nearest families, or with the vocabulary that lists them when none reads alike; a `method_id` no method carries is refused naming `search_methods`, where it suggested the methods whose specification read most like the id.
- `export_tables` refuses the folder an earlier export of the system made unless `replace` is passed, where it wrote over a person's edits.
- `view_link` answers `not_found` for a product system the store does not hold, and `rebase_scenario` refuses a scenario that is at the base already, where it appended an empty entry to the log.
- A validator's refusal is said without pydantic's `Value error, ` in every tool's answer.
- The built page is answered with `Cache-Control: no-cache`, so a browser asks for it again after a build, and its assets stay cacheable.

## 0.1.17

- A formula takes numbers, parameter names, arithmetic, comparisons, a conditional and the math functions `abs`, `acos`, `asin`, `atan`, `atan2`, `ceil`, `cos`, `cosh`, `degrees`, `exp`, `floor`, `hypot`, `log`, `log10`, `log2`, `max`, `min`, `pow`, `radians`, `round`, `sin`, `sinh`, `sqrt`, `tan` and `tanh`, with `pi` and `e`; anything else is refused before it is evaluated, naming what the formula holds. A formula in a parameter, an exchange, a table folder or a model package so reads no file and looks inside no object, where one could call `open`, `loadtxt`, `fromfile` and `genfromtxt` and read a file of the computer the engine runs on. Every release before this one evaluates such a formula: update.
- `contribution_analysis` by process and by flow counts in `cut` every part its list leaves out: `below` and `share` over every part under the cut-off, and `unlisted` and `unlisted_share` for the parts that reach it past `top_n`, where `cut` counted within the `top_n` parts alone. The page says both under each list.
- `export_product_system` refuses a path that holds a file unless `replace` is passed, and a path that is a directory, where it wrote over the file; `ecosemantic export` writes over the file its command names.
- A write answers in its `consequences` the issues of the system's own links: a link behind its system, a link that resolves to nothing, and a link to a system on another database, which `rebase_database` onto another database leaves. A calculation refuses such a link as on another database, and `validate_product_system`'s `database_build` names the systems on the installed database alone, where both named the linked system as on another build of the wrong database.
- `create_product_system`, `update_product_system`, `create_process` and `update_process` refuse a blank name, and the two process tools a blank reference product.
- `import_product_system` answers `invalid` for a file that is no zip, and `import_tables` for a folder that holds no `model.yaml`, where each failed with the library's own error.

## 0.1.16

- The page opens in the Cobalt theme, drawn in Source Sans 3 and JetBrains Mono, which it carries under the OFL-1.1 and lists in its third-party notices; the `Theme` menu offers Cobalt beside the two others, and a browser that kept another theme moves to Cobalt once.
- A page opened at an address carrying its token opens its event stream with that token.
- `contribution_analysis` by process and by flow keeps the parts whose share reaches `cutoff` and answers `cut`: the cut-off, how many parts fell under it and their share of the total. The page says what a list leaves out, and a contribution run's folder records it.
- `graph_layout` and `arrange_graph` answer `card`, the geometry every card is drawn at, in place of a `row_height` on each card, and `list_sources` answers each source's `account`, its name and the phrase that names one. The page draws its cards, its arrows and a process's rows from those answers, and its simulation form starts from the defaults the engine samples at, which `/api/monte-carlo` serves.
- A process with two production exchanges is refused, in an edit and in a `model.yaml`, and a `model.yaml` that is no product system is refused as `invalid`, naming the file.
- Every tool that takes a `limit` refuses one below 1 as `invalid`.
- `ecosemantic compute --contributions` refuses an impact method family of several methods, as `contribution_analysis` does, and `ecosemantic setup` refuses a database that is already installed before anything is downloaded, unless `--replace` is passed.
- A product system's log, requests or layout that this version cannot read is answered as `unavailable` in one sentence naming the file, the line and the field it refuses, with the remedy, as the activity and a run's record are. Each of the three is written whole, so a reader sees one version or the other and a write that fails leaves the file as it was.
- Every writer lands a file through one bounded retry, so a file another program holds on Windows is answered as `unavailable`, naming it: the bridge's credential, a chat client's configuration, the tray's settings, a product system's package and a database's build among them.
- The tray reads its sign-in as `ecosemantic bridge status` does: an engine token is a sign-in, and a machine without a credential store starts the tray signed out, where it refused to start.
- A setup that needs an account and is given none says to run the command in a terminal to be asked for it, or names the variables that carry it. A download cache that cannot be written is `unavailable` for a BAFU install as for a USLCI one, a bridge that answers a registration out of shape is `invalid`, naming the field, and `/stop` and `/yield` answer 401 to a nonce that is not the one held, whatever value is sent.
- `ecosemantic-databases uslci validate --record` refuses to record a run that found mismatches, naming how many and the first.

## 0.1.15

- The accounts screen at `/accounts` enters an ecoinvent or Nexus account on the computer where the engine runs, and the tray's menu offers `Database accounts…`, which opens it there.
- Where the page reaches the engine through the bridge or across the network, its account fields are disabled with the steps that do enter an account; an account posted from off the engine's computer is refused with the same advice, and the agent reads it where an install needs an account. An engine with no database leads the agent to the sources a database installs from.
- `/health` answers one declared document, read in one place; the tray starts its engine on the port it polls, and a port another application holds is refused as that application's, with the remedy.
- The bridge's tunnel resets a stream whose application fails, before or after its answer started, and the failure is logged.
- A device sign-in polls on past a poll that fails until its code expires, then names the last failure; a page address the bridge answers is refused unless it is https or loopback, whichever way the engine starts.

## 0.1.14

- The sign-in through the browser asks Logto for consent beside `offline_access`, which Logto requires before it issues the refresh token the engine keeps, where it answered `Logto's grant names no refresh_token`.

## 0.1.13

- `ecosemantic-relay`, a seventh distribution, holds the bridge's tunnel: the messages and frames of its one WebSocket, the bridge's discovery document and the Ed25519 proof a bridged request carries.
- `ecosemantic serve --bridge` serves the engine over HTTP, signs it in to `https://bridge.ecosemantic.com` when the machine holds no credential for it, and serves the bridge's tunnel beside the page, announcing `https://<handle>.bridge.ecosemantic.com` as the page's address and writing the connector's address and the tunnel's lines on stderr.
- `ecosemantic bridge sign-in` signs an engine in through the browser or `--device`, `ecosemantic bridge sign-out` revokes the grant, and `ecosemantic bridge status` says whether the engine is signed in and where its credential is kept, renewing nothing.
- `ecosemantic bridge status` answers on a machine without a credential store, naming the two sign-ins that need none.
- `ecosemantic bridge sign-out` refuses while an engine token gives the engine its sign-in, and answers that nothing was revoked when this systems directory holds no credential.
- `ecosemantic doctor` reports a bridge setting it cannot use, in its view section, and exits 0.
- `EcoSemantic-Engine-Setup-<version>.exe` installs EcoSemantic Engine on Windows for one person, with no administrator rights: it asks for the two folders the engine uses and holds each to what Windows reads, makes them, starts the tray at every login and opens the bridge's sign-in on the first run. A later version installs over it and keeps the two folders and the person's choices, and an uninstall removes the program and the engine's own folder while leaving the two folders and the sign-in in place.
- `ecosemantic.tray` is the notification-area tray that runs the engine: its menu says what the engine and the bridge are doing and offers the page, the connector's address, the bridge's sign-in and sign-out, start at login, the logs and quitting; `--quit` answers 0 when nothing of the tray runs any more, 3 when something still does and 4 when its settings cannot be read.
- `python -m ecosemantic` runs the command, so a server or a chatbot starts it from a module path as well as from the `ecosemantic` script.
- `/health` carries a `bridge` object on a server serving the bridge — the tunnel's state, its handle, the page's address and the connector's — and `{"state": "off"}` on one that is not.
- `POST /stop` ends a server serving over HTTP whose systems directory proves the caller can write in it, as `/yield` does, with a nonce written there for one call.
- `scripts/payload.py` builds the standalone Python the Windows installer carries: the archive `installer/python.json` pins, checked against its SHA256, with the locked wheels and the core's seven installed into it, its third-party notices, and the ISPP defines the installer reads, with the two folders' budgets written into them from `installer/budgets.json`.
- `ecosemantic-databases` and `ecosemantic setup ecoinvent`: ecoinvent 3.13 cutoff, built from the release's own files and validated against ecoinvent's published results, its two Ecological Scarcity 2021 biotic resources categories against the release's matrix export.

## 0.1.12

- A release's validation and the scoring of every dataset in `ecosemantic-databases` refuse a dataset the compiled background lacks as `not_found`, naming it as `the import names background dataset '<code>', which '<database>' does not hold`, where they answered `invalid`.
- `ecosemantic compute` asks the store for a folder's treatments once and names the exchanges run backwards from that one answer in the impact, the contributions and the inventory it writes; `contribution_analysis` and `calculate_inventory` ask once per call.

## 0.1.11

- `list_sources` names `unit process` as the system model of `uslci` and `bafu`, so the page's form for either source shows it as the system model.
- An inventory's run folder, which `ecosemantic compute` writes into a table folder's `results` and the page's inventory download zips, records `floor` and `dropped` in its `schema.yaml`: the amount at or below which a residue is set aside, and how many were.
- A miss reads the same from every store and names a product system by its id: `no product system <id>`, `no version <hash> of product system <id>`, `no database '<name>' under <directory>; this store serves [...]`, `product system <id> is at <hash>, the write is based on <hash>` for a write on a stale base, and `<system> links <linked>, which has no reference process; set one with update_product_system`.
- `ecosemantic export` into a directory that does not exist is refused as `invalid`, naming the directory.
- `arrange_graph` takes `release_all`, which lets every held card go before the placements apply, and refuses it beside `release`; the page's *Reset layout* releases through it, a held code no process carries included.

## 0.1.10

- An install's summary names the inputs no dataset of the release provides as `cut_off`, the inputs the install cut off from the calculation, in place of `unlinked` and `dropped`; the catalog keeps each as an exchange with its reason, and the record keeps the rows in `cut_off.json` beside it.
- `install_database` refuses a database the server serves before anything is downloaded, unless `replace` is passed, where the refusal came after the download and the build.
- `drop_unlinked` is an `openlca` install's choice: a draft of another source that sets it is refused as `invalid`, and a draft's refusal reaches the caller as `invalid` with its reason.

## 0.1.9

- An install downloads a release's files into `downloads` in the data directory, unless `LCA_DATA_INTERFACE_CACHE` names another folder, so they land under the root the person chose.
- lca-data-interface 0.1.2 or later is required; its cache paths fit Windows.
- Importing the command line, and running `doctor`, `telemetry`, `init`, `connect`, `setup`, `database` or `import`, loads no FastMCP and no page; `compute` and `export` load FastMCP through the tool functions they call.
- The telemetry collector's certificate is checked by the operating system's certificate verifier, and a failed send is logged at INFO, below the warning level the server writes, so nothing is written.

## 0.1.8

- A product system another server process is writing for the first time is announced to the page when its package is whole, never as deleted.

## 0.1.7

- Windows and macOS are tested on every change, beside Linux, at Python 3.12 and 3.14.
- Text is read and written as UTF-8 on every platform, so the tables a person opens on Windows carry their characters (e.g. `·`, accents).
- A database's fingerprint, and the digest of an ecoinvent release's files, are the same on every platform.
- Each install writes its build into its own directory and points the database at it, so a database installs again while a server on Windows serves it; the previous build's files are removed once nothing holds them.
- A data directory written by 0.1.6 opens without reinstalling: the first open moves each database into the new layout, keeping its fingerprint.
- After upgrading, restart every running EcoSemantic server: a server started before the upgrade starts its run and install workers from the upgraded files, which move the data directory into the new layout, and that server then lists no databases until it is restarted.

## 0.1.6

- The licence is the PolyForm Noncommercial License 1.0.0 in every distribution: any noncommercial purpose is permitted, by individuals and by charities, schools, public research and government bodies; commercial use needs a separate licence from Carlos Gaete-Morales.

## 0.1.5

- A running server counts its starts and its agents' tool calls by name, under a random install identifier, and sends the totals every hour and when it stops to `https://telemetry.ecosemantic.com/v1/metrics`. It is on by default. `ecosemantic telemetry off`, `ECOSEMANTIC_TELEMETRY=off` or `DO_NOT_TRACK=1` turns it off, and then nothing is sent and no telemetry file is made. `TELEMETRY.md` states everything that is sent.
- `ecosemantic telemetry [on|off]` records the choice and shows it, with the install identifier and the endpoint; `ecosemantic init` and `ecosemantic doctor` say whether telemetry is on, what it counts and how to turn it off.
- A collector that cannot be reached, answers with an error or never answers does not delay a start or a tool call, and a stop waits for it at most 5 seconds.

## 0.1.0

The first release of the core, six distributions under one version:

- `ecosemantic-engine`: the product-system vocabulary, the typed errors, the exact solve over a memory-mapped background, contributions by process, flow and path, the inventory and plain Monte Carlo with a stop rule on the median.
- `ecosemantic-core`: the ports, the pure computations over a product system, the model package that openLCA opens, the tables folder, database bundles and the native backend that installs them with a fingerprint of their build.
- `ecosemantic-mcp`: forty-three tools for a chatbot, and three guides it reads as resources.
- `ecosemantic-view`: the page a person watches, reads results in and posts requests from.
- `ecosemantic-databases`: ecoinvent 3.10, 3.10.1, 3.11 and 3.12 cutoff built from the release's own files and validated against ecoinvent's published results.
- `ecosemantic`: the command — `serve`, `connect`, `doctor`, `setup`, `database`, `export`, `import`, `compute` — and `import ecosemantic as es`.
