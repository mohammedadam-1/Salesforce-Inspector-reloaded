"""Phase G Engineering Intelligence Validation Tests."""
from sfir_backend.application.use_cases.ai.code_intelligence import CodeIntelligenceEngine


def test_code_intelligence_apex():
    ci = CodeIntelligenceEngine()
    code = """public without sharing class X {
    List<Account> get() { return [SELECT Id FROM Account]; }
    void save() { update new Account(); }
}"""
    result = ci.analyze_apex(code)
    assert result["sharing_declaration"] == "without sharing"
    assert len(result["soql_queries"]) == 1
    assert len(result["dml_operations"]) == 1
    assert result["total_lines"] in (3, 4, 5)
    assert isinstance(result["complexity_score"]["score"], float)
    for f in result["security_findings"]:
        print(f"  Security: [{f['severity']}] {f['finding']}")
    for g in result["governor_limit_concerns"]:
        print(f"  Governor: [{g['severity']}] {g['finding']}")
    assert "no sharing declaration" not in (
        str(result["security_findings"]).lower()
    )
    print("  PASSED: Apex analysis correct")


def test_code_intelligence_soql_in_loop():
    ci = CodeIntelligenceEngine()
    code = """void loop() {
    for (Account a : accounts) {
        Contact c = [SELECT Id FROM Contact WHERE AccountId = :a.Id];
    }
}"""
    result = ci.analyze_apex(code)
    concerns = result["governor_limit_concerns"]
    has_loop_concern = any("SOQL inside" in c["finding"] for c in concerns)
    assert has_loop_concern, f"Expected SOQL-in-loop concern, got: {concerns}"
    print("  PASSED: SOQL-in-loop detection correct")


def test_code_intelligence_security():
    ci = CodeIntelligenceEngine()
    code = """public class Insecure {
    List<Account> get() {
        return Database.query('SELECT Id FROM Account');
    }
}"""
    result = ci.analyze_apex(code)
    findings = result["security_findings"]
    has_sharing = any("sharing" in f["finding"].lower() for f in findings)
    assert has_sharing, f"Expected sharing warning, got: {findings}"
    print("  PASSED: Security analysis correct")


def test_code_intelligence_lwc():
    ci = CodeIntelligenceEngine()
    js = """import { LightningElement, api, wire } from "lwc";
import getRecs from "@salesforce/apex/Ctrl.getRecords";
export default class C extends LightningElement {
    @api recordId;
    @wire(getRecs, { id: "$recordId" })
    wired(result) {}
    connectedCallback() {}
}"""
    html = """<template>
    <div if:true={data}><c-child></c-child></div>
</template>"""
    result = ci.analyze_lwc(js, html)
    assert len(result["js"]["api_properties"]) == 1
    assert result["js"]["lifecycle_hooks"]["connectedCallback"]
    assert "c-child" in result["html"]["child_components"]
    print("  PASSED: LWC analysis correct")


def test_code_intelligence_flow():
    ci = CodeIntelligenceEngine()
    result = ci.analyze_flow_logic({
        "elements": [
            {"type": "Decision", "conditionLogic": "formula"},
            {"type": "RecordCreate"},
            {"type": "Subflow"},
            {"type": "Loop"},
            {"type": "Assignment"},
        ],
    })
    assert result["decision_count"] == 1
    assert result["record_operation_count"] == 1
    assert result["subflow_count"] == 1
    assert result["loop_count"] == 1
    print("  PASSED: Flow logic analysis correct")


def test_code_intelligence_governor_estimate():
    ci = CodeIntelligenceEngine()
    code = """void go() {
    List<Account> accts = [SELECT Id FROM Account];
    List<Contact> contacts = [SELECT Id FROM Contact];
    insert accts;
    update contacts;
    delete accts;
}"""
    result = ci.estimate_governor_usage(code)
    assert result["soql_queries"] == 2
    assert result["dml_statements"] == 3
    print("  PASSED: Governor estimate correct")


