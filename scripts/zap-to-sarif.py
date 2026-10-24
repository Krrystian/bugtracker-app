#!/usr/bin/env python3
"""Convert an OWASP ZAP JSON report (zap-baseline.py -J) to SARIF 2.1.0.

ZAP risk -> SARIF level / security-severity:
  3 High          -> error    / 8.0  (blocks in scripts/sarif-gate.py)
  2 Medium        -> warning  / 5.0
  1 Low           -> note     / 3.0
  0 Informational -> note     / 0.0
Informational alerts (risk 0) are left out of the SARIF unless the policy marks
them FAIL: ZAP itself does not consider them vulnerabilities (e.g. "a login form
was found"); they stay in the full HTML/JSON report.
Rules marked FAIL in the policy file (--policy, zap-baseline rules.tsv format)
are reported as "error" / 8.0 regardless of their ZAP risk: the project decided
that these must never reach production.

Findings are about a running web app, not a source file, so each result points
at the scanned URL path (logical location) and at the chart that was deployed.

Usage: zap-to-sarif.py zap.json zap.sarif [--policy .zap/rules.tsv]
"""

import argparse
import html
import json
import re
import sys
from urllib.parse import urlparse

LEVELS = {3: ("error", "8.0"), 2: ("warning", "5.0"), 1: ("note", "3.0"), 0: ("note", "0.0")}
DEPLOYED_ARTIFACT = "charts/bugtracker/values.yaml"


def failing_rules(path: str | None) -> set[str]:
    if not path:
        return set()
    rules = set()
    for line in open(path, encoding="utf-8"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 2 and not parts[0].startswith("#") and parts[1].strip() == "FAIL":
            rules.add(parts[0].strip())
    return rules


def text(value: str) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(value or "")).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--policy")
    args = parser.parse_args()
    src, dst = args.src, args.dst
    policy_fail = failing_rules(args.policy)
    report = json.load(open(src, encoding="utf-8"))
    version = report.get("@version", "unknown")

    rules: dict[str, dict] = {}
    results = []
    for site in report.get("site", []):
        for alert in site.get("alerts", []):
            risk = int(alert.get("riskcode", 0))
            if risk == 0 and str(alert.get("pluginid")) not in policy_fail:
                continue
            level, severity = LEVELS.get(risk, ("note", "0.0"))
            if str(alert.get("pluginid")) in policy_fail:
                level, severity = "error", "8.0"
            rule_id = f"zap-{alert.get('pluginid')}"
            name = alert.get("alert") or alert.get("name") or rule_id
            tags = ["security", "dast"]
            if str(alert.get("pluginid")) in policy_fail:
                tags.append("policy-fail")
            if alert.get("cweid") not in (None, "", "-1", "0"):
                tags.append(f"CWE-{alert['cweid']}")
            rules[rule_id] = {
                "id": rule_id,
                "name": re.sub(r"\W+", "", name.title()),
                "shortDescription": {"text": name},
                "fullDescription": {"text": text(alert.get("desc"))},
                "help": {"text": f"{text(alert.get('solution'))}\n\n{text(alert.get('reference'))}".strip()},
                "defaultConfiguration": {"level": level},
                "properties": {"security-severity": severity, "tags": tags},
            }
            for inst in alert.get("instances", []) or [{"uri": site.get("@name", "")}]:
                path = urlparse(inst.get("uri", "")).path or "/"
                detail = ", ".join(
                    f"{k}: {inst[k]}" for k in ("method", "param", "evidence") if inst.get(k)
                )
                results.append({
                    "ruleId": rule_id,
                    "level": level,
                    "message": {"text": f"{name} at {inst.get('uri', '')}" + (f" ({detail})" if detail else "")},
                    "locations": [{
                        "physicalLocation": {
                            "artifactLocation": {"uri": DEPLOYED_ARTIFACT},
                            "region": {"startLine": 1},
                        },
                        "logicalLocations": [{"name": path, "kind": "resource"}],
                    }],
                    "partialFingerprints": {"zapAlert/v1": f"{rule_id}:{inst.get('method', 'GET')}:{path}:{inst.get('param', '')}"},
                })

    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "OWASP ZAP",
                "version": version,
                "informationUri": "https://www.zaproxy.org/",
                "rules": list(rules.values()),
            }},
            "results": results,
        }],
    }
    json.dump(sarif, open(dst, "w", encoding="utf-8"), indent=2)
    print(f"{len(results)} result(s) from {len(rules)} ZAP rule(s) -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
