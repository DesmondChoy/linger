"""CodeQL rule references resolve within their declared SARIF tool component."""

import importlib.util
from pathlib import Path

import pytest


_script = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "security_gate.py"
_spec = importlib.util.spec_from_file_location("security_gate_sarif", _script)
security = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(security)


def sarif(score="8.1"):
    return {"version": "2.1.0", "runs": [{
        "tool": {"driver": {"name": "CodeQL", "rules": [{"id": "unsafe", "properties": {"security-severity": score}}]}},
        "results": [{"ruleId": "unsafe"}],
    }]}


def extension_sarif():
    document = sarif("1.0")
    run = document["runs"][0]
    run["tool"]["extensions"] = [{
        "name": "codeql/python-queries", "guid": "extension-guid",
        "rules": [{"id": "unsafe", "properties": {"security-severity": "7.5"}}],
    }]
    run["results"] = [{"ruleId": "unsafe", "rule": {"id": "unsafe", "index": 0, "toolComponent": {"index": 0}}}]
    return document


def test_codeql_resolves_hosted_extension_metadata_without_driver_collision():
    document = extension_sarif()
    assert security.codeql_findings(document) == ["unsafe: security severity 7.5"]
    document["runs"][0]["tool"]["driver"]["rules"] = []
    assert security.codeql_findings(document) == ["unsafe: security severity 7.5"]


def test_codeql_resolves_component_guid_and_rule_id_without_indexes():
    document = extension_sarif()
    document["runs"][0]["results"][0]["rule"] = {"id": "unsafe", "toolComponent": {"guid": "extension-guid"}}
    assert security.codeql_findings(document) == ["unsafe: security severity 7.5"]


def test_codeql_accepts_legacy_driver_rule_index():
    document = sarif()
    document["runs"][0]["results"] = [{"ruleIndex": 0}]
    assert security.codeql_findings(document) == ["unsafe: security severity 8.1"]


@pytest.mark.parametrize("index", [-1, 1, True, "0"])
@pytest.mark.parametrize("target", ["component", "rule"])
def test_codeql_rejects_invalid_reference_indexes(index, target):
    document = extension_sarif()
    reference = document["runs"][0]["results"][0]["rule"]
    if target == "component":
        reference["toolComponent"]["index"] = index
    else:
        reference["index"] = index
    with pytest.raises(ValueError, match="metadata"):
        security.codeql_findings(document)


@pytest.mark.parametrize("change", [
    {"ruleId": "different"}, {"ruleIndex": 1},
    {"rule": {"id": "unsafe", "index": 0, "toolComponent": {"index": 0, "name": "different"}}},
    {"rule": {"id": "unsafe", "index": 0, "toolComponent": {"index": 0, "guid": "different"}}},
])
def test_codeql_rejects_conflicting_rule_or_component_identity(change):
    document = extension_sarif()
    document["runs"][0]["results"][0].update(change)
    with pytest.raises(ValueError, match="conflicting"):
        security.codeql_findings(document)


def test_codeql_missing_component_reference_never_borrows_extension_metadata():
    document = extension_sarif()
    document["runs"][0]["tool"]["driver"]["rules"] = []
    del document["runs"][0]["results"][0]["rule"]["toolComponent"]
    with pytest.raises(ValueError, match="metadata"):
        security.codeql_findings(document)
