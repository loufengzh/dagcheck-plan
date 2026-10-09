"""Deterministic DAG analysis and non-preemptive list scheduling."""
import heapq
import json
import math
import unicodedata
from fractions import Fraction


MAX_INPUT_CHARS = 1_000_000
MAX_TASKS = 10_000
MAX_EDGES = 100_000


class PlanError(ValueError):
    """Invalid input, including a directed cycle with its witness."""


def _valid_id(value):
    return (isinstance(value, str) and 0 < len(value) <= 256
            and value.strip() == value
            and not any(unicodedata.category(c).startswith("C") for c in value))


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanError(f"{field} must be a finite non-negative number")
    try:
        valid = math.isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise PlanError(f"{field} must be a finite non-negative number")
    return Fraction(str(value))


def _output(value):
    if value.denominator == 1:
        return value.numerator
    try:
        result = float(value)
    except OverflowError as exc:
        raise PlanError("computed time exceeds JSON numeric range") from exc
    if not math.isfinite(result):
        raise PlanError("computed time exceeds JSON numeric range")
    return result


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PlanError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _parse_float(token):
    """Keep float precision, but never silently turn a nonzero input into zero."""
    value = float(token)
    mantissa = token.lower().split("e", 1)[0]
    if value == 0 and any(unicodedata.decimal(digit, 0) for digit in mantissa):
        raise PlanError("nonzero number underflows the supported float range")
    return value


def loads(text):
    """Parse strict JSON (reject duplicate keys and NaN/Infinity)."""
    if not isinstance(text, str) or len(text) > MAX_INPUT_CHARS:
        raise PlanError(f"JSON input must be text of at most {MAX_INPUT_CHARS} characters")
    def constant(value):
        raise PlanError(f"invalid JSON numeric constant: {value}")
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=constant,
                          parse_float=_parse_float)
    except (ValueError, RecursionError) as exc:
        raise PlanError(f"invalid JSON: {exc}") from exc


def _cycle(children, remaining):
    # Iterative DFS avoids Python's recursion limit on long dependency chains.
    color = {}
    for root in sorted(remaining):
        if color.get(root):
            continue
        path, positions = [root], {root: 0}
        color[root] = 1
        stack = [(root, iter(children[root]))]
        while stack:
            node, edges = stack[-1]
            target = next(edges, None)
            if target is None:
                color[node] = 2
                stack.pop()
                positions.pop(node)
                path.pop()
            elif target in remaining:
                if color.get(target) == 1:
                    return path[positions[target]:] + [target]
                if not color.get(target):
                    color[target] = 1
                    positions[target] = len(path)
                    path.append(target)
                    stack.append((target, iter(children[target])))
    raise AssertionError("cyclic residual without cycle")


