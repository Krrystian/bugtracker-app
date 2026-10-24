#!/usr/bin/env python3
"""Set level and security-severity on every rule/result of a SARIF report.

For scanners whose SARIF carries no severity at all (e.g. Gitleaks): without it
scripts/sarif-gate.py would treat findings as non-blocking and GitHub would show
them as plain warnings. A leaked secret is always treated as Critical.

Usage: sarif-set-severity.py IN.sarif OUT.sarif --level error --security-severity 9.0
"""

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--level", default="error", choices=["error", "warning", "note"])
    parser.add_argument("--security-severity", default="9.0")
    args = parser.parse_args()

    sarif = json.load(open(args.src, encoding="utf-8"))
    for run in sarif.get("runs", []):
        for rule in run.get("tool", {}).get("driver", {}).get("rules", []):
            rule.setdefault("defaultConfiguration", {})["level"] = args.level
            rule.setdefault("properties", {})["security-severity"] = args.security_severity
        for result in run.get("results", []):
            result["level"] = args.level
    json.dump(sarif, open(args.dst, "w", encoding="utf-8"))


if __name__ == "__main__":
    main()
