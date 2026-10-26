# Telemetry

EcoSemantic counts how often a server starts and which tools agents call. The counts are anonymous, they are on by default, and this page states everything that is sent.

## What is sent

Two counters, made by the meter named `ecosemantic`, and nothing else. Any other metric or label is not sent. Each counter is sent with its name, the table's attributes and a fixed description: `Server starts` and `Tool calls by tool name`.

| Metric | Kind | Attributes |
|---|---|---|
| `ecosemantic.server.starts` | counter, +1 when a server starts serving | none |
| `ecosemantic.tool.calls` | counter, +1 when a tool call ends, successful or refused | `tool`: the tool's name, one of the server's tool names; a name outside that list is counted as `other` |

Every report also carries these resource attributes.

| Attribute | Value |
|---|---|
| `service.name` | `ecosemantic` |
| `service.version` | the installed `ecosemantic` distribution's version |
| `service.instance.id` | the install identifier |
| `os.type` | `sys.platform` (`linux`, `darwin`, `win32`) |
| `ecosemantic.transport` | `stdio` or `http` |

No host name, process or user is added. Each report also carries the time it covers, the start and end of the interval it counts; the collector replaces both with the time it received the report. The sender sets no header of its own beyond the content type, takes no header, endpoint, certificate or timeout from `OTEL_*` environment variables, and sends the standard headers of Python's `urllib`, including `User-Agent: Python-urllib/3.x`. It goes through a proxy when the environment names one. Exemplars, which would carry a trace or span identifier, are off whatever the `OTEL_*` variables say. `OTEL_SDK_DISABLED=true` stops the SDK, so nothing is counted, while `ecosemantic telemetry` still reports the choice.

## What each count means

- A start is one `ecosemantic serve` process beginning to serve. A stdio server that yields the page to a newer one keeps serving and is not counted again. The workers that carry an install or a run report nothing.
- A tool call is every call an agent sends to a tool. The page's own calls to the tools are not counted. A call refused for its arguments, or naming no tool, is counted.
- Counts are sent as the amount counted since the last report.

## The first start

The first time a server starts with telemetry on and no choice recorded, it writes one line to standard error saying what is counted and how to turn it off, and records that it did. `ecosemantic init` and `ecosemantic doctor` print the same line whenever telemetry is on.

## The install identifier

A random UUID (version 4), made the first time a server starts with telemetry on and kept in `telemetry.json` in the data directory, beside your choice. It identifies an installation, not a person, and is derived from nothing on the machine. Deleting the file makes a new one. A server started with telemetry off makes no identifier.

## What is never sent

Nothing from inside your work leaves the machine: no tool arguments or answers, no product system, process, flow or database names, no error messages, no paths, no session or client identifiers, no account.

## Where it goes and how long it is kept

A report is posted to `https://telemetry.ecosemantic.com/v1/metrics` every hour and once when the server stops, with a 5 second timeout. A report that fails is dropped. Starting and tool calls never wait on it; stopping waits for the last report at most 5 seconds. A server stopped by SIGTERM sends that last report before it exits. A server killed outright, by SIGKILL or by Windows ending the process, sends none, and what it counted since its last hourly report is lost. `ECOSEMANTIC_TELEMETRY_ENDPOINT` names another address, for a collector you run yourself. The collector sees the sender's address on the connection, as any web request does, and does not keep it. It keeps only the two metrics and the attributes above, adds `collector.day`, the day it received the report, drops anything else, and stores the totals for 24 months: each one is kept at least 730 days and deleted no later than 731 days and 1 hour after the collector received it, plus the few seconds the collector takes to write it.

## The counts are unauthenticated

The collector holds no key, so anyone can post made-up install identifiers. The package's source is public, and a key in it would be public too. The counts are for judging use in aggregate, and an install counts as returning only after it has reported on two different days.

## Turning it off

Telemetry is on unless one of these says off. They are checked in this order when a server starts.

The two switches decide before the file is read, so a damaged `telemetry.json` does not refuse a start they turned off.

1. `ECOSEMANTIC_TELEMETRY` set to `off`. Set to `on`, it overrides the other two. Any other value is refused: the server does not start, and `ecosemantic telemetry on` or `off` writes nothing.
2. `DO_NOT_TRACK` set to anything but empty or `0`.
3. The choice in `telemetry.json`, which a command writes.

```bash
ecosemantic telemetry off
ecosemantic telemetry on
ecosemantic telemetry
```

`ecosemantic telemetry` alone shows whether telemetry is on, which setting decided it, the install identifier and the endpoint. `ecosemantic doctor` reports whether telemetry is on and why. A choice applies to servers started after it.

The two variables reach only the servers started with the environment that sets them. A chatbot such as Claude Desktop starts its server with its own environment, and `ecosemantic connect` does not carry either variable into it, so a variable set in your shell does not turn off the server your chatbot starts. `ecosemantic telemetry off` records the choice in `telemetry.json`, which every server on this machine reads, unless a variable in its own environment decides first; when a variable decides, `ecosemantic telemetry` and `ecosemantic doctor` say so.

A server started with telemetry off makes no provider, no thread, no `telemetry.json` and no identifier, and nothing connects to the collector. The command `ecosemantic telemetry off` writes `telemetry.json` to record the choice.