def test_code_intelligence_soql_optimization():
    ci = CodeIntelligenceEngine()
    code = """void go() {
    List<Account> accts = [SELECT Id, Name FROM Account];
}"""
    findings = ci.analyze_soql_optimization(code)
    has_limit_issue = any("LIMIT" in str(f.get("issues", [])) for f in findings)
    assert has_limit_issue, f"Expected LIMIT warning, got: {findings}"
    print("  PASSED: SOQL optimization analysis correct")


def test_documentation_generator_formatting():
    from sfir_backend.application.use_cases.ai.documentation_generator import (
        DocumentationGenerator,
    )

    text = DocumentationGenerator._build_component_markdown(
        None, "ApexClass", "AccountHelper",
        {"description": "Helper class for Account", "method_count": 5, "line_count": 120},
        {"upstream": [], "downstream": [
            {"type": "Flow", "name": "AccountFlow"},
            {"type": "ApexClass", "name": "AccountController"},
        ]},
    )
    assert "# ApexClass: AccountHelper" in text
    assert "AccountFlow" in text
    assert "AccountController" in text
    print("  PASSED: Component documentation format correct")


def test_documentation_field_markdown():
    from sfir_backend.application.use_cases.ai.documentation_generator import (
        DocumentationGenerator,
    )

    text = DocumentationGenerator._build_field_markdown(
        None, "Account", "Industry__c",
        {"field_type": "Picklist", "is_required": False, "picklist_values": ["A", "B", "C"]},
        [{"component_type": "ApexClass", "component_name": "AccountHelper",
          "reference_type": "direct_reference"}],
    )
    assert "# Field: Account.Industry__c" in text
    assert "Picklist" in text
    assert "ApexClass" in text
    print("  PASSED: Field documentation format correct")


def test_documentation_api_markdown():
    from sfir_backend.application.use_cases.ai.documentation_generator import (
        DocumentationGenerator,
    )

    text = DocumentationGenerator._build_api_markdown(
        None, "AccountService",
        {"type": "ApexClass", "line_count": 200, "method_count": 10,
         "methods": ["getById", "updateRecord"],
         "extends": [], "implements": ["Queueable"],
         "classes_used": ["Database"], "objects_referenced": ["Account"],
         "used_by": ["Flow:OppFlow"]},
        [{"object": "Account", "type": "SOQL"}],
    )
    assert "# Apex Class: AccountService" in text
    assert "Queueable" in text
    assert "getById" in text
    print("  PASSED: API documentation format correct")


def test_documentation_architecture_markdown():
    from sfir_backend.application.use_cases.ai.documentation_generator import (
        DocumentationGenerator,
    )

    text = DocumentationGenerator._build_architecture_overview(
        None,
        {"node_count": 250, "edge_count": 500, "cycles": 3,
         "component_types": {"ApexClass": 80, "CustomObject": 40, "Flow": 30}},
        [["A->B->C->A"]],
    )
    assert "# Architecture Overview" in text
    assert "250" in text
    assert "500" in text
    assert "80" in text
    print("  PASSED: Architecture documentation format correct")


if __name__ == "__main__":
    import sys
    tests = [
        ("Apex analysis", test_code_intelligence_apex),
        ("SOQL in loop detection", test_code_intelligence_soql_in_loop),
        ("Security analysis", test_code_intelligence_security),
        ("LWC analysis", test_code_intelligence_lwc),
        ("Flow logic analysis", test_code_intelligence_flow),
        ("Governor limit estimation", test_code_intelligence_governor_estimate),
        ("SOQL optimization", test_code_intelligence_soql_optimization),
        ("Component doc formatting", test_documentation_generator_formatting),
        ("Field doc formatting", test_documentation_field_markdown),
        ("API doc formatting", test_documentation_api_markdown),
        ("Architecture doc formatting", test_documentation_architecture_markdown),
    ]

    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK: {name}")
        except Exception as e:
            print(f"  FAIL: {name}: {e}")
            failures += 1

    if failures:
        print(f"\n{len(tests) - failures}/{len(tests)} passed, {failures} failed")
        sys.exit(1)
    else:
        print(f"\nAll {len(tests)} Phase G validation tests PASSED")
