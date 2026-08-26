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
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

from product.protocols.report import (
    BaseRunReport,
    GateRunReport,
    ReportDocument,
    ReportFinding,
    ReportPresentationIssue,
)


_REPORT_CSS = """
:root{color-scheme:light;--ink:#172033;--muted:#667085;--line:#dfe5ef;--surface:#fff;--soft:#f6f8fb;--brand:#3157d5;--brand-dark:#101d42;--danger:#c83245;--danger-soft:#fff1f3;--success:#178753;--success-soft:#ecfdf3;--warning:#b66a09;--warning-soft:#fff8e7}
*{box-sizing:border-box}
body{font-family:Inter,"Segoe UI","Microsoft YaHei",system-ui,sans-serif;line-height:1.65;margin:0;background:#edf1f7;color:var(--ink)}
main{max-width:1120px;margin:0 auto;padding:48px 28px 64px}
.report-header{background:linear-gradient(135deg,#101d42,#1a3477);border-radius:20px;color:#fff;padding:34px 38px;box-shadow:0 18px 50px rgba(16,29,66,.18)}
.brand-row{align-items:center;display:flex;gap:12px;margin-bottom:24px}
.brand-mark{background:#fff;border-radius:9px;color:var(--brand-dark);flex:0 0 auto;font-size:18px;font-weight:800;letter-spacing:.08em;padding:5px 10px;white-space:nowrap}
.eyebrow{color:#aebff4;font-size:13px;font-weight:700;letter-spacing:.14em;text-transform:uppercase}
h1{font-size:32px;line-height:1.25;margin:0 0 12px}
.report-header p{color:#d9e2ff;margin:0;max-width:720px}
.header-meta{display:flex;flex-wrap:wrap;gap:10px 24px;margin-top:26px;color:#d9e2ff;font-size:14px;overflow-wrap:anywhere}
.header-meta strong{color:#fff}
section,.technical{background:var(--surface);border:1px solid var(--line);border-radius:16px;margin:20px 0;padding:26px 28px;box-shadow:0 8px 28px rgba(16,29,66,.05)}
h2{font-size:21px;line-height:1.4;margin:0 0 18px;color:#14213d}
h3{line-height:1.45;margin:0}
p{margin:10px 0}
.verdict-panel{border-left:6px solid var(--brand);padding-left:24px}
.verdict-panel.verdict-block{background:var(--danger-soft);border-color:#f3bdc5;border-left-color:var(--danger)}
.verdict-panel.verdict-pass{background:var(--success-soft);border-color:#b7e4cc;border-left-color:var(--success)}
.verdict-panel.verdict-inconclusive{background:var(--warning-soft);border-color:#eed6a7;border-left-color:var(--warning)}
.verdict-topline{align-items:center;display:flex;flex-wrap:wrap;gap:12px;margin-bottom:10px}
.verdict-pill,.severity-pill{border-radius:999px;display:inline-flex;font-size:12px;font-weight:800;letter-spacing:.04em;padding:4px 10px}
.verdict-block .verdict-pill{background:var(--danger);color:#fff}
.verdict-pass .verdict-pill{background:var(--success);color:#fff}
.verdict-inconclusive .verdict-pill{background:var(--warning);color:#fff}
.verdict-unknown .verdict-pill{background:#667085;color:#fff}
.scope{color:#475467;margin-bottom:0}
.summary{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}
.summary-item{background:var(--soft);border:1px solid #e7ebf2;border-radius:12px;display:grid;gap:3px;padding:16px}
.summary-item span{color:var(--muted);font-size:13px}
.summary-item strong{font-size:28px;line-height:1.25;color:#14213d}
.summary-item.problem strong{color:var(--danger)}
.issue-list{display:grid;gap:18px}
.issue-card{border:1px solid #e0e5ed;border-radius:14px;overflow:hidden}
.issue-card-heading{align-items:flex-start;background:#fbfcfe;border-bottom:1px solid #e8ecf2;display:flex;gap:16px;justify-content:space-between;padding:20px 22px}
.issue-card-heading h3{font-size:18px}
.issue-card-heading p{color:var(--muted);font-size:13px;margin:4px 0 0}
.severity-pill{flex:0 0 auto}
.severity-critical,.severity-high{background:#ffe4e8;color:#9f1f35}
.severity-medium{background:#fff0c2;color:#85510a}
.severity-low,.severity-info{background:#e8efff;color:#294ba8}
.issue-body{display:grid;gap:18px;padding:22px}
.issue-meta{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.meta-item{background:var(--soft);border-radius:10px;padding:11px 13px;min-width:0}
.meta-item span,.result-box span,.conclusion-box span{color:var(--muted);display:block;font-size:12px;font-weight:700;margin-bottom:3px}
.meta-item strong{overflow-wrap:anywhere}
.result-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.result-box{border:1px solid #dde3ec;border-radius:11px;padding:15px}
.result-box.actual{background:#fff8f8;border-color:#f1c6cc}
.result-box p{margin:0}
.conclusion-box{background:#fff4f5;border-left:4px solid var(--danger);border-radius:10px;padding:15px 17px}
.conclusion-box strong{display:block;font-size:16px;margin-bottom:5px}
.conclusion-box p{color:#5f2932;margin:0}
.empty-state{background:var(--soft);border:1px dashed #cbd3df;border-radius:12px;color:var(--muted);padding:28px;text-align:center}
.coverage-note{background:var(--soft);border-radius:10px;padding:14px 16px}
ul{margin:8px 0;padding-left:22px}
li+li{margin-top:6px}
.gate-note{background:#f5f7ff;border-radius:10px;padding:14px 16px}
.technical{padding:0;overflow:hidden}
.technical summary{cursor:pointer;font-size:19px;font-weight:700;padding:22px 28px;list-style-position:inside}
.technical[open] summary{border-bottom:1px solid var(--line)}
.technical-body{padding:4px 28px 28px}
.technical-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:18px 0}
.technical-item{background:var(--soft);border-radius:9px;padding:11px 13px;overflow-wrap:anywhere}
.technical-item span{color:var(--muted);display:block;font-size:12px;font-weight:700}
.table-wrap{overflow-x:auto}
table{border-collapse:separate;border-spacing:0;width:100%;min-width:680px}
th,td{border-bottom:1px solid #e5e9f0;padding:11px 12px;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{background:#f5f7fa;color:#475467;font-size:12px;letter-spacing:.02em}
code{font-family:"Cascadia Code",Consolas,monospace;font-size:12px;overflow-wrap:anywhere}
.muted{color:var(--muted)}
@media(max-width:860px){main{padding:24px 16px 40px}.report-header{padding:26px 22px}.summary{grid-template-columns:repeat(2,minmax(0,1fr))}.issue-meta{grid-template-columns:repeat(2,minmax(0,1fr))}.technical-grid{grid-template-columns:1fr}}
@media(max-width:560px){h1{font-size:26px}section{padding:21px 18px}.summary,.issue-meta,.result-grid{grid-template-columns:1fr}.issue-card-heading{align-items:stretch;flex-direction:column}.severity-pill{align-self:flex-start}.technical summary{padding:20px}.technical-body{padding:4px 18px 20px}}
@media print{body{background:#fff}main{max-width:none;padding:0}.report-header,section,.technical{box-shadow:none;break-inside:avoid}.technical:not([open])>.technical-body{display:block}.technical summary{display:none}}
""".strip()


