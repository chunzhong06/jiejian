/* 正式报告面板：读取已发布报告索引，主体交给同源安全 HTML view。 */

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Dropdown, Select, Space, Typography } from 'antd'
import { DownOutlined } from '@ant-design/icons'
import { ApiError } from '../../api/http'
import { resultsApi, type ReportDto } from '../../api/results'
import { runsApi, type RunDto } from '../../api/runs'
import { gateDecisionLabel } from '../../app/presentation'
import { useThemeMode } from '../../app/ThemeContext'

const exportFormats = [
  ['html', 'HTML'],
  ['json', 'JSON'],
  ['sarif', 'SARIF'],
  ['junit', 'JUnit'],
] as const

export function ReportPanel({ run, onError }: { run?: RunDto; onError: (error: ApiError) => void }) {
  const { resolved } = useThemeMode()
  const [authoritative, setAuthoritative] = useState<RunDto | undefined>(run)
  const [reports, setReports] = useState<ReportDto[]>([])
  const [selectedId, setSelectedId] = useState<string>()

  useEffect(() => {
    setAuthoritative(run)
    setReports([])
    setSelectedId(undefined)
    if (!run?.run_id) return
    let active = true
    void runsApi.run(String(run.run_id)).then((value) => {
      if (!active) return
      setAuthoritative(value)
      if (String(value.result_integrity) !== 'VERIFIED') return
      void resultsApi.reports(String(run.run_id)).then((items) => {
        if (!active) return
        setReports(items)
        setSelectedId(items[0]?.report_id ? String(items[0].report_id) : undefined)
      }).catch((error) => { if (active && (error as ApiError).code !== 'REPORT_NOT_FOUND') onError(error as ApiError) })
    }).catch((error) => { if (active) onError(error as ApiError) })
    return () => { active = false }
  }, [run?.run_id])

  if (!run?.run_id) return <Card title="完整报告"><Alert type="info" showIcon message="尚未选择可查看的检查结果。" /></Card>
  if (authoritative?.result_integrity !== 'VERIFIED') return <Card title="完整报告"><Alert type="info" showIcon message="结果尚未通过完整性校验，暂不提供报告。" /></Card>
  const viewUrl = selectedId ? resultsApi.reportView(String(run.run_id), selectedId) : undefined
  const themedViewUrl = viewUrl && resolved === 'dark' ? `${viewUrl}#dark-theme` : viewUrl
  const exportItems = exportFormats.map(([format, label]) => ({
    key: format,
    label: <a href={resultsApi.reportFormat(String(run.run_id), String(selectedId), format)} target="_blank" rel="noopener noreferrer">{label}</a>,
  }))

  return <Card title="完整报告">
    {reports.length > 1 && <Select aria-label="选择完整报告" className="full-width" value={selectedId} onChange={setSelectedId} options={reports.map((item, index) => ({ value: String(item.report_id), label: `检查报告 ${index + 1} · ${item.gate_decision ? gateDecisionLabel(item.gate_decision) : '基础报告'}` }))} />}
    {!selectedId && <Typography.Paragraph type="secondary">已发布结果，但没有可读取的统一报告。</Typography.Paragraph>}
    {viewUrl && <Space direction="vertical" className="full-width">
      <Space wrap>
        <Button href={themedViewUrl} target="_blank" rel="noopener noreferrer">在新窗口打开</Button>
        <Dropdown menu={{ items: exportItems }} trigger={['click']}>
          <Button>导出 <DownOutlined /></Button>
        </Dropdown>
      </Space>
      <iframe title="界鉴权限安全检查报告" src={themedViewUrl} sandbox="" className="report-frame" />
    </Space>}
  </Card>
}
