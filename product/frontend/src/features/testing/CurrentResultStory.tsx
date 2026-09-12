// 已发布结果的业务展示；安全判断与断裂精度原样取自后端，原始证据只在明确详情中展开。
import { Alert, Button, Collapse, Descriptions, Drawer, Empty, Spin, Typography } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { currentChecksApi, type CheckBreakpoint, type CheckEvidence, type EvidenceExplanation, type ResultStory } from '../../api/currentChecks'
import type { ApiError } from '../../api/http'
import { AssistantPanel } from '../../components/AssistantPanel'
import { formatTimestamp } from '../../app/presentation'
import { repairLabels } from '../../api/repairs'

const breakpointLabels = {
  AUTHORIZATION_MISSING: '关键操作缺少权限检查', AUTHORIZATION_LATE: '权限检查介入过晚',
  AUTHORIZATION_BYPASS: '业务操作绕过了权限检查', IDENTITY_SUBSTITUTION: '执行身份发生替换',
  AUTHORITY_EXPANSION: '后台执行的权限范围扩大', COMPENSATION_MASKING: '后续恢复掩盖了已经发生的后果',
}
const precisionLabels = { EXACT: '已定位到首个可证明的位置', RANGE: '已定位到两个边界之间', VIOLATION_ONLY: '后果已确认，现有证据不足以进一步定位' }
const phaseLabels = { BASELINE: '初始状态', BEFORE: '操作前', AFTER: '操作后', EVENTUAL: '最终观察', RECOVERY: '恢复后' }
const stateLabels = { CONFIRMED: '已发现', ABSENT: '未发现', UNKNOWN: '无法确认' }
const controlLabels = { SAFE: '正常对照已通过', VULNERABLE: '正常对照发现问题', INCONCLUSIVE: '正常对照证据不足' }

