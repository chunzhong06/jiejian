/* 统一报告只读面板：分开安全检查结论与交付门禁。 */

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Collapse, Descriptions, Select, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi, type ReportDto } from '../../api/results'
import { runsApi, type RunDto } from '../../api/runs'
import { gateDecisionLabel, verdictLabel } from '../../app/presentation'

export function ReportPanel({ run, onError }: { run?: RunDto; onError: (error: ApiError) => void }) {
  const [authoritative, setAuthoritative] = useState<RunDto | undefined>(run)
  const [reports, setReports] = useState<ReportDto[]>([])
  const [selectedId, setSelectedId] = useState<string>()
  const [report, setReport] = useState<ReportDto | null>(null)
  useEffect(() => {
    setAuthoritative(run); setReports([]); setReport(null); setSelectedId(undefined)
    if (!run?.run_id) return
    let active = true
    void runsApi.run(String(run.run_id)).then((value) => {
      if (!active) return
      setAuthoritative(value)
      if (String(value.result_integrity) !== 'VERIFIED') return
      void resultsApi.reports(String(run.run_id)).then((items) => { if (active) { setReports(items); if (items.length === 1) setSelectedId(String(items[0].report_id)) } }).catch((error) => { if (active && (error as ApiError).code !== 'REPORT_NOT_FOUND') onError(error as ApiError) })
    }).catch((error) => { if (active) onError(error as ApiError) })
    return () => { active = false }
  }, [run?.run_id])
  useEffect(() => {
    if (!run?.run_id || !selectedId) return
    let active = true
    void resultsApi.report(String(run.run_id), selectedId).then((value) => { if (active) setReport(value) }).catch((error) => { if (active) onError(error as ApiError) })
    return () => { active = false }
  }, [run?.run_id, selectedId])
  if (!run?.run_id) return <Card title="完整报告"><Alert type="info" showIcon message="尚未选择可查看的检查结果。" /></Card>
  if (authoritative?.result_integrity !== 'VERIFIED') return <Card title="完整报告"><Alert type="info" showIcon message="结果尚未通过完整性校验，暂不提供报告。" /></Card>
  const runtimeVerdict = report?.runtime?.verdict ?? report?.verdict
  const gateDecision = report?.gate?.decision
  const findings = Array.isArray(report?.runtime?.findings) ? report.runtime.findings : []
  const errors = Array.isArray(report?.runtime?.execution_errors) ? report.runtime.execution_errors : []
  const observers = Array.isArray(report?.runtime?.observer_statuses) ? report.runtime.observer_statuses : []
  const artifacts = Array.isArray(report?.artifacts) ? report.artifacts : []
  const limitations = Array.isArray(report?.limitations) ? report.limitations : []
  return <Card title="完整报告">
    {reports.length > 1 && <Select aria-label="选择完整报告" className="full-width" value={selectedId} onChange={setSelectedId} options={reports.map((item, index) => ({ value: String(item.report_id), label: `检查报告 ${index + 1} · ${gateDecisionLabel(item.gate_decision)}` }))} />}
    {!report && reports.length === 0 && <Typography.Paragraph type="secondary">已发布结果，但没有可读取的统一报告。</Typography.Paragraph>}
    {report && <Space direction="vertical" className="full-width">
      <Space wrap><Tag color={runtimeVerdict === 'BLOCK' ? 'red' : runtimeVerdict === 'PASS' ? 'green' : 'gold'}>安全检查结论：{verdictLabel(runtimeVerdict)}</Tag>{gateDecision && <Tag>交付门禁：{gateDecisionLabel(gateDecision)}</Tag>}</Space>
      {gateDecision && <Typography.Paragraph type="secondary">安全检查结论与交付门禁是相互独立的判断。</Typography.Paragraph>}
      <Descriptions size="small" column={{ xs: 1, sm: 2 }}><Descriptions.Item label="问题数量">{findings.length}</Descriptions.Item><Descriptions.Item label="产物检查">{artifacts.length > 0 ? artifacts.map((item, index) => `产物 ${index + 1}：${item.status === 'COMPLETE' ? '检查完整' : '无法确认'}`).join('；') : '没有产物检查结果'}</Descriptions.Item><Descriptions.Item label="必需观察">{observers.length > 0 ? observers.filter((item) => item.required).map((item) => `${item.observer_id === 'http' ? '接口响应' : item.observer_id === 'owner_api' ? '资源状态' : '外部状态'}：${item.status === 'AVAILABLE' ? '可用' : '无法确认'}`).join('；') || '未声明' : '未提供'}</Descriptions.Item>{errors.length > 0 && <Descriptions.Item label="执行错误">存在 {errors.length} 项执行错误</Descriptions.Item>}{limitations.length > 0 && <Descriptions.Item label="限制">存在 {limitations.length} 项无法确认的内容</Descriptions.Item>}</Descriptions>
      {selectedId && <Space wrap>{(['json', 'html', 'sarif', 'junit'] as const).map((format) => <Button key={format} href={resultsApi.reportFormat(String(run.run_id), selectedId, format)} target="_blank">导出{format.toUpperCase()}</Button>)}</Space>}
      <Collapse ghost items={[{ key: 'report-technical', label: '高级：报告技术详情', children: <pre className="report-view">{JSON.stringify(report, null, 2)}</pre> }]} />
    </Space>}
  </Card>
}
