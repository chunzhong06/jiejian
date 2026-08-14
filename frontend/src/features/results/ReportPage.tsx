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
import { Alert, Card, Collapse, Descriptions, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi } from '../../api/results'
import { runsApi } from '../../api/runs'
import { StageGuide } from '../../components/StageGuide'
import { verdictLabel } from '../sharedStatus'

type Item = Record<string, any>

export function ReportPage({ run, onError, onNext }: { run?: Item; onError: (e: ApiError) => void; onNext?: () => void }) {
  const [report, setReport] = useState<Item | null>(null)
  const [runState, setRunState] = useState<Item | null>(run ?? null)
  useEffect(() => {
    setReport(null)
    setRunState(run ?? null)
    if (!run?.run_id) return
    let active = true
    void runsApi.run(String(run.run_id)).then((authoritative) => {
      if (!active) return
      setRunState(authoritative)
      if (String(authoritative.result_integrity) !== 'VERIFIED') return
      if (String(authoritative.execution_schema_version ?? authoritative.result_schema_version) === '2') return
      void resultsApi.report(String(run.run_id)).then((next) => { if (active) setReport(next) }).catch((e) => {
        if (active && (e as ApiError).code !== 'ARTIFACT_NOT_PUBLISHED') onError(e as ApiError)
      })
    }).catch((e) => { if (active) onError(e as ApiError) })
    return () => { active = false }
  }, [run?.run_id])
  const verdict = report?.verdict
  const reasonCodes = Array.isArray(report?.reason_codes) ? report.reason_codes : []
  const isV2 = String(runState?.execution_schema_version ?? runState?.result_schema_version) === '2'
  const isPublishedV2 = isV2 && runState?.result_integrity === 'VERIFIED'
  const reportMessage = runState?.result_integrity === 'INVALID' ? '结果完整性无效，暂不提供报告。' : isPublishedV2 ? '复杂权限证据已发布，统一报告尚未生成；后续能力提供。' : isV2 ? '等待已发布证据。' : '报告仍在生成或尚未开始。'
  return <Space direction="vertical" size="large" style={{ width: '100%' }}><StageGuide stage="报告" what="阅读一次已发布检查的可读结论" why="报告只展示已发布且完整的结果，不把缺失数据当作通过" missing={report ? '尚未确认' : reportMessage} next="回到接入重新检查，或选择其他项目" onNext={onNext} nextLabel="回到接入" /><Card title="报告"><Typography.Paragraph>报告仅来自通过发布完整性校验的结果。</Typography.Paragraph>{isPublishedV2 && <Alert type="info" showIcon message="复杂权限证据已发布" description="统一报告尚未生成，当前不提供阶段 7 Finding 或 Gate 语义。" />}{report ? <>{verdict ? <Tag color={verdict === 'BLOCK' ? 'red' : verdict === 'PASS' ? 'green' : 'gold'}>{verdictLabel(verdict)}</Tag> : <Typography.Text type="warning">报告未提供安全结论</Typography.Text>}<Descriptions size="small" column={1}>{report.finding_count != null && <Descriptions.Item label="发现数量">{String(report.finding_count)}</Descriptions.Item>}{reasonCodes.length > 0 && <Descriptions.Item label="原因">{reasonCodes.join('、')}</Descriptions.Item>}</Descriptions><Collapse ghost items={[{ key: 'raw-report', label: '高级：原始报告 JSON', children: <pre className="report-view">{JSON.stringify(report, null, 2)}</pre> }]} /></> : <Typography.Paragraph>{reportMessage}</Typography.Paragraph>}</Card></Space>
}
