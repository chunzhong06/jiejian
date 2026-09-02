// 把单条 ResultPresentation 收束为唯一判定、决定性证据和断裂定位，不在前端重算安全结论。

import { Button, Collapse, Typography } from 'antd'
import type { ResultEvidenceExplanationDto, ResultEvidenceSourceDto, ResultPresentationIssueDto } from '../../api/results'
import { occurrenceStatusLabel, severityLabel } from '../../app/presentation'

function resultTone(verdict: ResultPresentationIssueDto['verdict']) {
  return verdict === 'VULNERABLE' ? 'danger' : verdict === 'INCONCLUSIVE' ? 'warning' : 'safe'
}

function resultLabel(verdict: ResultPresentationIssueDto['verdict']) {
  return verdict === 'VULNERABLE' ? '权限问题已确认' : verdict === 'INCONCLUSIVE' ? '暂不能下安全结论' : '当前规则已被验证'
}

function sourceRoleLabel(role: ResultEvidenceSourceDto['role']) {
  return role === 'KEY' ? '关键来源' : '佐证来源'
}

function sourceStatusLabel(status: ResultEvidenceSourceDto['status']) {
  return ({ FOUND: '已发现', NOT_FOUND: '未发现', UNAVAILABLE: '无法确认' } as const)[status]
}

function breakpointTitle(issue: ResultPresentationIssueDto) {
  if (issue.diagnosis?.precision === 'EXACT') return '首个可证明断裂'
  if (issue.diagnosis?.precision === 'RANGE') return '可证明的断裂区间'
  return '当前定位精度'
}

function breakpointDetail(issue: ResultPresentationIssueDto) {
  if (issue.diagnosis?.precision !== 'EXACT') return issue.diagnosis?.summary
  return issue.diagnosis.minimal_witness.find((item) => item.kind === 'BREAKPOINT')?.detail ?? issue.diagnosis.summary
}

function decisiveExplanations(issue: ResultPresentationIssueDto): ResultEvidenceExplanationDto[] {
  const published = issue.evidence_explanations ?? []
  if (published.length === 0) return []
  const surface = published.find((item) => item.source === '执行表面响应')
  const breakpoint = published.find((item) => item.source === '权限断裂定位')
  const keySources = new Set((issue.evidence_sources ?? []).filter((item) => item.role === 'KEY').map((item) => item.label))
  const keyEvidence = published.filter((item) => keySources.has(item.source))
  const ordered = issue.verdict === 'VULNERABLE'
    ? [surface, ...keyEvidence, breakpoint]
    : [surface, ...keyEvidence]
  const remaining = published.filter((item) => !ordered.includes(item))
  return [...ordered, ...remaining].filter((item): item is ResultEvidenceExplanationDto => Boolean(item)).filter((item, index, items) => items.indexOf(item) === index).slice(0, 4)
}

function fallbackEvidence(issue: ResultPresentationIssueDto) {
  return [
    { source: '执行表面响应', location: '本轮目标执行结果记录', label: issue.surface_result, proves: '这项已发布事实说明目标怎样回应本次操作。' },
    { source: issue.verdict === 'INCONCLUSIVE' ? '关键观察缺口' : '真实业务结果', location: '本轮已发布业务结果', label: issue.actual_result, proves: issue.claim_boundary?.supported_statement ?? issue.explanation },
  ]
}

