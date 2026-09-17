"""Run local mock/process, simulated native-guard and geometry checks only.

No native application or provider is dispatched. Raw logs remain ignored;
the public summary excludes personal paths and raw traces.
"""
import datetime
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "prototypes/local"
LOGS = REPO / ".test-output"


def run(label, arguments, timeout=1200):
    start = time.monotonic()
    path = LOGS / (label + ".log")
    with path.open("w") as log:
        try:
            process = subprocess.run([sys.executable, "-B", *arguments], cwd=ROOT,
                                     stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            code = process.returncode
        except subprocess.TimeoutExpired:
            code = 124
    print(label + ": " + ("passed" if code == 0 else "failed; inspect " + str(path.relative_to(REPO))), flush=True)
    return {"command": ["python3", "-B", *arguments], "exit_code": code,
            "elapsed_seconds": round(time.monotonic() - start, 3),
            "raw_log_local_only": path.relative_to(REPO).as_posix()}


def latest_report(folder, name, log_name):
    # Bind to this invocation's final output, never silently reuse an older LATEST.
    lines = (LOGS / log_name).read_text().strip().splitlines()
    if not lines:
        raise ValueError("No completed report in this invocation")
    summary = json.loads(lines[-1])
    directory = Path(summary["report"]).resolve()
    if not directory.is_relative_to(ROOT / "reports" / folder):
        raise ValueError("Report outside the expected suite directory")
    index = json.loads((ROOT / "reports" / folder / "LATEST.json").read_text())
    if Path(index["report"]).resolve() != directory:
        raise ValueError("Latest report differs from this invocation")
    return json.loads((directory / name).read_text())


def main():
    LOGS.mkdir(exist_ok=True)
    result = {"recorded_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "platform": platform.system(), "platform_release": platform.release(),
              "python_version": platform.python_version(), "passed": False,
              "provenance": "Executed local source-snapshot checks; see per-group classifications",
              "native_applications_executed": False, "model_providers_called": False,
              "groups": {}, "errors": []}
    current = run("mock-contract", ["-m", "tests.run_current_contract", "--run-suites"])
    result["groups"]["mock_contract"] = current
    current["classification"] = "Actual local mock Python process checks plus synthetic policy scenarios"
    try:
        data = latest_report("current-contract", "ACCEPTANCE.json", "mock-contract.log")
        current["acceptance_passed"] = data["passed"]
        current["historical_groups"] = [{key: group[key] for key in
            ("group", "total", "passed", "failed", "historical_exit_code", "historical_failures")}
            for group in data.get("groups", [])]
        current["current_P11"] = data.get("current_P11", {}).get("status", "not_completed")
        current["preservation"] = data.get("preservation", {})
        current["skipped"] = data.get("skipped", [])
        current["unexplained_failures"] = len(data.get("failures", []))
    except (OSError, KeyError, ValueError):
        result["errors"].append("Current mock acceptance report unavailable; inspect ignored raw log")

    guards = run("native-guards", ["-m", "tests.test_native_integrity"], timeout=120)
    result["groups"]["native_guards"] = guards
    guards["classification"] = "Simulated host/receipt inputs; one actual Python CLI ownership check; native launch spy"
    try:
        data = latest_report("native-integrity", "RESULTS.json", "native-guards.log")
        guards.update({key: data[key] for key in ("passed", "failed", "skipped", "global_budget_unchanged", "blender_executed")})
    except (OSError, KeyError, ValueError):
        result["errors"].append("Native-guard report unavailable; inspect ignored raw log")

    geometry = run("geometry", ["-m", "unittest", "tests.test_fluted_candidate_v4", "-v"], timeout=120)
    result["groups"]["geometry"] = geometry
    geometry["classification"] = "Python geometry predicates with damaged-mesh controls; no visual quality claim"
    text = (LOGS / "geometry.log").read_text()
    count = re.search(r"Ran (\d+) tests? in", text)
    geometry["tests_run"] = int(count.group(1)) if count else None
    if count is None:
        result["errors"].append("Geometry test count unavailable")
    result["passed"] = not result["errors"] and all(g["exit_code"] == 0 for g in result["groups"].values())
    result["unverified"] = ["Native Blender execution in this public snapshot", "Other DCCs/renderers",
                            "Live model providers", "Windows controller operation", "Host power loss",
                            "Production visual acceptance", "All crash boundaries"]
    destination = REPO / "verification/local-test-results.json"
    if any(p.name.casefold() == destination.name.casefold() and p.name != destination.name for p in destination.parent.iterdir()):
        raise RuntimeError("Case-colliding result path")
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