def render_json(report: ReportDocument) -> bytes:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def render_html(report: ReportDocument) -> bytes:
    presentation = report.presentation
    summary = report.artifact_summary
    issue_cards = _issue_cards(presentation.issues)
    artifact_rows = "".join(
        "<tr>"
        f"<td>{_esc(item.artifact_id)}</td><td>{_esc(item.status)}</td>"
        f"<td>{_esc(item.verdict)}</td><td>{_esc(item.error_code or '')}</td>"
        f"<td>{_esc(len(item.findings))}</td></tr>"
        for item in summary.results
    ) or '<tr><td colspan="5">当前没有请求产物检查。</td></tr>'
    evidence_refs = tuple(sorted(
        {ref.evidence_id for ref in report.runtime.evidence_refs}
        | {
            ref.evidence_id
            for artifact in summary.results
            for ref in artifact.evidence_refs
        }
    ))
    finding_rows = "".join(
        "<tr>"
        f"<td>{_esc(finding.finding_id)}</td><td>{_esc(finding.source_type)}</td>"
        f"<td>{_esc(finding.verdict)}</td><td>{_esc(finding.severity)}</td>"
        f"<td>{_esc(','.join(ref.evidence_id for ref in finding.evidence_refs))}</td></tr>"
        for finding in _findings(report)
    ) or '<tr><td colspan="5">当前没有已发布证据对应的问题记录。</td></tr>'
    business_limitations = _list_items(
        (presentation.execution_problem,) if presentation.execution_problem else (),
        presentation.limitations,
        empty="当前没有额外业务限制或证据不足说明。",
    )
    technical_limitations = _list_items(
        (),
        report.limitations,
        empty="当前没有报告技术限制。",
    )
    reason_codes = tuple(sorted({
        *summary.reason_codes,
        *report.runtime.execution_errors,
        *(reason for observer in report.runtime.observer_statuses for reason in observer.reason_codes),
    }))
    verdict_class = _verdict_class(presentation.verdict)
    verdict_label = _verdict_label(presentation.verdict)
    gate_text = ""
    if isinstance(report, GateRunReport):
        gate_reasons = _list_items(
            (),
            tuple(
                json.dumps(reason, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                for reason in report.gate.reasons
            ),
            empty="Gate 没有附加原因。",
        )
        gate_text = (
            '<section><h2>发布门禁</h2>'
            f"<p class=\"gate-note\">Gate decision：{_esc(report.gate.decision)}；"
            f"该决策不覆盖安全检查结论（{_esc(presentation.verdict or '未形成')}）。</p>"
            '<div class="technical-grid">'
            f'<div class="technical-item"><span>GateResult</span><code>{_esc(report.gate_result_id)}</code></div>'
            f'<div class="technical-item"><span>基线</span><code>{_esc(report.gate.baseline_id)}</code></div>'
            f'<div class="technical-item"><span>策略</span>{_esc(report.gate.policy_version)}</div>'
            f'<div class="technical-item"><span>评估时间</span>{_esc(_utc_time(report.gate.evaluated_at_us))}</div>'
            f'<div class="technical-item"><span>输入摘要</span><code>{_esc(report.gate.input_hash)}</code></div>'
            '</div>'
            f"<h3>Gate 原因</h3><ul>{gate_reasons}</ul></section>"
        )
    document = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>界鉴 · 权限安全检查报告</title>'
        f'<style>{_REPORT_CSS}</style>'
        '</head><body><main>'
        '<header class="report-header"><div class="brand-row"><span class="brand-mark">界鉴</span>'
        '<span class="eyebrow">Authorization Verification Report</span></div>'
        '<h1>权限安全检查报告</h1><p>表面 HTTP 响应不代表真实安全结果；本报告依据权限预期、真实执行与可信观察生成。</p>'
        '<div class="header-meta">'
        f'<span>项目 <strong>{_esc(presentation.project_name)}</strong></span>'
        f'<span>检查时间（UTC） <strong>{_esc(_utc_time(report.run.finished_at_us if report.run.finished_at_us is not None else report.run.created_at_us))}</strong></span>'
        f'<span>Run <strong>{_esc(report.run_id)}</strong></span></div></header>'
        f'<section class="verdict-panel verdict-{verdict_class}"><div class="verdict-topline">'
        f'<span class="verdict-pill">{_esc(verdict_label)}</span><h2>总体结论</h2></div>'
        f"<h3>{_esc(presentation.headline)}</h3><p class=\"scope\">{_esc(presentation.scope_statement)}</p></section>"
        '<section><h2>检查摘要</h2><div class="summary">'
        f'<div class="summary-item"><span>检查项</span><strong>{_esc(presentation.checked_count)}</strong></div>'
        f'<div class="summary-item"><span>符合预期</span><strong>{_esc(presentation.safe_count)}</strong></div>'
        f'<div class="summary-item problem"><span>权限问题</span><strong>{_esc(presentation.problem_count)}</strong></div>'
        f'<div class="summary-item"><span>证据不足</span><strong>{_esc(presentation.inconclusive_count)}</strong></div>'
        f'<div class="summary-item"><span>未覆盖</span><strong>{_esc(presentation.uncovered_count)}</strong></div>'
        '</div></section>'
        f'<section><h2>关键问题</h2><div class="issue-list">{issue_cards}</div></section>'
        '<section><h2>权限覆盖与未覆盖</h2>'
        f'<p class="coverage-note">已检查 <strong>{_esc(presentation.checked_count)}</strong> 项；仍有 <strong>{_esc(presentation.uncovered_count)}</strong> 项权限要求未覆盖。</p><p>{_esc(presentation.scope_statement)}</p></section>'
        f"<section><h2>限制与证据不足</h2><h3>业务限制</h3><ul>{business_limitations}</ul><h3>报告技术限制</h3><ul>{technical_limitations}</ul></section>"
        f"{gate_text}"
        '<details class="technical"><summary>技术附录</summary><div class="technical-body">'
        '<div class="technical-grid">'
        f'<div class="technical-item"><span>Report ID</span><code>{_esc(report.report_id)}</code></div>'
        f'<div class="technical-item"><span>Report type</span>{_esc(report.report_type)}</div>'
        f'<div class="technical-item"><span>Canonical hash</span><code>{_esc(report.canonical_sha256)}</code></div>'
        f'<div class="technical-item"><span>Run ID</span><code>{_esc(report.run_id)}</code></div>'
        f'<div class="technical-item"><span>Lifecycle</span>{_esc(report.run.lifecycle)}</div>'
        f'<div class="technical-item"><span>安全结论</span>安全结论：{_esc(report.runtime.verdict or "未形成")}</div>'
        f'<div class="technical-item"><span>Evidence refs</span><code>{_esc(",".join(evidence_refs) or "无")}</code></div>'
        f'<div class="technical-item"><span>Schema</span><code>report={_esc(report.versions.report_schema_version)}；runner={_esc(report.versions.runner_schema_version)}；evidence={_esc(report.versions.evidence_schema_version)}；observer={_esc(report.versions.observer_schema_version)}；artifact={_esc(report.versions.artifact_schema_version)}</code></div>'
        f'<div class="technical-item"><span>Ruleset</span><code>{_esc(",".join(report.versions.ruleset_versions) or "无")}</code></div>'
        f'<div class="technical-item"><span>Reason codes</span><code>{_esc(",".join(reason_codes) or "无")}</code></div>'
        '</div>'
        '<h3>已发布问题事实摘要</h3><div class="table-wrap"><table><thead><tr><th>ID</th><th>来源</th><th>结论</th><th>严重度</th><th>Evidence refs</th></tr></thead><tbody>'
        f"{finding_rows}</tbody></table></div>"
        '<h3>产物摘要</h3><div class="table-wrap"><table><thead><tr><th>ID</th><th>状态</th><th>结论</th><th>错误</th><th>问题数</th></tr></thead><tbody>'
        f"{artifact_rows}</tbody></table></div></div></details>"
        '</main></body></html>'
    )
    return document.encode("utf-8")


