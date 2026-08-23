# =============================================================================
# 统一报告纯投影
#
# 定位
#   只把已校验的 ReportDocument 投影为 JSON、HTML、SARIF 与 JUnit。
#
# 边界
#   不读取数据库或文件，不补写 Finding，不参与 Verdict/实验判定。
# =============================================================================

from __future__ import annotations

import html
import json
from xml.sax.saxutils import escape as xml_escape

from product.protocols.report import BaseRunReport, GateRunReport, ReportDocument, ReportFinding


def render_json(report: ReportDocument) -> bytes:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def render_html(report: ReportDocument) -> bytes:
    rows = []
    for finding in _findings(report):
        rows.append(
            "<tr>"
            f"<td>{html.escape(finding.finding_id)}</td>"
            f"<td>{html.escape(finding.source_type)}</td>"
            f"<td>{html.escape(finding.verdict)}</td>"
            f"<td>{html.escape(finding.severity)}</td>"
            f"<td>{html.escape(finding.message or '')}</td></tr>"
        )
    finding_rows = "".join(rows) or '<tr><td colspan="5">未发现已发布 Finding</td></tr>'
    summary = report.artifact_summary
    artifact_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item.artifact_id)}</td><td>{html.escape(item.status)}</td>"
        f"<td>{html.escape(item.verdict)}</td><td>{html.escape(item.error_code or '')}</td>"
        f"<td>{len(item.findings)}</td></tr>"
        for item in summary.results
    ) or '<tr><td colspan="5">未请求产物检查</td></tr>'
    limitation_rows = "".join(f"<li>{html.escape(item)}</li>" for item in report.limitations) or "<li>无</li>"
    gate_text = ""
    if isinstance(report, GateRunReport):
        gate_text = (
            f"<h2>Gate</h2><p>GateResult: {html.escape(report.gate_result_id)}；"
            f"决策: {html.escape(report.gate.decision)}</p>"
        )
    document = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>界鉴报告 {html.escape(report.report_id)}</title></head><body>"
        f"<h1>{html.escape(report.report_type)} Report {html.escape(report.report_id)}</h1>"
        f"<p>Run: {html.escape(report.run_id)}；Artifact: {html.escape(summary.status.value)}</p>"
        + gate_text
        + '<h2>Finding</h2><table><thead><tr><th>ID</th><th>来源</th><th>结论</th><th>严重度</th><th>消息</th></tr></thead><tbody>'
        + finding_rows
        + '</tbody></table><h2>Artifact</h2><table><thead><tr><th>ID</th><th>状态</th><th>结论</th><th>错误</th><th>风险数量</th></tr></thead><tbody>'
        + artifact_rows
        + f"</tbody></table><h2>限制与不可确认信息</h2><ul>{limitation_rows}</ul></body></html>"
    )
    return document.encode("utf-8")


def render_sarif(report: ReportDocument) -> bytes:
    results = []
    for finding in _findings(report):
        item = {
            "ruleId": finding.rule_id or finding.category or finding.finding_id,
            "level": _sarif_level(finding),
            "message": {"text": finding.message or finding.verdict},
            "properties": {
                "finding_id": finding.finding_id,
                "source_type": finding.source_type,
                "evidence_refs": [ref.evidence_id for ref in finding.evidence_refs],
            },
        }
        if isinstance(report, GateRunReport):
            item["properties"].update({"gate_result_id": report.gate_result_id, "gate_decision": report.gate.decision})
        if finding.path:
            item["locations"] = [{"physicalLocation": {"artifactLocation": {"uri": finding.path}}}]
        results.append(item)
    notifications = [
        {"level": "warning", "message": {"text": limitation}, "properties": {"limitation": limitation}}
        for limitation in report.limitations
    ]
    properties = {"report_id": report.report_id, "report_type": report.report_type}
    if isinstance(report, GateRunReport):
        properties.update({"gate_result_id": report.gate_result_id, "gate_decision": report.gate.decision})
    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "界鉴统一报告", "informationUri": "https://example.invalid/jiejian"}},
            "results": results,
            "invocations": [{"executionSuccessful": not bool(notifications), "toolExecutionNotifications": notifications}],
            "properties": properties,
        }],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def render_junit(report: ReportDocument) -> bytes:
    cases = []
    for finding in _findings(report):
        name = xml_escape(finding.finding_id)
        message = xml_escape(finding.message or finding.verdict)
        evidence = xml_escape(",".join(ref.evidence_id for ref in finding.evidence_refs))
        if finding.verdict == "INCONCLUSIVE":
            body = f'<skipped message="{message}"/>'
        elif finding.verdict == "VULNERABLE":
            body = f'<failure message="{message}">evidence_refs={evidence}</failure>'
        else:
            body = ""
        cases.append(f'<testcase classname="{finding.source_type}" name="{name}">{body}</testcase>')
    for item in report.artifact_summary.results:
        body = ""
        if item.status == "INCONCLUSIVE":
            body = f'<error message="{xml_escape(item.error_code or "ARTIFACT_INCONCLUSIVE")}"/>'
        elif item.verdict == "VULNERABLE":
            body = f'<failure message="{xml_escape(item.artifact_id)}"/>'
        cases.append(f'<testcase classname="ARTIFACT" name="{xml_escape(item.artifact_id)}">{body}</testcase>')
    for limitation in report.limitations:
        token = xml_escape(limitation)
        cases.append(f'<testcase classname="LIMITATION" name="{token}"><error message="{token}"/></testcase>')
    if isinstance(report, GateRunReport):
        gate_body = "" if report.gate.decision == "PASS" else f'<failure message="{xml_escape(report.gate.decision)}"/>'
        cases.append(f'<testcase classname="GATE" name="{xml_escape(report.gate_result_id)}">{gate_body}</testcase>')
    errors = len(report.limitations) + sum(item.status == "INCONCLUSIVE" for item in report.artifact_summary.results)
    document = f'<testsuite name="jiejian-report" tests="{len(cases)}" errors="{errors}" report_id="{xml_escape(report.report_id)}">{"".join(cases)}</testsuite>'
    return document.encode("utf-8")


def render_format(report: ReportDocument, output_format: str) -> bytes:
    return {
        "json": render_json,
        "html": render_html,
        "sarif": render_sarif,
        "junit": render_junit,
    }.get(output_format, _unsupported)(report)


def _findings(report: ReportDocument) -> tuple[ReportFinding, ...]:
    return tuple(report.runtime.findings) + tuple(item for artifact in report.artifact_summary.results for item in artifact.findings)


def _sarif_level(finding: ReportFinding) -> str:
    if finding.verdict == "INCONCLUSIVE":
        return "warning"
    if finding.severity in {"critical", "high"}:
        return "error"
    return "note"


def _unsupported(_: ReportDocument) -> bytes:
    raise ValueError("unsupported report format")