def plan(document, *, workers=1, budget=None):
    """Return a JSON-compatible plan. Budget limits heuristic makespan, inclusively.

    Durations share an arbitrary caller-chosen time unit. Internally decimal
    representations are rational numbers; only output fractions are rounded.
    """
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise PlanError("workers must be a positive integer")
    limit = None if budget is None else _number(budget, "budget")
    if not isinstance(document, dict) or set(document) != {"tasks"}:
        raise PlanError("document must contain exactly one key: tasks")
    if not isinstance(document["tasks"], list):
        raise PlanError("tasks must be an array")
    if len(document["tasks"]) > MAX_TASKS:
        raise PlanError(f"at most {MAX_TASKS} tasks are supported")
    durations, dependencies = {}, {}
    edge_count = 0
    for index, task in enumerate(document["tasks"]):
        if not isinstance(task, dict) or not {"id", "duration"} <= set(task) or set(task) - {"id", "duration", "needs"}:
            raise PlanError(f"tasks[{index}] requires id, duration, and optional needs only")
        name = task["id"]
        if not _valid_id(name):
            raise PlanError(f"tasks[{index}].id must be a nonempty string (max 256 characters) without outer whitespace or Unicode category C characters")
        if name in durations:
            raise PlanError(f"duplicate task id: {name}")
        durations[name] = _number(task["duration"], f"{name}.duration")
        deps = task.get("needs", [])
        if not isinstance(deps, list) or any(not _valid_id(d) for d in deps):
            raise PlanError(f"{name}.needs must be an array of task IDs")
        edge_count += len(deps)
        if edge_count > MAX_EDGES:
            raise PlanError(f"at most {MAX_EDGES} dependency edges are supported")
        if len(set(deps)) != len(deps):
            raise PlanError(f"duplicate dependency in {name}")
        dependencies[name] = sorted(deps)
    names = sorted(durations)
    children = {name: [] for name in names}
    for name in names:
        for dep in dependencies[name]:
            if dep not in durations:
                raise PlanError(f"unknown dependency {dep} in {name}")
            children[dep].append(name)
    indegree = {name: len(dependencies[name]) for name in names}
    ready = [name for name in names if not indegree[name]]
    heapq.heapify(ready)
    order = []
    while ready:
        name = heapq.heappop(ready)
        order.append(name)
        for child in children[name]:
            indegree[child] -= 1
            if not indegree[child]:
                heapq.heappush(ready, child)
    if len(order) != len(names):
        witness = _cycle(children, {n for n in names if indegree[n]})
        raise PlanError("cycle: " + " -> ".join(witness))
    zero = Fraction(0)
    earliest, finish, predecessor = {}, {}, {}
    for name in order:
        deps = dependencies[name]
        parent = min(deps, key=lambda d: (-finish[d], d)) if deps else None
        predecessor[name] = parent
        earliest[name] = finish[parent] if parent is not None else zero
        finish[name] = earliest[name] + durations[name]
    critical_length = max(finish.values(), default=zero)
    latest, remaining = {}, {}
    for name in reversed(order):
        latest[name] = min((latest[c] for c in children[name]), default=critical_length) - durations[name]
        remaining[name] = durations[name] + max((remaining[c] for c in children[name]), default=zero)
    # Lexicographically smallest maximum-duration source-to-sink path.
    roots = [name for name in names if not dependencies[name]]
    current = min(roots, key=lambda n: (-remaining[n], n)) if roots else None
    critical_path = []
    while current is not None:
        critical_path.append(current)
        current = min(children[current], key=lambda n: (-remaining[n], n)) if children[current] else None
    indegree = {name: len(dependencies[name]) for name in names}
    ready = [(-remaining[n], n) for n in names if not indegree[n]]
    heapq.heapify(ready)
    # Worker identities are 1-based. Avoid allocating workers for idle capacity.
    free = list(range(1, min(workers, len(names)) + 1))
    running, schedule = [], []
    now = zero
    while ready or running:
        # All tasks ending at this instant finish before new dispatches.
        while running and running[0][0] == now:
            _, worker, name = heapq.heappop(running)
            heapq.heappush(free, worker)
            for child in children[name]:
                indegree[child] -= 1
                if not indegree[child]:
                    heapq.heappush(ready, (-remaining[child], child))
        while free and ready:
            _, name = heapq.heappop(ready)
            worker = heapq.heappop(free)
            end = now + durations[name]
            schedule.append({"id": name, "worker": worker, "start": _output(now), "finish": _output(end)})
            heapq.heappush(running, (end, worker, name))
            # Process zero-time completion before further dispatch at this time.
            if end == now:
                break
        if running:
            if running[0][0] == now or not free or not ready:
                now = running[0][0]
    total = sum(durations.values(), zero)
    return {
        "topological_order": order,
        "critical_path": critical_path,
        "unlimited_worker_makespan": _output(critical_length),
        "worker_lower_bound": _output(max(critical_length, total / workers)),
        "total_work": _output(total),
        "workers": workers,
        "heuristic_makespan": _output(now),
        "budget": None if limit is None else _output(limit),
        "within_budget": None if limit is None else now <= limit,
        "timings": {name: {"earliest_start": _output(earliest[name]), "earliest_finish": _output(finish[name]), "latest_start": _output(latest[name]), "latest_finish": _output(latest[name] + durations[name]), "slack": _output(latest[name] - earliest[name])} for name in names},
        "schedule": schedule,
    }
