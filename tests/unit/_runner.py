#!/usr/bin/env python3
"""
Tiny zero-dependency test runner.

We avoid pytest on purpose: the whole point of this layer is that it runs in CI
on a bare `python3` with nothing installed. Each test file collects its test
functions into a CASES list and calls run(CASES). A test "fails" by raising
(an assert or any exception); it "passes" by returning normally.

run() prints one line per test and returns a process exit code: 0 if all passed,
1 if any failed. run_all() discovers and runs every test_*.py in this directory.
"""
import importlib.util
import os
import sys
import traceback

GREEN = "\033[32m" if sys.stdout.isatty() else ""
RED = "\033[31m" if sys.stdout.isatty() else ""
DIM = "\033[2m" if sys.stdout.isatty() else ""
RESET = "\033[0m" if sys.stdout.isatty() else ""


def run(cases, label=""):
    passed = 0
    failed = 0
    if label:
        print("%s%s%s" % (DIM, label, RESET))
    for fn in cases:
        name = fn.__name__
        try:
            fn()
            print("  %sPASS%s %s" % (GREEN, RESET, name))
            passed += 1
        except Exception as exc:  # noqa: BLE001 - a test runner catches everything
            print("  %sFAIL%s %s" % (RED, RESET, name))
            doc = (fn.__doc__ or "").strip().splitlines()
            if doc:
                print("       guards: %s" % doc[0])
            print("       %s: %s" % (type(exc).__name__, exc))
            tb = traceback.format_exc().strip().splitlines()
            # show only the assertion frame, not the runner frames
            for line in tb[-3:]:
                print("       %s%s%s" % (DIM, line, RESET))
            failed += 1
    print("  -> %d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


def run_all():
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    files = sorted(f for f in os.listdir(here)
                   if f.startswith("test_") and f.endswith(".py"))
    total_fail = 0
    print("=" * 60)
    print("CLAIRE UNIT TESTS (deterministic — must be 100%% green in CI)")
    print("=" * 60)
    for f in files:
        path = os.path.join(here, f)
        spec = importlib.util.spec_from_file_location(f[:-3], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cases = getattr(mod, "CASES", [])
        if not cases:
            continue
        total_fail += run(cases, label=f)
    print("=" * 60)
    if total_fail:
        print("%sRESULT: %d test file(s) had failures%s" % (RED, total_fail, RESET))
    else:
        print("%sRESULT: all unit tests passed%s" % (GREEN, RESET))
    print("=" * 60)
    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(run_all())
