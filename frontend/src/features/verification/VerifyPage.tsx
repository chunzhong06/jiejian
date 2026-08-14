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
import { Alert, Button, Card, Collapse, Descriptions, List, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi } from '../../api/results'
import { runsApi } from '../../api/runs'
import { StageGuide } from '../../components/StageGuide'
import { lifecycleLabel, verdictLabel } from '../sharedStatus'

type Item = Record<string, any>

export function VerifyPage({ run, onError, onNext }: { run?: Item; onError: (e: ApiError) => void; onNext?: () => void }) {
  const [current, setCurrent] = useState<Item | undefined>(run)
  const [findings, setFindings] = useState<Item[]>([])
  const [evidence, setEvidence] = useState<Item[]>([])
  const [detail, setDetail] = useState<Item | null>(null)
  useEffect(() => {
    setCurrent(run)
    setFindings([])
    setEvidence([])
    if (!run?.run_id) return
    let active = true
    void runsApi.run(String(run.run_id)).then(async (authoritative) => {
      if (!active) return
      setCurrent(authoritative)
      if (String(authoritative.result_integrity) !== 'VERIFIED') return
      const nextEvidence = await resultsApi.evidence(String(run.run_id))
      if (active) setEvidence(nextEvidence)
      if (active && String(authoritative.execution_schema_version ?? authoritative.result_schema_version) !== '2') {
        setFindings(await resultsApi.findings(String(run.run_id)))
      }
    }).catch((e) => { if (active) onError(e as ApiError) })
    return () => { active = false }
  }, [run?.run_id])
  const target = current?.target_scope as Item | undefined
  const budget = current?.budget as Item | undefined
  const observer = current?.observer_health as Item | undefined
  const progress = current?.case_progress as Item | undefined
  const safety = current?.safety_context as Item | undefined
  const reasonCodes = Array.isArray(current?.reason_codes) ? current.reason_codes : []
  const isV2 = String(current?.execution_schema_version ?? current?.result_schema_version) === '2'
  const safetyReasonCodes = Array.isArray(safety?.reason_codes) ? safety.reason_codes : []
  const integrity = String(current?.result_integrity ?? 'UNAVAILABLE')
  const verdictVisible = integrity !== 'INVALID'
  const integrityColor = integrity === 'VERIFIED' ? 'green' : integrity === 'INVALID' ? 'red' : 'default'
  return <Card title="验证">
    <Space direction="vertical" size="middle" className="full-width">
      <StageGuide stage="验证" what="查看系统为什么得出结论" why="把执行状态和安全结论分开，避免把未完成当成安全" missing={!current ? '等待检查完成' : progress?.status === 'PUBLISHED' ? '尚未确认' : '等待证据发布'} next={progress?.status === 'PUBLISHED' ? '查看可读报告' : '等待检查完成并发布证据'} onNext={progress?.status === 'PUBLISHED' ? onNext : undefined} nextLabel="查看报告" />
      <Card size="small" title="检查状态与结论">
        <Descriptions size="small" column={1}><Descriptions.Item label="当前状态">{lifecycleLabel(current?.lifecycle)}</Descriptions.Item><Descriptions.Item label="安全结论">{verdictVisible && current?.verdict ? verdictLabel(current.verdict) : current?.result_integrity === 'INVALID' ? '结果完整性无效，暂不提供安全结论' : '等待结论'}</Descriptions.Item><Descriptions.Item label="结果完整性"><Tag color={integrityColor}>{integrity === 'VERIFIED' ? '已验证' : integrity === 'INVALID' ? '无效' : '尚未确认'}</Tag></Descriptions.Item></Descriptions>
      </Card>
      {current?.lifecycle === 'SAFETY_STOPPED' && <Alert type="error" showIcon message="安全边界已停止运行" description="系统已停止这次检查，不会把未完成或不完整的证据当作安全结论。" />}
      <Collapse ghost items={[{ key: 'verification-details', label: isV2 ? '高级：复杂权限证据与运行细节' : '高级：证据与运行细节', forceRender: true, children: <Space direction="vertical" className="full-width"><Card size="small" title="结果完整性与运行概览">
        <Space direction="vertical" className="full-width">
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="目标 base_url">{String(target?.base_url ?? '—')}</Descriptions.Item>
            <Descriptions.Item label="允许主机">{Array.isArray(target?.allowed_hosts) && target.allowed_hosts.length > 0 ? target.allowed_hosts.join('、') : '—'}</Descriptions.Item>
            <Descriptions.Item label="允许端口">{Array.isArray(target?.allowed_ports) && target.allowed_ports.length > 0 ? target.allowed_ports.join('、') : '—'}</Descriptions.Item>
            <Descriptions.Item label="预算 max_requests">{String(budget?.max_requests ?? '—')}</Descriptions.Item>
            <Descriptions.Item label="预算 max_response_bytes">{String(budget?.max_response_bytes ?? '—')}</Descriptions.Item>
            <Descriptions.Item label="预算 request_timeout_us">{String(budget?.request_timeout_us ?? '—')}</Descriptions.Item>
            <Descriptions.Item label="执行版本">{isV2 ? 'Runner V2 / Evidence V2' : 'Runner V1'}</Descriptions.Item>
            {isV2 ? <Descriptions.Item label="必需观察器"><Space wrap>{Array.isArray(observer?.required_observers) && observer.required_observers.map((name: string) => <Tag key={name}>{name}{observer?.[name]?.required ? ' · 必需' : ''}</Tag>)}</Space></Descriptions.Item> : <><Descriptions.Item label="HTTP 观察器">{observer?.http?.configured ? '已配置' : '未配置'} · {observer?.http?.required ? '契约要求' : '契约未要求'}</Descriptions.Item><Descriptions.Item label="owner_api 观察器">{observer?.owner_api?.configured ? '已配置' : '未配置'} · {observer?.owner_api?.required ? '契约要求' : '契约未要求'}</Descriptions.Item></>}
            {isV2 && <Descriptions.Item label="覆盖与缺口">覆盖 {String(current?.coverage_record_count ?? 0)} · 缺口 {String(current?.coverage_gap_count ?? 0)}</Descriptions.Item>}
            <Descriptions.Item label="用例进度">{progress?.status === 'PUBLISHED' ? `${progress.completed}/${progress.total}` : '发布后可用'}</Descriptions.Item>
            <Descriptions.Item label="Finding 数量">{current?.finding_count == null ? '发布后可用' : String(current.finding_count)}</Descriptions.Item>
          </Descriptions>
        </Space>
      </Card>{current?.lifecycle === 'SAFETY_STOPPED' && <Descriptions size="small" column={1}><Descriptions.Item label="停止原因">{safetyReasonCodes.length ? safetyReasonCodes.join('、') : '尚未确认'}</Descriptions.Item><Descriptions.Item label="停止时目标">{String(safety?.target_scope?.base_url ?? target?.base_url ?? '—')}</Descriptions.Item><Descriptions.Item label="停止时预算">{String(safety?.budget?.max_requests ?? budget?.max_requests ?? '—')}</Descriptions.Item></Descriptions>}{current?.verdict === 'INCONCLUSIVE' && <Alert type="warning" showIcon message="证据不足" description={reasonCodes.length ? reasonCodes.join('、') : '原因尚未确认'} />}{isV2 ? <List header="V2 Evidence" dataSource={evidence} locale={{ emptyText: '等待已发布 Evidence' }} renderItem={(item) => <List.Item actions={[<Button onClick={() => current && void resultsApi.evidenceDetail(String(current.run_id), String(item.evidence_id)).then(setDetail).catch((e) => onError(e as ApiError))}>查看证据</Button>]}><List.Item.Meta title={String(item.case_id)} description={`Evidence ${String(item.evidence_id)}`} /></List.Item>} /> : <><List header="确定性 Findings" dataSource={findings} locale={{ emptyText: '等待已发布证据' }} renderItem={(finding) => <List.Item><Space><Tag>{finding.verdict}</Tag><Typography.Text>{finding.finding_id}</Typography.Text></Space></List.Item>} /><List header="证据差分" dataSource={evidence} renderItem={(item) => <List.Item actions={[<Button onClick={() => current && void resultsApi.evidenceDetail(String(current.run_id), String(item.evidence_id)).then(setDetail).catch((e) => onError(e as ApiError))}>查看差分</Button>]}><List.Item.Meta title={String(item.case_id)} description={`Evidence ${String(item.evidence_id)}`} /></List.Item>} /></>}{detail && <Card size="small" title={isV2 ? 'V2 Evidence（已发布原始可信字段）' : '身份、请求与副作用差分'}><pre>{JSON.stringify(detail.difference ?? detail, null, 2)}</pre></Card>}</Space> }]} />
    </Space>
  </Card>
}