def _issue_cards(issues: tuple[ReportPresentationIssue, ...]) -> str:
    if not issues:
        return '<div class="empty-state">当前没有需要单独说明的关键问题。</div>'
    return "".join(
        '<article class="issue-card">'
        '<div class="issue-card-heading"><div>'
        f'<h3>{_esc(issue.title)}</h3><p>问题记录 {_esc(issue.finding_id)}</p></div>'
        f'<span class="severity-pill severity-{_severity_class(issue.severity)}">{_esc(_severity_label(issue.severity))}</span></div>'
        '<div class="issue-body"><div class="issue-meta">'
        f'<div class="meta-item"><span>权限组</span><strong>{_esc(issue.subject_group)}</strong></div>'
        f'<div class="meta-item"><span>业务动作</span><strong>{_esc(issue.action)}</strong></div>'
        f'<div class="meta-item"><span>受保护资源</span><strong>{_esc(issue.resource)}</strong></div>'
        f'<div class="meta-item"><span>资源关系</span><strong>{_esc(issue.relation)}</strong></div>'
        f'<div class="meta-item"><span>权限预期</span><strong>{_esc(issue.expectation)}</strong></div>'
        '</div><div class="result-grid">'
        f'<div class="result-box"><span>表面结果</span><p>{_esc(issue.surface_result)}</p></div>'
        f'<div class="result-box actual"><span>可信观察到的真实结果</span><p>{_esc(issue.actual_result)}</p></div>'
        '</div><div class="conclusion-box"><span>安全结论</span>'
        f'<strong>{_esc(issue.conclusion)}</strong><p>{_esc(issue.explanation)}</p></div>'
        '</div></article>'
        for issue in issues
    )


