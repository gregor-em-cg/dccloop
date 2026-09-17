"""Check current public frozen inputs. No runtime, model or native dispatch."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "prototypes/local"


def verify(root=ROOT):
    root = Path(root).resolve()
    manifests = sorted((root / "fixtures").rglob("*FREEZE*.json"))
    manifests += sorted((root / "policies").glob("*FREEZE*.json"))
    manifests += [root / "reports/current-contract/BASELINE-HASHES.json"]
    failures = []
    checked = 0
    for manifest in manifests:
        try:
            record = json.loads(manifest.read_text())
            if "files" in record:
                files = record["files"]
            elif "path" in record and "sha256" in record:
                target = Path(record["path"])
                base = root if target.parts[0] in {"schemas", "policies", "fixtures"} else manifest.parent
                relative = (base / target).relative_to(root).as_posix()
                files = {relative: record["sha256"]}
            else:
                raise ValueError("unrecognized frozen manifest format")
            if not files:
                raise ValueError("empty file manifest")
            for relative, expected in files.items():
                file = (root / relative).resolve()
                if not file.is_relative_to(root) or not file.is_file():
                    failures.append({"file": relative, "error": "missing or outside prototype"})
                    continue
                actual = hashlib.sha256(file.read_bytes()).hexdigest()
                checked += 1
                if actual != expected:
                    failures.append({"file": relative, "error": "frozen SHA-256 mismatch"})
        except (OSError, ValueError, KeyError, TypeError) as error:
            failures.append({"manifest": manifest.relative_to(root).as_posix(), "error": type(error).__name__})
    if not checked:
        failures.append({"error": "no frozen inputs checked"})
    return {"passed": not failures, "manifest_count": len(manifests), "hash_checks": checked,
            "failures": failures, "scope": "Preservation only; not execution or quality acceptance"}


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
