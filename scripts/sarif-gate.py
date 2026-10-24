#!/usr/bin/env python3
"""Security gate for SARIF reports.

Prints every finding and exits 1 when at least one is High/Critical:
  - result level (or the rule's default level) is "error", or
  - the rule's "security-severity" property is >= the threshold (default 7.0,
    the CVSS boundary for High).

Usage: sarif-gate.py REPORT.sarif [--threshold 7.0]
"""

import argparse
import json
import sys


def severity(rule: dict) -> float | None:
    value = (rule.get("properties") or {}).get("security-severity")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report")
    parser.add_argument("--threshold", type=float, default=7.0)
    args = parser.parse_args()

    with open(args.report, encoding="utf-8") as fh:
        sarif = json.load(fh)

    blocking = 0
    total = 0
    for run in sarif.get("runs", []):
        tool = run.get("tool", {}).get("driver", {}).get("name", "scanner")
        rules = {r.get("id"): r for r in run.get("tool", {}).get("driver", {}).get("rules", [])}
        for result in run.get("results", []):
            total += 1
            rule = rules.get(result.get("ruleId"), {})
            level = result.get("level") or rule.get("defaultConfiguration", {}).get("level", "warning")
            score = severity(rule)
            is_blocking = level == "error" or (score is not None and score >= args.threshold)
            blocking += is_blocking

            loc = (result.get("locations") or [{}])[0].get("physicalLocation", {})
            where = loc.get("artifactLocation", {}).get("uri", "?")
            line = loc.get("region", {}).get("startLine")
            if line:
                where += f":{line}"
            score_txt = f" severity={score}" if score is not None else ""
            mark = "BLOCK" if is_blocking else "info "
            message = result.get("message", {}).get("text", "").splitlines()[0][:160]
            print(f"[{mark}] {tool}: {result.get('ruleId')} ({level}{score_txt}) {where}\n         {message}")

    print(f"\n{total} finding(s), {blocking} High/Critical (blocking).")
    if blocking:
        print("Security gate FAILED.")
        return 1
    print("Security gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