export function ResultDecisionNarrative({
  issue,
  contextLabel = '关键发现',
  onEvidence,
}: {
  issue: ResultPresentationIssueDto
  contextLabel?: string
  onEvidence: () => void
}) {
  const tone = resultTone(issue.verdict)
  const decisive = decisiveExplanations(issue)
  const proofItems = decisive.length > 0 ? decisive : fallbackEvidence(issue)
  // BLOCK 之外不发布断裂定位，避免证据不足或安全结果被误画成已确认断点。
  const breakpoint = issue.verdict === 'VULNERABLE' ? issue.diagnosis : null
  const breakpointEvidence = decisive.find((item) => item.source === '权限断裂定位')
  const impacts = Array.from(new Set((breakpoint?.confirmed_impacts ?? []).map((item) => item.summary)))

  return <article className={`result-decision result-decision-${tone}`} aria-label={issue.title}>
    <header className="result-decision-header">
      <div>
        <Typography.Text className="result-decision-kicker">{contextLabel}</Typography.Text>
        <Typography.Title level={3}>{issue.title}</Typography.Title>
        <Typography.Text type="secondary">{issue.subject_group} · {issue.action} · {issue.resource} · {issue.relation}</Typography.Text>
      </div>
      <div className="result-decision-state">
        <span className={`semantic-state is-${tone}`}>{resultLabel(issue.verdict)}</span>
        <span className="semantic-state">严重程度：{severityLabel(issue.severity)}</span>
      </div>
    </header>

    <section className="result-decision-statement" aria-label="本项判断">
      <Typography.Text type="secondary">本项判断</Typography.Text>
      <Typography.Title level={4}>{issue.claim_boundary?.supported_statement ?? issue.explanation}</Typography.Title>
    </section>

    <div className="result-decision-contrast" aria-label="权限要求、表面响应与真实结果">
      <article><Typography.Text type="secondary">权限要求</Typography.Text><strong>{issue.expectation}</strong></article>
      <article><Typography.Text type="secondary">表面响应</Typography.Text><strong>{issue.surface_result}</strong></article>
      <article className={`is-${tone}`}><Typography.Text type="secondary">{issue.verdict === 'INCONCLUSIVE' ? '尚未确认的真实结果' : '独立观察到的真实结果'}</Typography.Text><strong>{issue.actual_result}</strong></article>
    </div>

    {issue.repair_requirement && <section className="result-repair-contract" aria-labelledby={`result-repair-${issue.finding_id}`}>
      <div><Typography.Text className="result-decision-kicker">修复复验对照</Typography.Text><Typography.Title id={`result-repair-${issue.finding_id}`} level={4}>既要消除违规结果，也要保留合法功能</Typography.Title></div>
      <dl>
        <div><dt>必须消失</dt><dd>{issue.repair_requirement.must_disappear}</dd></div>
        <div><dt>必须保留</dt><dd>{issue.repair_requirement.must_remain}</dd></div>
        {issue.repair_requirement.must_not_change.length > 0 && <div><dt>必须保持</dt><dd>{issue.repair_requirement.must_not_change.join('；')}</dd></div>}
      </dl>
    </section>}

    {breakpoint && <section className="result-breakpoint" aria-label="定位结果">
      <div className="result-breakpoint-heading">
        <div><Typography.Text className="result-decision-kicker">定位结果</Typography.Text><Typography.Title level={4}>{breakpointTitle(issue)}</Typography.Title></div>
        <span className={`semantic-state is-${breakpoint.precision === 'EXACT' ? 'danger' : 'warning'}`}>{breakpoint.precision === 'EXACT' ? '精确位置' : breakpoint.precision === 'RANGE' ? '位置区间' : '只能确认违规'}</span>
      </div>
      <Typography.Paragraph>{breakpointDetail(issue)}</Typography.Paragraph>
      <dl className="result-breakpoint-location">
        <div><dt>发生位置</dt><dd>{breakpoint.precision === 'VIOLATION_ONLY' ? '当前证据没有形成可发布的具体位置' : breakpointEvidence?.location ?? '本轮已发布执行路径'}</dd></div>
        {impacts.length > 0 && <div><dt>已确认影响</dt><dd>{impacts.join('；')}</dd></div>}
      </dl>
    </section>}

    <section className="result-proof" aria-labelledby={`result-proof-${issue.finding_id}`}>
      <div className="result-proof-heading">
        <div><Typography.Title id={`result-proof-${issue.finding_id}`} level={4}>决定性证明链</Typography.Title><Typography.Paragraph type="secondary">每一步都说明在哪里看到、看到什么，以及它支持哪一部分判断。</Typography.Paragraph></div>
        <Button onClick={onEvidence}>查看全部证据与边界</Button>
      </div>
      <ol className="result-proof-list">{proofItems.map((item, index) => <li key={`${item.source}-${index}`}>
        <span className="result-proof-index" aria-hidden="true">{index + 1}</span>
        <div className="result-proof-copy">
          <div><Typography.Text type="secondary">在哪里看到</Typography.Text><strong>{item.location ?? `${item.source}的本轮已发布记录`}</strong></div>
          <div><Typography.Text type="secondary">看到什么</Typography.Text><span>{item.label}</span></div>
          <div><Typography.Text type="secondary">因此支持</Typography.Text><span>{item.proves}</span></div>
        </div>
      </li>)}</ol>
    </section>

    <Collapse className="result-decision-details" items={[{
      key: 'details',
      label: '查看完整诊断、来源状态与可说明范围',
      children: <div className="result-decision-detail-content">
        {breakpoint && <section><Typography.Text strong>完整诊断见证</Typography.Text><ol className="result-diagnosis-witness">{breakpoint.minimal_witness.map((witness, index) => <li key={`${witness.kind}-${index}`}><span className="result-story-step-index" aria-hidden="true">{index + 1}</span><div className="result-diagnosis-witness-copy"><Typography.Text type="secondary">{witness.label}</Typography.Text><Typography.Text strong>{witness.detail}</Typography.Text></div></li>)}</ol></section>}
        <section><Typography.Text strong>全部证据来源</Typography.Text>{(issue.evidence_sources ?? []).length > 0
          ? <ul className="result-source-list">{issue.evidence_sources.map((source) => <li key={`${source.observer_type}-${source.label}`}><div><Typography.Text strong>{source.label}</Typography.Text><Typography.Text type="secondary">{sourceRoleLabel(source.role)}</Typography.Text></div><span className={`semantic-state is-${source.status === 'FOUND' ? 'safe' : source.status === 'UNAVAILABLE' ? 'warning' : 'current'}`}>{sourceStatusLabel(source.status)}</span></li>)}</ul>
          : <Typography.Paragraph type="secondary">本次发布结果没有可展示的观察来源。</Typography.Paragraph>}</section>
        {(issue.claim_boundary?.unsupported_statements ?? []).length > 0 && <section><Typography.Text strong>当前不能据此宣称</Typography.Text><ul>{issue.claim_boundary.unsupported_statements.map((item) => <li key={item}>{item}</li>)}</ul></section>}
      </div>,
    }]} />

    <footer className="result-decision-footer"><span className="semantic-state">{occurrenceStatusLabel(issue.occurrence_status)}</span></footer>
  </article>
}
