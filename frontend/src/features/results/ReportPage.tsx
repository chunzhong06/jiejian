/* =============================================================================
 * 报告页面
 *
 * 定位
 *   已发布 Run 报告 JSON 的只读用户页面
 *
 * 职责
 *   请求可信发布报告｜显示缺失状态｜保持服务端结果为事实真源
 *
 * 调用链
 *   ControlShell → ReportPage → resultsApi.report
 * ============================================================================= */

import { useEffect, useState } from 'react'
import { Alert, Card, Collapse, Descriptions, Select, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi } from '../../api/results'
import { runsApi } from '../../api/runs'
import { StageGuide } from '../../components/StageGuide'
import { verdictLabel } from '../sharedStatus'

type Item = Record<string, any>

export function ReportPage({ run, onError, onNext }: { run?: Item; onError: (e: ApiError) => void; onNext?: () => void }) {
  const [report, setReport] = useState<Item | null>(null)
  const [runState, setRunState] = useState<Item | null>(run ?? null)
  const [availableReports, setAvailableReports] = useState<Item[]>([])
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null)
  const [selectedGateResultId, setSelectedGateResultId] = useState<string | null>(null)
  const isV2 = String(runState?.execution_schema_version ?? runState?.result_schema_version) === '2'
  const isPublishedV2 = isV2 && runState?.result_integrity === 'VERIFIED'
  useEffect(() => {
    setReport(null)
    setAvailableReports([])
    setSelectedReportId(null)
    setSelectedGateResultId(null)
    setRunState(run ?? null)
    if (!run?.run_id) return
    let active = true
    void runsApi.run(String(run.run_id)).then((authoritative) => {
      if (!active) return
      setRunState(authoritative)
      if (String(authoritative.result_integrity) !== 'VERIFIED') return
      if (String(authoritative.execution_schema_version ?? authoritative.result_schema_version) === '2') {
        void resultsApi.reports(String(run.run_id)).then((available) => {
          if (!active) return
          setAvailableReports(available)
          if (available.length === 1 && available[0]?.report_id) {
            setSelectedReportId(String(available[0].report_id))
            setSelectedGateResultId(String(available[0].gate_result_id ?? ''))
          }
        }).catch((e) => { if (active && (e as ApiError).code !== 'REPORT_NOT_FOUND') onError(e as ApiError) })
        return
      }
      void resultsApi.report(String(run.run_id)).then((next) => { if (active) setReport(next) }).catch((e) => {
        if (active && (e as ApiError).code !== 'ARTIFACT_NOT_PUBLISHED') onError(e as ApiError)
      })
    }).catch((e) => { if (active) onError(e as ApiError) })
    return () => { active = false }
  }, [run?.run_id])
  useEffect(() => {
    if (!run?.run_id || !isPublishedV2 || !selectedReportId) return
    let active = true
    void resultsApi.reportV2(String(run.run_id), selectedReportId).then((next) => {
      if (!active) return
      setSelectedGateResultId(String(next.gate?.gate_result_id ?? ''))
      setReport(next)
    }).catch((e) => { if (active) onError(e as ApiError) })
    return () => { active = false }
  }, [run?.run_id, isPublishedV2, selectedReportId])
  const verdict = report?.gate?.decision ?? report?.verdict
  const runtimeVerdict = report?.runtime?.verdict
  const reasonCodes = Array.isArray(report?.gate?.reasons) ? report.gate.reasons.map((item: Item) => item.code) : Array.isArray(report?.reason_codes) ? report.reason_codes : []
  const reportMessage = runState?.result_integrity === 'INVALID' ? '结果完整性无效，暂不提供报告。' : isPublishedV2 ? '复杂权限证据已发布，尚未找到完整性已验证的统一报告。' : isV2 ? '等待已发布证据。' : '报告仍在生成或尚未开始。'
  const artifactCount = Array.isArray(report?.artifacts) ? report.artifacts.length : 0
  const executionErrors = Array.isArray(report?.runtime?.execution_errors) ? report.runtime.execution_errors : []
  return <Space direction="vertical" size="large" style={{ width: '100%' }}><StageGuide stage="报告" what="阅读一次已发布检查的可读结论" why="报告只展示已发布且完整的结果，不把缺失数据当作通过" missing={report ? '尚未确认' : reportMessage} next="回到接入重新检查，或选择其他项目" onNext={onNext} nextLabel="回到接入" /><Card title="报告"><Typography.Paragraph>报告仅来自通过发布完整性校验的结果。</Typography.Paragraph>{isPublishedV2 && !report && <Alert type="info" showIcon message="复杂权限证据已发布" description="统一报告必须从明确的 GateResult 生成并通过独立 publication 校验。" />}{availableReports.length > 1 && <Select style={{ minWidth: 360 }} placeholder="请选择报告与 GateResult" value={selectedReportId ?? undefined} onChange={(value) => { setReport(null); setSelectedReportId(String(value)); const selected = availableReports.find((item) => String(item.report_id) === String(value)); setSelectedGateResultId(String(selected?.gate_result_id ?? '')) }} options={availableReports.map((item) => ({ value: String(item.report_id), label: `${item.report_id} · ${item.gate_result_id} · ${item.gate_decision}` }))} />}{report ? <>{verdict ? <Tag color={verdict === 'BLOCK' ? 'red' : verdict === 'PASS' ? 'green' : 'gold'}>{verdictLabel(verdict)}</Tag> : <Typography.Text type="warning">报告未提供安全结论</Typography.Text>}<Descriptions size="small" column={1}>{report.run_id && <Descriptions.Item label="Run ID">{String(report.run_id)}</Descriptions.Item>}{(report.gate?.gate_result_id ?? selectedGateResultId) && <Descriptions.Item label="GateResult ID">{String(report.gate?.gate_result_id ?? selectedGateResultId)}</Descriptions.Item>}{report.gate?.decision && <Descriptions.Item label="Gate decision">{String(report.gate.decision)}</Descriptions.Item>}{reasonCodes.length > 0 && <Descriptions.Item label="Gate reasons">{reasonCodes.join('、')}</Descriptions.Item>}{runtimeVerdict && <Descriptions.Item label="运行时 verdict">{String(runtimeVerdict)}</Descriptions.Item>}{report.runtime?.findings && <Descriptions.Item label="运行时 Finding 数">{String(report.runtime.findings.length)}</Descriptions.Item>}{report.artifacts && <Descriptions.Item label="Artifact 数">{String(artifactCount)}</Descriptions.Item>}{executionErrors.length > 0 && <Descriptions.Item label="运行时执行错误">{executionErrors.join('、')}</Descriptions.Item>}{Array.isArray(report.limitations) && report.limitations.length > 0 && <Descriptions.Item label="限制">{report.limitations.join('、')}</Descriptions.Item>}</Descriptions>{artifactCount > 0 && <Descriptions title="Artifact 状态" size="small" column={1}>{report.artifacts.map((artifact: Item) => <Descriptions.Item key={String(artifact.artifact_id)} label={String(artifact.artifact_id)}>{`${artifact.status} / ${artifact.verdict} / 风险 ${Array.isArray(artifact.findings) ? artifact.findings.length : 0}${artifact.error_code ? ` / ${artifact.error_code}` : ''}`}</Descriptions.Item>)}</Descriptions>}<Collapse ghost items={[{ key: 'raw-report', label: '高级：原始报告 JSON', children: <pre className="report-view">{JSON.stringify(report, null, 2)}</pre> }]} /></> : <Typography.Paragraph>{availableReports.length > 1 ? '存在多个报告，请明确选择 report_id。' : reportMessage}</Typography.Paragraph>}</Card></Space>
}
