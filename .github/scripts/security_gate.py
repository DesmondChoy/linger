"""Fail a release check on high or critical findings, or incomplete scan evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def trivy_findings(document: dict) -> list[str]:
    if document.get("SchemaVersion") != 2 or not document.get("ArtifactName"):
        raise ValueError("Unrecognized Trivy report.")
    results = document.get("Results")
    if not isinstance(results, list) or not results:
        raise ValueError("Trivy did not identify any scan targets.")
    findings = []
    for result in results:
        for finding in result.get("Vulnerabilities") or []:
            severity = finding.get("Severity")
            if severity not in {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
                raise ValueError("Trivy finding has an unrecognized severity.")
            if severity in {"HIGH", "CRITICAL"}:
                findings.append(f"{result['Target']}: {finding['VulnerabilityID']} ({severity})")
    return findings


def codeql_findings(document: dict) -> list[str]:
    runs = document.get("runs")
    if document.get("version") != "2.1.0" or not isinstance(runs, list) or not runs:
        raise ValueError("CodeQL did not produce a SARIF run.")
    findings = []
    for run in runs:
        driver = run["tool"]["driver"]
        if driver.get("name") != "CodeQL" or not isinstance(run.get("results"), list):
            raise ValueError("Unrecognized CodeQL results.")
        if any(invocation.get("executionSuccessful") is False for invocation in run.get("invocations", [])):
            raise ValueError("CodeQL reports an unsuccessful analysis.")
        rules = {rule["id"]: rule for rule in driver.get("rules", [])}
        for result in run["results"]:
            rule = rules.get(result.get("ruleId"))
            if rule is None:
                raise ValueError("CodeQL result has no rule metadata.")
            score = rule.get("properties", {}).get("security-severity")
            if score is not None and float(score) >= 7:
                findings.append(f"{rule['id']}: security severity {score}")
            elif score is None and result.get("level", rule.get("defaultConfiguration", {}).get("level")) == "error":
                findings.append(f"{rule['id']}: error without a numeric security severity")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["trivy", "codeql"])
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    paths = sorted(args.report.glob("*.sarif")) if args.report.is_dir() else [args.report]
    if not paths:
        parser.exit(1, "No scan reports were written.\n")
    findings = []
    try:
        for path in paths:
            document = json.loads(path.read_text())
            findings.extend((trivy_findings if args.kind == "trivy" else codeql_findings)(document))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Security evidence is incomplete: {exc}\n")
    for finding in findings:
        print(finding)
    print(f"Blocking findings: {len(findings)}. Full reports also contain lower severity findings.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