def _verdict_class(verdict: str | None) -> str:
    return {"BLOCK": "block", "PASS": "pass", "INCONCLUSIVE": "inconclusive"}.get(
        verdict or "",
        "unknown",
    )


def _verdict_label(verdict: str | None) -> str:
    return {
        "BLOCK": "发现权限问题",
        "PASS": "检查范围内符合预期",
        "INCONCLUSIVE": "证据不足",
    }.get(verdict or "", "未形成结论")


def _severity_class(severity: str) -> str:
    value = severity.casefold()
    return value if value in {"critical", "high", "medium", "low", "info"} else "info"


def _severity_label(severity: str) -> str:
    return {
        "critical": "严重",
        "high": "高风险",
        "medium": "中风险",
        "low": "低风险",
        "info": "提示",
    }.get(severity.casefold(), severity)


def _esc(value: object) -> str:
    """统一转义报告动态文本，避免展示层成为 HTML 注入边界。"""

    return html.escape(str(value), quote=True)


def _utc_time(value: int) -> str:
    return datetime.fromtimestamp(value / 1_000_000, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S.%f UTC"
    )


def _list_items(*groups: tuple[str, ...], empty: str) -> str:
    values = tuple(item for group in groups for item in group if item)
    return "".join(f"<li>{_esc(item)}</li>" for item in values) or f"<li>{_esc(empty)}</li>"


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
