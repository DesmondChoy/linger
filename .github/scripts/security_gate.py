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


def _rule_metadata(tool: dict, result: dict) -> dict:
    reference = dict(result.get("rule", {}))
    for legacy, key in (("ruleId", "id"), ("ruleIndex", "index")):
        if legacy in result:
            if key in reference and reference[key] != result[legacy]:
                raise ValueError("CodeQL result has conflicting rule references.")
            reference[key] = result[legacy]

    component_reference = reference.get("toolComponent", {})
    component = tool["driver"]
    extensions = tool.get("extensions", [])
    if "index" in component_reference:
        index = component_reference["index"]
        if type(index) is not int or not 0 <= index < len(extensions):
            raise ValueError("CodeQL result has no matching component metadata.")
        component = extensions[index]
    elif "guid" in component_reference:
        matches = [item for item in [component, *extensions] if item.get("guid") == component_reference["guid"]]
        if len(matches) != 1:
            raise ValueError("CodeQL result has no unique component metadata.")
        component = matches[0]
    if any(component.get(key) != component_reference[key] for key in ("name", "guid") if key in component_reference):
        raise ValueError("CodeQL result has conflicting component metadata.")

    rules = component.get("rules", [])
    identity = {key: reference[key] for key in ("id", "guid") if key in reference}
    if "index" in reference:
        index = reference["index"]
        if type(index) is not int or not 0 <= index < len(rules):
            raise ValueError("CodeQL result has no matching rule metadata.")
        rule = rules[index]
    else:
        matches = [rule for rule in rules if identity and all(rule.get(key) == value for key, value in identity.items())]
        if len(matches) != 1:
            raise ValueError("CodeQL result has no unique rule metadata.")
        rule = matches[0]
    if not rule.get("id") or any(rule.get(key) != value for key, value in identity.items()):
        raise ValueError("CodeQL result has conflicting rule metadata.")
    return rule


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
        for result in run["results"]:
            rule = _rule_metadata(run["tool"], result)
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
