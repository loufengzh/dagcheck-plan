# dagcheck-plan

Explain a CI or batch pipeline before running it: validate its dependency graph,
find its critical path, and estimate a deterministic schedule with limited workers.
Nothing is executed. Python 3.10+, standard-library runtime, MIT license.

[简体中文](docs/README.zh-CN.md) · [Русский](docs/README.ru.md) · [Deutsch](docs/README.de.md)

## Quick start

```sh
python -m pip install .
dagcheck-plan analyze examples/build.json --workers 2 --budget 8
# Or run directly from a source checkout:
python -m dagcheck_plan analyze examples/build.json --workers 2 --format json
python -m unittest discover -s tests -v
```

The example reports `fetch -> test -> package`, an unlimited-worker makespan of
8, and a two-worker heuristic makespan of 8. All durations use the same unit
(seconds, minutes, or another unit you choose).

## Input contract

```json
{"tasks":[
  {"id":"fetch","duration":2},
  {"id":"test","duration":5,"needs":["fetch"]},
  {"id":"package","duration":1,"needs":["test"]}
]}
```

The root must have exactly `tasks`, an array. Tasks require `id` and `duration`;
`needs` defaults to `[]`. Unknown fields are rejected to catch misspellings. IDs
are unique, case-sensitive nonempty strings with no outer whitespace. IDs are limited to 256 characters and reject Unicode category C
(control, format, surrogate, private-use, and unassigned characters). Dependencies
are unique existing IDs. Durations must be finite, nonnegative JSON numbers;
booleans are rejected. Empty graphs and zero durations are valid. Duplicate JSON
keys, duplicate dependencies, unknown IDs, self-dependencies, and cycles are errors.
Cycle errors show an actual directed cycle, not merely blocked downstream nodes.
`-` reads JSON from stdin; files are UTF-8.

## Interpretation

- `topological_order`: lexicographically smallest available ID at each step.
- `critical_path`: one connected maximum-duration source-to-sink path; ties use
  the lexicographically smallest ID sequence. It is not the union of critical nodes.
- `timings`: earliest/latest start and finish plus slack, under unlimited capacity.
  All disconnected components share the same project finish for latest times.
- `unlimited_worker_makespan`: critical-path duration; a lower bound for any worker count.
- `worker_lower_bound`: maximum of that duration and total work / worker count.
- `schedule`: non-preemptive, identical workers numbered from 1. Ready tasks are
  prioritized by largest remaining critical-path duration, then ID. All completions
  at the current time are processed before dispatch. Zero-duration tasks complete
  immediately, allowing their dependents to compete before the next dispatch.
  The lowest free worker ID is assigned first.
- `heuristic_makespan`: length of this specific feasible schedule. **Not a claim of
  an optimal finite-worker schedule.** A missed budget does not prove infeasibility.

`--workers` defaults to **1**. `--budget` always applies to heuristic makespan,
not the lower bound. Equality passes. With no budget, `within_budget` is JSON null.
Exit codes: **0** valid and within budget (or no budget); **1** valid but this
schedule exceeds the budget; **2** invalid input/options or unreadable file.
JSON reports go to stdout; diagnostics go to stderr.

Internally durations are exact rational values of the parsed number's decimal
representation, so `0.1 + 0.2` meets a `0.3` budget. JSON parsing first uses Python
float precision for non-integer input, so arbitrary-precision decimal input is not
preserved. Non-integral report values are rounded to finite Python floats;
budget comparisons occur before that output rounding. Integer outputs are exact.

## Library API

```python
from dagcheck_plan import loads, plan, PlanError

report = plan(loads('{"tasks":[{"id":"lint","duration":3}]}'),
              workers=2, budget=4)
assert report["within_budget"] is True
```

`plan` accepts a Python dict and does not mutate it. `loads` supplies strict JSON
parsing. Invalid input raises `PlanError`, a `ValueError` subclass. Output is
JSON-compatible and deterministic across task and dependency input permutations.

## Scope and alternatives

This tool plans supplied estimates. It does not run commands, read CI secrets,
model worker startup, caches, retries, resource classes, or infer a real CI graph.
Reported times are estimates, not execution guarantees. Do not use it as a security
sandbox or an optimizer. Rational arithmetic can be expensive on huge inputs;
limits are 1,000,000 input characters, 10,000 tasks, and 100,000 dependency edges.
The library task/edge limits also apply to Python dict inputs. Treat inputs as
trusted project configuration; these limits are not a security sandbox.

[NetworkX](https://github.com/networkx/networkx) offers general graph algorithms;
[PyGraphviz](https://github.com/pygraphviz/pygraphviz) integrates Graphviz. This small
project focuses on a no-execution budget-check CLI and explicit scheduling semantics,
not new graph algorithms.

## Development

Run tests from the repository root. Tests include invalid schemas, cycle witnesses,
long chains, zero-time tasks, permutation stability, simultaneous completions,
fractional budgets, CLI exit codes, and 100 seeded random-DAG schedule checks.
CI tests Python 3.10–3.13 and installs the command before its example smoke test.

Possible next work: graph comparison, resource-class capacities, and a GitHub
Actions adapter with explicit limits for dynamic matrices. These are not implemented.
See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [MIT](LICENSE).
