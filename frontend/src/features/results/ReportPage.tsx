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
import { Card, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi } from '../../api/results'

type Item = Record<string, any>

export function ReportPage({ run, onError }: { run?: Item; onError: (e: ApiError) => void }) {
  const [report, setReport] = useState<Item | null>(null)
  useEffect(() => { if (run?.run_id) void resultsApi.report(run.run_id).then(setReport).catch((e) => onError(e as ApiError)) }, [run?.run_id])
  return <Card title="报告"><Typography.Paragraph>报告仅来自通过发布完整性校验的 JSON。</Typography.Paragraph><pre className="report-view">{report ? JSON.stringify(report, null, 2) : '暂无已发布报告'}</pre></Card>
}
