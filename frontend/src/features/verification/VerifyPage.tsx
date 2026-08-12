/* =============================================================================
 * 验证页面
 *
 * 定位
 *   Run 生命周期、Verdict、Finding 与 Evidence 的用户核验页面
 *
 * 职责
 *   区分执行状态和安全结论｜读取已发布详情｜呈现证据关联
 *
 * 调用链
 *   ControlShell → VerifyPage → runsApi / resultsApi
 * ============================================================================= */

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Descriptions, List, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi } from '../../api/results'
import { runsApi } from '../../api/runs'

type Item = Record<string, any>

export function VerifyPage({ run, onError }: { run?: Item; onError: (e: ApiError) => void }) {
  const [current, setCurrent] = useState<Item | undefined>(run)
  const [findings, setFindings] = useState<Item[]>([])
  const [evidence, setEvidence] = useState<Item[]>([])
  const [detail, setDetail] = useState<Item | null>(null)
  useEffect(() => {
    setCurrent(run)
    if (run?.run_id) {
      void runsApi.run(String(run.run_id)).then(setCurrent).catch((e) => onError(e as ApiError))
      void resultsApi.findings(String(run.run_id)).then(setFindings).catch((e) => onError(e as ApiError))
      void resultsApi.evidence(String(run.run_id)).then(setEvidence).catch((e) => onError(e as ApiError))
    }
  }, [run?.run_id])
  const target = current?.target_scope as Item | undefined
  const budget = current?.budget as Item | undefined
  const observer = current?.observer_health as Item | undefined
  const progress = current?.case_progress as Item | undefined
  const safety = current?.safety_context as Item | undefined
  const reasonCodes = Array.isArray(current?.reason_codes) ? current.reason_codes : []
  const safetyReasonCodes = Array.isArray(safety?.reason_codes) ? safety.reason_codes : []
  const integrity = String(current?.result_integrity ?? 'UNAVAILABLE')
  const verdictVisible = integrity !== 'INVALID'
  const integrityColor = integrity === 'VERIFIED' ? 'green' : integrity === 'INVALID' ? 'red' : 'default'
  return <Card title="验证">
    <Space direction="vertical" size="middle" className="full-width">
      <Card size="small" title="生命周期">
        <Descriptions size="small" column={1}><Descriptions.Item label="当前状态">{current?.lifecycle ?? '—'}</Descriptions.Item></Descriptions>
      </Card>
      <Card size="small" title="门禁结论">
        <Descriptions size="small" column={1}><Descriptions.Item label="Gate verdict">{verdictVisible ? <Tag color={current?.verdict === 'BLOCK' ? 'red' : current?.verdict === 'PASS' ? 'green' : 'gold'}>{current?.verdict ?? '等待结论'}</Tag> : <Typography.Text type="danger">结果完整性无效，已隐藏 Gate verdict</Typography.Text>}</Descriptions.Item></Descriptions>
      </Card>
      <Card size="small" title="结果完整性与运行概览">
        <Space direction="vertical" className="full-width">
          <Tag color={integrityColor}>结果完整性：{integrity}</Tag>
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="目标 base_url">{String(target?.base_url ?? '—')}</Descriptions.Item>
            <Descriptions.Item label="允许主机">{Array.isArray(target?.allowed_hosts) && target.allowed_hosts.length > 0 ? target.allowed_hosts.join('、') : '—'}</Descriptions.Item>
            <Descriptions.Item label="允许端口">{Array.isArray(target?.allowed_ports) && target.allowed_ports.length > 0 ? target.allowed_ports.join('、') : '—'}</Descriptions.Item>
            <Descriptions.Item label="预算 max_requests">{String(budget?.max_requests ?? '—')}</Descriptions.Item>
            <Descriptions.Item label="预算 max_response_bytes">{String(budget?.max_response_bytes ?? '—')}</Descriptions.Item>
            <Descriptions.Item label="预算 request_timeout_us">{String(budget?.request_timeout_us ?? '—')}</Descriptions.Item>
            <Descriptions.Item label="HTTP 观察器">{observer?.http?.configured ? '已配置' : '未配置'} · {observer?.http?.required ? '契约要求' : '契约未要求'}</Descriptions.Item>
            <Descriptions.Item label="owner_api 观察器">{observer?.owner_api?.configured ? '已配置' : '未配置'} · {observer?.owner_api?.required ? '契约要求' : '契约未要求'}</Descriptions.Item>
            <Descriptions.Item label="用例进度">{progress?.status === 'PUBLISHED' ? `${progress.completed}/${progress.total}` : '发布后可用'}</Descriptions.Item>
            <Descriptions.Item label="Finding 数量">{current?.finding_count == null ? '发布后可用' : String(current.finding_count)}</Descriptions.Item>
          </Descriptions>
        </Space>
      </Card>
      {current?.verdict === 'INCONCLUSIVE' && <Alert type="warning" showIcon message="INCONCLUSIVE · 原因码" description={reasonCodes.length ? reasonCodes.join('、') : '未提供 reason_codes'} />}
      {current?.lifecycle === 'SAFETY_STOPPED' && <Alert type="error" showIcon message="SAFETY_STOPPED · 安全边界已停止运行" description={<Descriptions size="small" column={1}><Descriptions.Item label="原因码">{safetyReasonCodes.length ? safetyReasonCodes.join('、') : '未提供 reason_codes'}</Descriptions.Item><Descriptions.Item label="目标">{String(safety?.target_scope?.base_url ?? target?.base_url ?? '—')}</Descriptions.Item><Descriptions.Item label="预算 max_requests">{String(safety?.budget?.max_requests ?? budget?.max_requests ?? '—')}</Descriptions.Item></Descriptions>} />}
      <List header="确定性 Findings" dataSource={findings} locale={{ emptyText: '等待已发布证据' }} renderItem={(finding) => <List.Item><Space><Tag>{finding.verdict}</Tag><Typography.Text>{finding.finding_id}</Typography.Text></Space></List.Item>} />
      <List header="证据差分" dataSource={evidence} renderItem={(item) => <List.Item actions={[<Button onClick={() => current && void resultsApi.evidenceDetail(String(current.run_id), String(item.evidence_id)).then(setDetail).catch((e) => onError(e as ApiError))}>查看差分</Button>]}><List.Item.Meta title={String(item.case_id)} description={`Evidence ${String(item.evidence_id)}`} /></List.Item>} />
      {detail && <Card size="small" title="身份、请求与副作用差分"><pre>{JSON.stringify(detail.difference ?? detail, null, 2)}</pre></Card>}
    </Space>
  </Card>
}
