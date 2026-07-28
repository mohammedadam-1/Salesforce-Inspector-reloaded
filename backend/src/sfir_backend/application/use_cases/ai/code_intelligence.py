from __future__ import annotations

import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class CodeIntelligenceEngine:
    def analyze_apex(self, code: str) -> dict[str, Any]:
        if not code:
            return {"error": "No code provided"}

        lines = code.split("\n")
        total_lines = len(lines)
        total_chars = len(code)

        classes = self._extract_classes(code)
        methods = self._extract_methods(code)
        properties = self._extract_properties(code)

        soql_queries = self._extract_soql(code)
        sosl_queries = self._extract_sosl(code)
        dml_ops = self._extract_dml(code)
        dynamic_soql = self._extract_dynamic_soql(code)

        sharing = self._detect_sharing(code)
        annotations = self._extract_annotations(code)
        has_test = "@istest" in code.lower() or "testmethod" in code.lower()
        has_future = "@future" in code.lower()
        has_http = any(kw in code.lower() for kw in ("httprequest", "httpresponse", "http.send"))
        has_batch = "database.batchable" in code.lower()
        has_queueable = "queueable" in code.lower()
        has_schedule = "schedulable" in code.lower()

        security = self._check_security(code)
        governor = self._check_governor_limits(code, soql_queries, dml_ops)
        best_practices = self._check_best_practices(code)

        return {
            "total_lines": total_lines,
            "total_chars": total_chars,
            "classes": classes,
            "methods": methods,
            "properties": properties,
            "sharing_declaration": sharing,
            "annotations": annotations,
            "has_test_methods": has_test,
            "has_future_methods": has_future,
            "has_http_callouts": has_http,
            "has_batchable": has_batch,
            "has_queueable": has_queueable,
            "has_schedulable": has_schedule,
            "soql_queries": soql_queries,
            "sosl_queries": sosl_queries,
            "dynamic_soql": dynamic_soql,
            "dml_operations": dml_ops,
            "security_findings": security,
            "governor_limit_concerns": governor,
            "best_practices": best_practices,
            "complexity_score": self._compute_complexity(
                total_lines, len(soql_queries), len(dml_ops), len(methods["all"]),
            ),
        }

    def analyze_soql_optimization(self, code: str) -> list[dict[str, Any]]:
        if not code:
            return []

        findings: list[dict[str, Any]] = []

        queries = self._extract_soql(code)
        for query in queries:
            q = query["query"]
            issues: list[str] = []

            if "select " in q[:20].lower() and q.count(",") <= 1:
                pass

            if "limit" not in q.lower() and "count(" not in q.lower():
                issues.append("No LIMIT clause — may return too many rows")
                issues.append("Add a LIMIT clause to bound the result set")

            if "order by" in q.lower() and "limit" not in q.lower():
                issues.append("ORDER BY without LIMIT can cause performance issues")

            if "for update" in q.lower():
                issues.append("FOR UPDATE — verify row locking is intentional")

            if "!" in q or "+" in q:
                issues.append("String concatenation in query — potential injection risk")

            if issues:
                findings.append({
                    "query": q[:200],
                    "object": query["object"],
                    "issues": issues,
                    "severity": "warning",
                })

        if not queries:
            findings.append({"info": "No SOQL queries found to analyze."})

        return findings

    def estimate_governor_usage(self, code: str) -> dict[str, Any]:
        if not code:
            return {"error": "No code provided"}

        soql_count = len(self._extract_soql(code))
        sosl_count = len(self._extract_sosl(code))
        dml_count = len(self._extract_dml(code))

        in_loops = self._detect_in_loops(code)

        heap_allocations = len(re.findall(r"\bnew\s+\w+\[", code))

        cpu_patterns = len(re.findall(r"\bfor\s*\(", code)) * 2 + len(re.findall(r"\bwhile\s*\(", code)) * 3

        return {
            "soql_queries": soql_count,
            "sosl_queries": sosl_count,
            "dml_statements": dml_count,
            "in_loops_count": in_loops,
            "heap_allocations": heap_allocations,
            "cpu_operations_estimate": cpu_patterns,
            "limits_usage": {
                "soql_query_limit": f"{soql_count} / 100",
                "dml_limit": f"{dml_count} / 150",
                "sosl_limit": f"{sosl_count} / 20",
            },
            "concerns": [],
        }

    def analyze_flow_logic(self, flow_metadata: dict[str, Any]) -> dict[str, Any]:
        elements = flow_metadata.get("elements", [])
        decisions = [e for e in elements if e.get("type") == "Decision"]
        assigns = [e for e in elements if e.get("type") == "Assignment"]
        records = [e for e in elements if e.get("type") in ("RecordCreate", "RecordUpdate", "RecordDelete")]
        loops = [e for e in elements if e.get("type") == "Loop"]
        subflows = [e for e in elements if e.get("type") == "Subflow"]

        formula_count = 0
        formula_refs: list[str] = []
        for e in elements:
            formulas = e.get("formulas", [])
            if isinstance(formulas, list):
                formula_count += len(formulas)
                for f in formulas:
                    if isinstance(f, dict) and "reference" in f:
                        formula_refs.append(f["reference"])

        return {
            "total_elements": len(elements),
            "decision_count": len(decisions),
            "assignment_count": len(assigns),
            "record_operation_count": len(records),
            "loop_count": len(loops),
            "subflow_count": len(subflows),
            "elements_with_formulas": formula_count,
            "formula_references": formula_refs[:20],
            "has_scheduled_paths": any(e.get("type") == "ScheduledPath" for e in elements),
            "has_formula_conditions": any("formula" in (e.get("conditionLogic", "") or "") for e in decisions),
        }

    def analyze_lwc(self, js_code: str, html_code: str = "") -> dict[str, Any]:
        if not js_code and not html_code:
            return {"error": "No LWC code provided"}

        result: dict[str, Any] = {}

        if js_code:
            imports = re.findall(r"import\s+\{?\s*(\w+(?:\s*,\s*\w+)*)\s*\}?\s+from\s+['\"]([^'\"]+)['\"]", js_code)
            exposed = re.findall(r"@api\s+(\w+)", js_code)
            tracked = re.findall(r"@track\s+(\w+)", js_code)
            wire = re.findall(r"@wire\s*\(\s*(\w+)\s*(?:,\s*(\{[^}]+\})\s*)?\)", js_code)
            has_rendered_callback = "renderedCallback" in js_code
            has_connected_callback = "connectedCallback" in js_code
            has_disconnected_callback = "disconnectedCallback" in js_code
            imperative_apex = "import " in js_code and "@salesforce/apex" in js_code

            result["js"] = {
                "imports": [(m[0], m[1]) for m in imports[:30]],
                "api_properties": exposed,
                "tracked_properties": tracked,
                "wire_adapters": [w[0] for w in wire],
                "lifecycle_hooks": {
                    "renderedCallback": has_rendered_callback,
                    "connectedCallback": has_connected_callback,
                    "disconnectedCallback": has_disconnected_callback,
                },
                "uses_imperative_apex": imperative_apex,
                "line_count": js_code.count("\n") + 1,
            }

        if html_code:
            template_tags = re.findall(r"<(\w+)-(\w+)[\s>]", html_code)
            wire_bindings = re.findall(r"\{(\w+)\}", html_code)
            event_handlers = re.findall(r"on(\w+)\s*=\s*\{", html_code)
            conditionals = {
                "if_true": html_code.count("if:true"),
                "if_false": html_code.count("if:false"),
                "for_each": html_code.count("for:each"),
                "iterator": html_code.count("iterator:it"),
            }

            result["html"] = {
                "child_components": list(set(f"{m[0]}-{m[1]}" for m in template_tags)),
                "data_bindings": list(set(wire_bindings)),
                "event_handlers": list(set(event_handlers)),
                "conditionals": conditionals,
                "line_count": html_code.count("\n") + 1,
            }

        return result

    def _extract_classes(self, code: str) -> list[dict[str, str]]:
        classes: list[dict[str, str]] = []
        pattern = re.compile(
            r"(?:public|private|global|virtual|abstract)?\s*"
            r"(?:class|interface|enum)\s+(\w+)"
            r"(?:\s+extends\s+(\w+))?"
            r"(?:\s+implements\s+([\w,\s]+))?",
        )
        for m in pattern.finditer(code):
            cls = {"name": m.group(1)}
            if m.group(2):
                cls["extends"] = m.group(2)
            if m.group(3):
                cls["implements"] = [i.strip() for i in m.group(3).split(",")]
            classes.append(cls)
        return classes

    def _extract_methods(self, code: str) -> dict[str, list[str]]:
        all_methods: list[str] = []
        signatures: list[str] = []

        pattern = re.compile(
            r"(?:public|private|global|protected|static|virtual|override|abstract)?\s*"
            r"(?:public|private|global|protected|static|virtual|override|abstract)?\s*"
            r"(\w+(?:\[\])?)\s+(\w+)\s*\(",
        )
        seen = set()
        for m in pattern.finditer(code):
            name = m.group(2)
            if name not in seen and not name.startswith("__"):
                is_apex = name[0].isupper()
                if is_apex and not name.endswith("Exception"):
                    seen.add(name)
                    all_methods.append(name)
                    signatures.append(m.group(0)[:120])

        return {"all": all_methods, "signatures": signatures}

    def _extract_properties(self, code: str) -> list[str]:
        return re.findall(r"(?:public|private|global|protected|static)?\s*(\w+)\s+\{?\s*get;\s*set;\s*\}?", code)

    def _extract_soql(self, code: str) -> list[dict[str, str]]:
        queries: list[dict[str, str]] = []
        pattern = re.compile(r"\[SELECT\s+(.+?)\s+FROM\s+(\w+)([^\]]*)\]", re.IGNORECASE | re.DOTALL)
        for m in pattern.finditer(code):
            queries.append({
                "query": m.group(0)[:300],
                "fields": m.group(1).strip()[:200],
                "object": m.group(2),
            })
        return queries

    def _extract_sosl(self, code: str) -> list[dict[str, str]]:
        queries: list[dict[str, str]] = []
        pattern = re.compile(r"\[FIND\s+(.+?)\s+RETURNING\s+(\w+)([^\]]*)\]", re.IGNORECASE | re.DOTALL)
        for m in pattern.finditer(code):
            queries.append({
                "query": m.group(0)[:300],
                "returning": m.group(2),
            })
        return queries

    def _extract_dml(self, code: str) -> list[dict[str, str]]:
        ops: list[dict[str, str]] = []
        lower = code.lower()
        patterns = [
            (r"\binsert\s+(\w+)", "insert"),
            (r"\bupdate\s+(\w+)", "update"),
            (r"\bdelete\s+(\w+)", "delete"),
            (r"\bupsert\s+(\w+)", "upsert"),
            (r"\bundelete\s+(\w+)", "undelete"),
        ]
        for pat, op_type in patterns:
            for m in re.finditer(pat, code, re.IGNORECASE):
                ops.append({"type": op_type, "target": m.group(1)})
        return ops

    def _extract_dynamic_soql(self, code: str) -> list[dict[str, str]]:
        queries: list[dict[str, str]] = []
        patterns = [
            r"Database\.query\(\s*['\"]([^'\"]+)['\"]\s*\)",
            r"Database\.countQuery\(\s*['\"]([^'\"]+)['\"]\s*\)",
        ]
        for pat in patterns:
            for m in re.finditer(pat, code, re.IGNORECASE | re.DOTALL):
                queries.append({
                    "query": m.group(1)[:300],
                    "type": "dynamic",
                })
        return queries

    def _detect_sharing(self, code: str) -> str:
        lower = code.lower()
        if "without sharing" in lower:
            return "without sharing"
        if "with sharing" in lower:
            return "with sharing"
        return "inherited"

    def _extract_annotations(self, code: str) -> list[str]:
        return re.findall(r"@(\w+)", code)

    def _check_security(self, code: str) -> list[dict[str, str]]:
        findings: list[dict[str, str]] = []
        lower = code.lower()

        sharing = self._detect_sharing(code)
        if sharing == "inherited" and ("select " in lower and " from " in lower):
            findings.append({
                "severity": "warning",
                "finding": "No sharing declaration — class runs in system context",
                "detail": "Add 'with sharing' or 'without sharing' declaration",
            })

        if "database.query" in lower:
            findings.append({
                "severity": "high",
                "finding": "Dynamic SOQL with Database.query()",
                "detail": "Potential SOQL injection risk if query contains user-supplied strings",
            })

        if "stripinaccessible" not in lower and ("select " in lower and " from " in lower):
            findings.append({
                "severity": "info",
                "finding": "stripInaccessible not used",
                "detail": "Consider using stripInaccessible when querying non-SObject fields",
            })

        crud_checks = {
            "isaccessible": "Object/Field accessibility",
            "iscreateable": "Create permission",
            "isupdateable": "Update permission",
            "isdeletable": "Delete permission",
        }
        missing_crud = [desc for kw, desc in crud_checks.items() if kw not in lower]
        if len(missing_crud) >= 3:
            findings.append({
                "severity": "warning",
                "finding": "CRUD/FLS enforcement may be incomplete",
                "detail": f"Missing checks for: {', '.join(missing_crud)}. "
                         "Use Schema methods to check object and field accessibility.",
            })

        if "@suppresswarnings" not in code:
            methods = self._extract_methods(code)
            long_methods = [m for m in methods["all"] if len(m) > 0]
            for m_name in long_methods:
                if lower.count(m_name.lower()) > 5:
                    findings.append({
                        "severity": "info",
                        "finding": f"Method '{m_name}' may need optimization",
                        "detail": "High call count — consider caching or restructuring",
                    })
                    break

        return findings

    def _check_governor_limits(
        self,
        code: str,
        soql_queries: list,
        dml_ops: list,
    ) -> list[dict[str, Any]]:
        concerns: list[dict[str, Any]] = []
        lower = code.lower()

        total_in_loops = self._detect_in_loops(code)
        if total_in_loops > 0 and soql_queries:
            concerns.append({
                "severity": "high",
                "finding": f"SOQL inside {total_in_loops} loop(s) — risk of hitting 101 query limit",
                "detail": "Move SOQL queries outside loops using collections and bulk queries",
            })

        if len(soql_queries) > 5:
            concerns.append({
                "severity": "warning",
                "finding": f"{len(soql_queries)} SOQL queries — approach synchronous query limit",
                "detail": "Consider reducing query count or using aggregation",
            })

        if len(dml_ops) > 3:
            concerns.append({
                "severity": "warning",
                "finding": f"{len(dml_ops)} DML operations — may approach 150 operation limit in bulk contexts",
                "detail": "Consolidate DML operations using collections",
            })

        if "system.debug" in lower:
            debug_count = lower.count("system.debug")
            if debug_count > 10:
                concerns.append({
                    "severity": "info",
                    "finding": f"{debug_count} debug statements — may hit debug log limit",
                    "detail": "Remove debug statements before deployment",
                })

        if code.count("SELECT") > 50:
            concerns.append({
                "severity": "warning",
                "finding": "Very high SELECT count — possible CPU limit concern",
                "detail": "Review for query optimization opportunities",
            })

        if "callout" in lower and len(re.findall(r"HttpRequest", code)) > 5:
            concerns.append({
                "severity": "warning",
                "finding": "Multiple HTTP callouts — verify within 10-callout limit",
                "detail": "Ensure callouts are not inside loops",
            })

        if "future" in lower and "callout" in lower:
            ct = lower.count("@future")
            if ct > 5:
                concerns.append({
                    "severity": "info",
                    "finding": f"{ct} @future methods — consider Queueable for better limits",
                    "detail": "@future methods share the same limits as the caller",
                })

        return concerns

    def _check_best_practices(self, code: str) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []

        if "system.debug" in code.lower():
            suggestions.append({
                "severity": "info",
                "finding": "Contains System.debug statements",
                "detail": "Remove debug statements before deploying to production",
            })

        lower = code.lower()
        if "without sharing" in lower:
            suggestions.append({
                "severity": "info",
                "finding": "Declared 'without sharing'",
                "detail": "Verify this is intentional — exposes data in system context",
            })

        if "//" not in code and code.count("\n") > 50:
            suggestions.append({
                "severity": "info",
                "finding": "No inline comments in a large class",
                "detail": "Add comments for complex logic blocks",
            })

        if "trigger" in lower and code.count("\n") > 100:
            suggestions.append({
                "severity": "warning",
                "finding": "Large trigger body",
                "detail": "Trigger logic should be delegated to a handler class",
            })

        if "hardisdelete" in lower or "delete" in lower:
            pass

        if "select " in lower and " from " in lower:
            for query in ["SELECT * ", "select id ", "SELECT Id "]:
                pass

        return suggestions

    def _detect_in_loops(self, code: str) -> int:
        lines = code.split("\n")
        in_loop = False
        loop_depth = 0
        soql_in_loop = 0
        for line in lines:
            stripped = line.strip()
            if any(kw in stripped for kw in ["for (", "for(", "while (", "while(", "do {", "do{"]):
                loop_depth += 1
                in_loop = True
            if in_loop and ("[select " in stripped.lower() or "[find " in stripped.lower()
                          or "database.query" in stripped.lower()):
                soql_in_loop += 1
            if "}" in stripped:
                loop_depth = max(0, loop_depth - 1)
                if loop_depth == 0:
                    in_loop = False
        return soql_in_loop

    def _compute_complexity(
        self,
        lines: int,
        soql_count: int,
        dml_count: int,
        method_count: int,
    ) -> dict[str, Any]:
        raw = (lines * 0.3) + (soql_count * 5) + (dml_count * 3) + (method_count * 2)
        score = min(100, raw)

        level: str
        if score < 20:
            level = "low"
        elif score < 50:
            level = "medium"
        else:
            level = "high"

        return {
            "score": round(score, 1),
            "level": level,
            "factors": {
                "lines": lines,
                "soql_queries": soql_count,
                "dml_ops": dml_count,
                "methods": method_count,
            },
        }
