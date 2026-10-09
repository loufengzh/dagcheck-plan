import contextlib
import io
import itertools
import json
import random
import unittest
from unittest.mock import patch
from dagcheck_plan import PlanError, loads, plan
from dagcheck_plan.__main__ import main


def graph(*tasks):
    return {"tasks": [{"id": n, "duration": d, "needs": list(deps)} for n, d, deps in tasks]}


class PlanningTests(unittest.TestCase):
    def test_chain(self):
        p = plan(graph(("a", 2, []), ("b", 3, ["a"]), ("c", 1, ["b"])), workers=4)
        self.assertEqual(p["critical_path"], ["a", "b", "c"])
        self.assertEqual(p["heuristic_makespan"], 6)
        self.assertTrue(all(v["slack"] == 0 for v in p["timings"].values()))

    def test_diamond(self):
        p = plan(graph(("a", 2, []), ("b", 3, ["a"]), ("c", 5, ["a"]), ("d", 1, ["b", "c"])), workers=2)
        self.assertEqual(p["critical_path"], ["a", "c", "d"])
        self.assertEqual(p["timings"]["b"]["slack"], 2)
        self.assertEqual(p["heuristic_makespan"], 8)
        self.assertEqual(p["total_work"], 11)

    def test_disconnected(self):
        p = plan(graph(("a", 2, []), ("z", 5, [])), workers=2)
        self.assertEqual(p["critical_path"], ["z"])
        self.assertEqual(p["timings"]["a"]["latest_start"], 3)

    def test_tied_path_is_connected(self):
        p = plan(graph(("a", 1, []), ("b", 1, []), ("c", 1, ["a", "b"])))
        self.assertEqual(p["critical_path"], ["a", "c"])
        self.assertEqual(p["topological_order"], ["a", "b", "c"])

    def test_critical_path_full_sequence_tie(self):
        p = plan(graph(("z", 1, []), ("b", 1, ["z"]), ("a", 1, []), ("c", 1, ["a"])))
        self.assertEqual(p["critical_path"], ["a", "c"])

    def test_zero_chain_and_empty(self):
        p = plan(graph(("a", 0, []), ("b", 0, ["a"]), ("c", 0, ["b"])), workers=2, budget=0)
        self.assertEqual(p["heuristic_makespan"], 0)
        self.assertEqual(len(p["schedule"]), 3)
        self.assertEqual(p["critical_path"], ["a", "b", "c"])
        p = plan({"tasks": []}, workers=1000000000)
        self.assertEqual(p["critical_path"], [])
        self.assertEqual(p["heuristic_makespan"], 0)

    def test_worker_bottleneck_and_budget(self):
        g = graph(("a", 3, []), ("b", 3, []), ("c", 3, []))
        p = plan(g, workers=2, budget=5)
        self.assertEqual(p["unlimited_worker_makespan"], 3)
        self.assertEqual(p["worker_lower_bound"], 4.5)
        self.assertEqual(p["heuristic_makespan"], 6)
        self.assertFalse(p["within_budget"])
        self.assertTrue(plan(g, workers=2, budget=6)["within_budget"])

    def test_all_simultaneous_completions_before_dispatch(self):
        g = graph(("a", 1, []), ("b", 1, []), ("x", 1, ["a"]), ("z", 4, ["b"]), ("y", 2, ["a", "b"]))
        p = plan(g, workers=2)
        at_one = [t["id"] for t in p["schedule"] if t["start"] == 1]
        self.assertEqual(at_one, ["z", "y"])

    def test_fractional_no_drift(self):
        p = plan(graph(("a", .1, []), ("b", .2, ["a"])), budget=.3)
        self.assertEqual(p["heuristic_makespan"], .3)
        self.assertTrue(p["within_budget"])

    def test_permutation_stability(self):
        g = graph(("a", 1, []), ("b", 1, []), ("c", 1, ["b", "a"]))
        expected = plan(g, workers=2)
        for tasks in itertools.permutations(g["tasks"]):
            self.assertEqual(plan({"tasks": list(tasks)}, workers=2), expected)

    def test_long_chain_without_recursion(self):
        tasks = [(str(i), 0, [str(i-1)] if i else []) for i in range(1500)]
        self.assertEqual(len(plan(graph(*tasks))["critical_path"]), 1500)

    def test_seeded_schedule_invariants(self):
        rng = random.Random(7)
        for _ in range(100):
            tasks = [(str(i), rng.randrange(5), [str(j) for j in range(i) if rng.random() < .2]) for i in range(15)]
            p = plan(graph(*tasks), workers=3)
            schedule = {t["id"]: t for t in p["schedule"]}
            self.assertEqual(len(schedule), len(tasks))
            for name, duration, deps in tasks:
                task = schedule[name]
                self.assertEqual(task["finish"] - task["start"], duration)
                self.assertTrue(all(schedule[d]["finish"] <= task["start"] for d in deps))
            for worker in range(1, 4):
                active = [t for t in p["schedule"] if t["worker"] == worker]
                self.assertTrue(all(a["finish"] <= b["start"] for a, b in zip(active, active[1:])))
            self.assertGreaterEqual(p["heuristic_makespan"], p["worker_lower_bound"])


