#!/usr/bin/env python3
"""Summarise an `arduino-cli compile --format json` result for CI.

Prints a Markdown report (also appended to $GITHUB_STEP_SUMMARY when set),
shows flash/RAM deltas against an optional base build, lists compiler
warnings that originate in the sketch itself, and exits non-zero when the
build failed or, with --enforce, when memory use exceeds the given limits.
"""
import argparse
import json
import os
import re
import sys

SECTION_LABELS = {"text": "Flash", "data": "RAM (globals)"}
MAX_ERROR_LINES = 60


def load(path):
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # arduino-cli crashed before producing JSON; keep whatever it printed.
        return {"success": False, "compiler_err": raw, "builder_result": {}}


def sections(result):
    out = {}
    for sec in (result.get("builder_result") or {}).get("executable_sections_size") or []:
        out[sec["name"]] = (int(sec["size"]), int(sec["max_size"]))
    return out


def sketch_warnings(result, sketch_dir):
    """Warnings whose file path contains the sketch folder (not a library)."""
    text = (result.get("compiler_err") or "") + "\n" + (result.get("compiler_out") or "")
    pat = re.compile(
        r"^(?P<file>[^:\n]*%s[^:\n]*):(?P<line>\d+):\d+: warning: (?P<msg>.*)$"
        % re.escape(sketch_dir),
        re.M,
    )
    seen, found = set(), []
    for m in pat.finditer(text):
        key = (os.path.basename(m["file"]), m["line"], m["msg"].strip())
        if key not in seen:
            seen.add(key)
            found.append(key)
    return found


def pct(n, d):
    return 100.0 * n / d if d else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--head", required=True, help="compile JSON for this commit")
    ap.add_argument("--base", help="compile JSON for the base commit")
    ap.add_argument("--label", default="")
    ap.add_argument("--sketch-dir", default="")
    ap.add_argument("--max-flash-pct", type=float, default=100.0)
    ap.add_argument("--max-ram-pct", type=float, default=100.0)
    ap.add_argument("--enforce", action="store_true")
    a = ap.parse_args()

    head = load(a.head)
    base = load(a.base) if a.base and os.path.exists(a.base) else None
    title = f"## Firmware build ({a.label})" if a.label else "## Firmware build"
    lines = [title, ""]
    failed = False

    if not head.get("success"):
        failed = True
        lines += [":x: **Compilation failed**", ""]
        if head.get("error"):
            lines += [f"`{head['error']}`", ""]
        err = (head.get("compiler_err") or "").strip() or "(no compiler output captured)"
        lines += ["```"] + err.splitlines()[-MAX_ERROR_LINES:] + ["```", ""]
        print("Compilation failed:")
        print("\n".join(err.splitlines()[-MAX_ERROR_LINES:]))
    else:
        hs = sections(head)
        bs = sections(base) if base and base.get("success") else {}
        limits = {"text": a.max_flash_pct, "data": a.max_ram_pct}
        lines += [
            "| Section | Used | Max | Use | Limit | Delta | |",
            "|---|---:|---:|---:|---:|---:|:--|",
        ]
        for name in ("text", "data"):
            if name not in hs:
                continue
            used, mx = hs[name]
            p = pct(used, mx)
            over = p > limits[name]
            delta = f"{used - bs[name][0]:+d} B" if name in bs else ""
            if over and a.enforce:
                mark, failed = ":x:", True
            elif over:
                mark = ":warning:"
            else:
                mark = ":white_check_mark:"
            lines.append(
                f"| {SECTION_LABELS[name]} | {used} B | {mx} B | {p:.1f}% "
                f"| {limits[name]:.0f}% | {delta} | {mark} |"
            )
            print(
                f"{'FAIL' if over else 'OK  '} {SECTION_LABELS[name]}: {used}/{mx} B "
                f"({p:.1f}%), limit {limits[name]:.0f}%"
                + (f", delta {delta}" if delta else "")
            )
        if base is None:
            lines.append("\n_No base build available; deltas omitted._")
        elif not bs:
            lines.append("\n_Base commit did not compile; deltas omitted._")
        lines.append("")

        warns = sketch_warnings(head, a.sketch_dir) if a.sketch_dir else []
        if warns:
            lines += [
                f"<details><summary>{len(warns)} compiler warning(s) in sketch sources</summary>",
                "",
            ]
            lines += [f"- `{f}:{ln}` {msg}" for f, ln, msg in warns]
            lines += ["", "</details>", ""]
            print(f"{len(warns)} warning(s) in sketch sources")

    report = "\n".join(lines) + "\n"
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(report)
    else:
        print(report)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