export function CurrentResultStory({ story, onError, onNavigate }: { story: ResultStory; onError: (error: ApiError) => void; onNavigate?: (path: string) => void }) {
  const [detail, setDetail] = useState<{ source?: EvidenceExplanation; breakpoint?: CheckBreakpoint; refs: string[] }>()
  const [documents, setDocuments] = useState<CheckEvidence[]>([])
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)
  const requestEpoch = useRef(0)
  useEffect(() => () => { requestEpoch.current += 1 }, [])
  const openEvidence = async (refs: string[], source?: EvidenceExplanation, breakpoint?: CheckBreakpoint) => {
    const epoch = ++requestEpoch.current
    setDetail({ refs, source, breakpoint }); setDocuments([]); setLoading(true); setFailed(false)
    try {
      // 详情必须重新走完整性 reader；不把索引或缓存中的显示文案当作证据文件。
      const values = await Promise.all([...new Set(refs)].map((id) => currentChecksApi.evidence(story.run_id, id)))
      if (requestEpoch.current === epoch) setDocuments(values)
    } catch (error) { if (requestEpoch.current === epoch) { setFailed(true); onError(error as ApiError) } }
    finally { if (requestEpoch.current === epoch) setLoading(false) }
  }
  const evidenceRow = (item: EvidenceExplanation, index: number) => <section className="check-evidence-row" key={`${item.observed_fact.observer_id}:${item.observed_fact.phase}:${index}`}>
    <Typography.Text strong>{item.source_label}</Typography.Text>
    <Typography.Paragraph type="secondary">{phaseLabels[item.observed_fact.phase]} · {stateLabels[item.observed_fact.state]}</Typography.Paragraph>
    <Typography.Paragraph>{item.supports_claim}</Typography.Paragraph>
    <Button onClick={() => void openEvidence(item.evidence_refs, item)}>查看{item.source_label}证据</Button>
  </section>
  const ordered = [...story.actions].sort((a, b) => Number(a.permission.expectation === 'ALLOW') - Number(b.permission.expectation === 'ALLOW'))
  return <>
    <Typography.Paragraph type="secondary">本次检查依据权限版本 {story.policy_epoch}</Typography.Paragraph>
    {story.repair_verification && <Alert type={story.repair_verification.status === 'VERIFIED' ? 'success' : 'warning'} showIcon message={repairLabels[story.repair_verification.status]} description="原题复验状态来自原检查与本次新检查的已发布事实。" action={onNavigate && <Button onClick={() => onNavigate(`/tests?run_id=${encodeURIComponent(story.repair_verification!.source_run_id)}`)}>查看原问题</Button>} />}
    {story.change_context && onNavigate && <Button onClick={() => onNavigate('/changes')}>查看关联变化与修复</Button>}
    <Collapse accordion defaultActiveKey={ordered[0]?.case_id} items={ordered.map((action) => {
      const comparison = action.fact_comparison
      const actual = comparison.verified_actual_identity
      return { key: action.case_id, label: `${action.display_name} · ${comparison.planned_identity.label ?? '计划账号'} · ${action.permission.expectation === 'DENY' ? '应当拒绝' : '应当允许'}`,
        children: <>
          <Typography.Title level={4}>{action.judgement}</Typography.Title>
          {action.repair_requirement && <section aria-label="原题修复要求">
            <Typography.Title level={5}>原题修复要求</Typography.Title>
            <Typography.Paragraph>保持原权限、操作账号、资源归属和证据标准，消除本题不应发生的后果，并保留 {action.repair_requirement.regressions.length} 项原正常业务回归。</Typography.Paragraph>
            {onNavigate && <Button onClick={() => onNavigate(`/changes?repair_reference=${encodeURIComponent(action.repair_requirement!.repair_fingerprint)}`)}>登记修复变化</Button>}
          </section>}
          <Descriptions title="事实对照" column={{ xs: 1, sm: 2 }} layout="vertical" items={[
            { key: 'permission', label: '权限要求', children: `${comparison.planned_identity.actor_label ?? '当前主体'}${action.permission.expectation === 'DENY' ? '不得' : '可以'}${action.display_name}；${action.permission.relation === 'OWNS' ? '操作自己的资源' : action.permission.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? '操作同类主体其他账号的资源' : '操作其他权限主体的资源'}` },
            { key: 'planned', label: '计划使用的账号', children: comparison.planned_identity.label ?? '未提供账号名称' },
            { key: 'actual', label: '独立确认的实际账号', children: actual.verification_status === 'MATCH' ? actual.label ?? '身份已独立确认' : actual.verification_status === 'MISMATCH' ? '实际身份与计划不一致' : '无法独立确认' },
            { key: 'http', label: '请求的表面回应', children: <>{comparison.http_surface.http_status !== null && <Typography.Text>HTTP {comparison.http_surface.http_status} · </Typography.Text>}{comparison.http_explanation}</> },
            { key: 'effects', label: '真实业务后果', span: 2, children: comparison.effects.map((effect) => <Typography.Paragraph key={effect.effect_id}>{effect.business_label}：{effect.judgement}</Typography.Paragraph>) },
            { key: 'control', label: '正常业务对照', children: comparison.allow_control ? controlLabels[comparison.allow_control.verdict] : '本项为正常业务验证' },
          ]} />
          {action.breakpoint && <section aria-label="断裂位置">
            <Typography.Title level={5}>断裂位置</Typography.Title>
            <Typography.Paragraph>{action.breakpoint.breakpoint_type ? breakpointLabels[action.breakpoint.breakpoint_type] : '当前无法确定断裂类型'}</Typography.Paragraph>
            <Typography.Paragraph type="secondary">{precisionLabels[action.breakpoint.precision]}</Typography.Paragraph>
            <Button onClick={() => void openEvidence(action.breakpoint!.evidence_refs, undefined, action.breakpoint!)}>查看定位证据</Button>
          </section>}
          <Typography.Title level={5}>决定性证明链</Typography.Title>
          {action.decisive_proof_chain.length ? action.decisive_proof_chain.map(evidenceRow) : <Typography.Paragraph type="secondary">当前没有完整的决定性证明；请查看本项判断和全部观察来源。</Typography.Paragraph>}
          <details><summary>全部观察来源与说明边界</summary>
            {action.evidence_explanations.map(evidenceRow)}
            {action.claim_boundary.map((text) => <Typography.Paragraph key={text} type="secondary">{text}</Typography.Paragraph>)}
          </details>
        </> }
    })} />
    {!ordered.length && <Empty description="本次没有可展示的检查项" />}
    <AssistantPanel runId={story.run_id} title="理解本次检查结果" actionLabel="解释已有结果" />
    {story.claim_boundary.map((text) => <Typography.Paragraph key={text} type="secondary">{text}</Typography.Paragraph>)}
    <Drawer title="已发布证据" open={Boolean(detail)} width={640} onClose={() => { requestEpoch.current += 1; setDetail(undefined); setDocuments([]) }}>
      {loading && <Spin tip="正在核验发布证据"><div style={{ minHeight: 80 }} /></Spin>}
      {failed && <Alert showIcon type="error" message="证据未能通过读取或完整性检查，请返回刷新检查结果。" />}
      {!loading && !failed && detail?.source && <Descriptions column={1} layout="vertical" items={[
        { key: 'where', label: '在哪里看到', children: `${detail.source.source_label} · ${detail.source.source_location}` },
        { key: 'what', label: '看到什么', children: `${phaseLabels[detail.source.observed_fact.phase]}：${stateLabels[detail.source.observed_fact.state]}；${detail.source.observed_fact.closure === 'CLOSED' ? '观察窗口已闭合' : '观察窗口尚未闭合'}` },
        { key: 'supports', label: '因此支持什么', children: detail.source.supports_claim },
        { key: 'limit', label: '不能单独证明什么', children: detail.source.does_not_prove },
      ]} />}
      {documents.map((document) => <section key={document.evidence_id}>
        {detail?.breakpoint && document.trace && <>
          <Typography.Title level={5}>已发布的定位边界</Typography.Title>
          {document.trace.events.filter((event) => [detail.breakpoint?.first_violation_event_id, detail.breakpoint?.range_start_event_id, detail.breakpoint?.range_end_event_id].includes(event.event_id)).map((event) => <Typography.Paragraph key={event.event_id}>{event.source_component} · {event.source_location}</Typography.Paragraph>)}
          {!document.trace.complete && <Typography.Paragraph type="secondary">执行路径不完整，定位精度以本项判断为准。</Typography.Paragraph>}
        </>}
        <Typography.Title level={5}>观察记录</Typography.Title>
        {document.observations.map((item, index) => <Typography.Paragraph key={index}>{phaseLabels[item.phase]} · {stateLabels[item.state]} · {formatTimestamp(item.window_end_us)}</Typography.Paragraph>)}
        <details><summary>证据文件与技术引用</summary><pre className="check-evidence-json">{JSON.stringify(document, null, 2)}</pre></details>
      </section>)}
    </Drawer>
  </>
}
