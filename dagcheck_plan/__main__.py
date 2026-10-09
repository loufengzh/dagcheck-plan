"""Command-line interface; diagnostics go to stderr, reports to stdout."""
import argparse
import json
import sys
from pathlib import Path
from .core import MAX_INPUT_CHARS, PlanError, _parse_float, loads, plan


def _budget(token):
    try:
        return _parse_float(token)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dagcheck-plan", description="Validate a task DAG and simulate a deterministic worker schedule; never execute tasks.")
    parser.add_argument("command", choices=["analyze"])
    parser.add_argument("graph", help="JSON graph path, or - for stdin")
    parser.add_argument("--workers", type=int, default=1, help="positive worker count (default: 1)")
    parser.add_argument("--budget", type=_budget, help="inclusive limit on simulated makespan")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args(argv)
    try:
        if args.graph == "-":
            raw = sys.stdin.read(MAX_INPUT_CHARS + 1)
        else:
            with Path(args.graph).open(encoding="utf-8") as stream:
                raw = stream.read(MAX_INPUT_CHARS + 1)
        result = plan(loads(raw), workers=args.workers, budget=args.budget)
    except (PlanError, OSError, UnicodeError) as exc:
        print(f"dagcheck-plan: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    else:
        print("Topological order: " + ", ".join(result["topological_order"]))
        print("Critical path: " + " -> ".join(result["critical_path"]))
        print(f"Unlimited-worker makespan: {result['unlimited_worker_makespan']}")
        print(f"Worker lower bound: {result['worker_lower_bound']}")
        print(f"Heuristic makespan ({args.workers} workers): {result['heuristic_makespan']}")
        if args.budget is not None:
            print("Budget: " + ("PASS" if result["within_budget"] else "EXCEEDED"))
        for item in result["schedule"]:
            print(f"  {item['id']}: worker {item['worker']}, {item['start']} -> {item['finish']}")
    return 1 if result["within_budget"] is False else 0


if __name__ == "__main__":
    sys.exit(main())