class ValidationTests(unittest.TestCase):
    def test_invalid_numbers(self):
        for value in [True, False, -1, float("nan"), float("inf"), "1", None, 10**400]:
            with self.subTest(value=str(value)), self.assertRaises(PlanError):
                plan(graph(("a", value, [])))

    def test_invalid_schema(self):
        bad = [[], {}, {"tasks": {}}, {"tasks": [], "extra": 1}, {"tasks": [None]},
               {"tasks": [{"id": "a"}]}, graph(("", 1, [])), graph((" a", 1, [])),
               graph((True, 1, [])), graph(("a", 1, [False])), graph(("a", 1, ["x"])),
               graph(("a", 1, []), ("a", 2, [])), graph(("a", 1, ["b", "b"]), ("b", 1, []))]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(PlanError):
                plan(value)

    def test_cycle_witness_excludes_downstream(self):
        with self.assertRaisesRegex(PlanError, r"cycle: a -> b -> a$"):
            plan(graph(("a", 1, ["b"]), ("b", 1, ["a"]), ("z", 1, ["b"])))
        with self.assertRaisesRegex(PlanError, "a -> a"):
            plan(graph(("a", 1, ["a"])))

    def test_worker_budget_validation(self):
        for workers in [0, -1, True, 1.5, None]:
            with self.assertRaises(PlanError):
                plan({"tasks": []}, workers=workers)
        for budget in [-1, True, float("inf")]:
            with self.assertRaises(PlanError):
                plan({"tasks": []}, budget=budget)

    def test_resource_and_identifier_limits(self):
        for name in ["a\n", "a\x1bb", "\ud800", "x" * 257, "a\u202eb"]:
            with self.assertRaises(PlanError):
                plan(graph((name, 1, [])))
        with self.assertRaises(PlanError):
            loads(" " * 1_000_001)
        with self.assertRaises(PlanError):
            loads('{"tasks": [], "n":' + '1' * 5000 + '}')
        with self.assertRaises(PlanError):
            plan({"tasks": [{"id": str(i), "duration": 0} for i in range(10_001)]})

    def test_json_float_underflow(self):
        for token in ("1e-400", "-1e-400", "2e-324", "-2e-324"):
            with self.subTest(token=token), self.assertRaisesRegex(PlanError, "underflows"):
                loads('{"tasks":[{"id":"a","duration":' + token + '}]}')
        for token in ("0e-400", "-0e-400", "0.000e-999999999999"):
            with self.subTest(token=token):
                p = plan(loads('{"tasks":[{"id":"a","duration":' + token + '}]}'), budget=0)
                self.assertEqual(p["heuristic_makespan"], 0)
                self.assertTrue(p["within_budget"])
        p = plan(loads('{"tasks":[{"id":"a","duration":5e-324}]}'), budget=0)
        self.assertGreater(p["heuristic_makespan"], 0)
        self.assertFalse(p["within_budget"])

    def test_strict_json(self):
        for raw in ['{"tasks": [], "tasks": []}', '{"tasks":[NaN]}', '[', '{"tasks":[Infinity]}']:
            with self.assertRaises(PlanError):
                loads(raw)


class CliTests(unittest.TestCase):
    def test_json_and_budget_exit(self):
        for budget, code in [(8, 0), (7, 1)]:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                actual = main(["analyze", "examples/build.json", "--workers", "2", "--budget", str(budget), "--format", "json"])
            self.assertEqual(actual, code)
            self.assertEqual(json.loads(out.getvalue())["heuristic_makespan"], 8)

    def test_json_underflow_cli(self):
        for token in ("1e-400", "-1e-400"):
            out, err = io.StringIO(), io.StringIO()
            raw = '{"tasks":[{"id":"a","duration":' + token + '}]}'
            with self.subTest(token=token), patch("sys.stdin", io.StringIO(raw)), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["analyze", "-", "--budget", "0", "--format", "json"])
            self.assertEqual(code, 2)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("underflows", err.getvalue())

    def test_budget_underflow(self):
        for token in ("1e-400", "-1e-400", "2e-324", "-2e-324", "١e-٤٠٠"):
            out, err = io.StringIO(), io.StringIO()
            with self.subTest(token=token), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as exc:
                    main(["analyze", "examples/build.json", "--budget=" + token])
            self.assertEqual(exc.exception.code, 2)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("underflows", err.getvalue())
        for token in ("0e-400", "-0e-400", "5e-324"):
            with self.subTest(token=token), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["analyze", "examples/build.json", "--budget=" + token]), 1)

    def test_missing_file(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["analyze", "missing-file.json"]), 2)


if __name__ == "__main__":
    unittest.main()
