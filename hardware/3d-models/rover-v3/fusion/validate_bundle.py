#!/usr/bin/env python3
"""Run the package preflight outside Fusion; this does not execute Fusion CAD."""
import argparse
import ast
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "RoverFusion"))
from manifest_tools import load_and_preflight


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", default=str(HERE / "RoverFusion" / "assembly_manifest.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        for file in (HERE / "RoverFusion").glob("*.py"):
            ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        manifest, report = load_and_preflight(args.manifest)
        report["python_ast_valid"] = True
        report["fusion_runtime_executed"] = False
        report["project_name"] = manifest.get("project_name", "Rover V3")
    except Exception as exc:
        report = {"status": "failed", "error": str(exc), "fusion_runtime_executed": False}
    output = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
