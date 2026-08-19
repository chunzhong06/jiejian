# =============================================================================
# 统一报告纯投影
#
# 定位
# canonical Report 到 JSON、HTML、SARIF 与 JUnit 的无副作用格式投影边界。
#
# 职责
# 保持字段语义一致｜转义用户可见文本｜生成确定性格式字节
#
# 边界
# 只消费已校验 Report，不读取 publication、数据库或扫描结果，也不反向参与判定。
#
# 调用链
# ReportStore → render_json/html/sarif/junit → report publication
# =============================================================================

from __future__ import annotations

import html
import json
from xml.sax.saxutils import escape as xml_escape

from product.protocols.report import ReportFinding, Report, canonical_sha256


def render_json(report: Report) -> bytes:
    """输出唯一语义真源的确定性 UTF-8 JSON。"""

    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def render_html(report: Report) -> bytes:
    """生成供人阅读的转义 HTML；不引入 canonical Report 之外的结论。"""

    rows = []
    for finding in (*report.runtime.findings, *(item for artifact in report.artifacts for item in artifact.findings)):
        rows.append(
            "<tr>"
            f"<td>{html.escape(finding.finding_id)}</td>"
            f"<td>{html.escape(finding.source_type)}</td>"
            f"<td>{html.escape(finding.verdict)}</td>"
            f"<td>{html.escape(finding.severity)}</td>"
            f"<td>{html.escape(finding.message or '')}</td>"
            "</tr>"
        )
    if not rows:
        rows.append("<tr><td colspan=\"5\">未发现已发布 Finding</td></tr>")
    artifact_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item.artifact_id)}</td>"
        f"<td>{html.escape(item.status)}</td>"
        f"<td>{html.escape(item.verdict)}</td>"
        f"<td>{html.escape(item.error_code or '')}</td>"
        f"<td>{len(item.findings)}</td>"
        "</tr>"
        for item in report.artifacts
    ) or "<tr><td colspan=\"5\">NO_ARTIFACT_RESULT</td></tr>"
    gate_reasons = "".join(
        f"<li>{html.escape(item.get('code', ''))}</li>" for item in report.gate.reasons
    ) or "<li>无</li>"
    limitations = "".join(f"<li>{html.escape(item)}</li>" for item in report.limitations) or "<li>无</li>"
    document = (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<title>界鉴统一报告</title></head><body>"
        f"<h1>统一报告 {html.escape(report.report_id)}</h1>"
        f"<p>Run: {html.escape(report.run_id)}；GateResult: {html.escape(report.gate_result_id)}；"
        f"决策: {html.escape(report.gate.decision)}</p>"
        "<h2>Finding</h2><table><thead><tr><th>ID</th><th>来源</th><th>结论</th><th>严重度</th><th>消息</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table><h2>Artifact</h2><table><thead><tr><th>ID</th><th>状态</th><th>结论</th><th>错误</th><th>风险数量</th></tr></thead><tbody>"
        + artifact_rows
        + "</tbody></table><h2>Gate 原因</h2><ul>"
        + gate_reasons
        + "</ul><h2>限制与不可确认信息</h2><ul>"
        + limitations
        + "</ul></body></html>"
    )
    return document.encode("utf-8")


def render_sarif(report: Report) -> bytes:
    """把既有 Finding 投影为 SARIF result；缺失事实不会被补写为通过。"""

    results = []
    for finding in _findings(report):
        result = {
            "ruleId": finding.rule_id or finding.category or finding.finding_id,
            "level": _sarif_level(finding),
            "message": {"text": finding.message or finding.verdict},
            "properties": {
                "finding_id": finding.finding_id,
                "source_type": finding.source_type,
                "evidence_refs": [item.evidence_id for item in finding.evidence_refs],
                "gate_result_id": report.gate_result_id,
                "gate_decision": report.gate.decision,
            },
        }
        if finding.path:
            result["locations"] = [{"physicalLocation": {"artifactLocation": {"uri": finding.path}}}]
        results.append(result)
    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "界鉴统一报告", "informationUri": "https://example.invalid/jiejian"}},
            "results": results,
            "invocations": [{
                "executionSuccessful": not report.limitations,
                "toolExecutionNotifications": [
                    {"level": "warning", "message": {"text": item}, "properties": {"limitation": item}}
                    for item in report.limitations
                ],
            }],
            "properties": {"report_id": report.report_id, "gate_result_id": report.gate_result_id, "gate_decision": report.gate.decision},
        }],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def render_junit(report: Report) -> bytes:
    """把报告与 Gate 结果投影为 JUnit suite，保持阻断和不确定语义。"""

    cases = []
    for finding in _findings(report):
        name = xml_escape(finding.finding_id)
        evidence = xml_escape(",".join(item.evidence_id for item in finding.evidence_refs))
        message = xml_escape(finding.message or finding.verdict)
        if finding.verdict == "INCONCLUSIVE":
            body = f"<skipped message=\"{message}\"/>"
        elif finding.verdict == "VULNERABLE":
            body = f"<failure message=\"{message}\">evidence_refs={evidence}</failure>"
        else:
            body = ""
        cases.append(f"<testcase classname=\"{finding.source_type}\" name=\"{name}\">{body}</testcase>")
    for artifact in report.artifacts:
        name = xml_escape(artifact.artifact_id)
        status = xml_escape(f"{artifact.status}:{artifact.verdict}:{artifact.error_code or ''}")
        body = ""
        if artifact.status == "INCONCLUSIVE":
            body = f"<error message=\"{status}\"/>"
        elif artifact.verdict == "VULNERABLE":
            body = f"<failure message=\"{status}\"/>"
        cases.append(f"<testcase classname=\"ARTIFACT\" name=\"{name}\">{body}</testcase>")
    for limitation in report.limitations:
        token = xml_escape(limitation)
        cases.append(f"<testcase classname=\"LIMITATION\" name=\"{token}\"><error message=\"{token}\"/></testcase>")
    gate_message = xml_escape(";".join(item["code"] for item in report.gate.reasons) or report.gate.decision)
    gate_body = "" if report.gate.decision == "PASS" else f"<failure message=\"{gate_message}\"/>"
    cases.append(f"<testcase classname=\"GATE\" name=\"{xml_escape(report.gate_result_id)}\">{gate_body}</testcase>")
    error_count = len(report.limitations) + sum(1 for item in report.artifacts if item.status == "INCONCLUSIVE")
    document = f"<testsuite name=\"jiejian-report\" tests=\"{len(cases)}\" errors=\"{error_count}\" report_id=\"{xml_escape(report.report_id)}\">{''.join(cases)}</testsuite>"
    return document.encode("utf-8")


def render_format(report: Report, output_format: str) -> bytes:
    """按明确格式名分派纯投影；未知格式立即拒绝。"""

    if output_format == "json":
        return render_json(report)
    if output_format == "html":
        return render_html(report)
    if output_format == "sarif":
        return render_sarif(report)
    if output_format == "junit":
        return render_junit(report)
    raise ValueError("unsupported report format")


def _findings(report: Report) -> tuple[ReportFinding, ...]:
    return tuple(report.runtime.findings) + tuple(item for artifact in report.artifacts for item in artifact.findings)


def _sarif_level(finding: ReportFinding) -> str:
    if finding.verdict == "INCONCLUSIVE":
        return "warning"
    if finding.severity in {"critical", "high"}:
        return "error"
    return "note"
