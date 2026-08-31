// 普通结果与展示模式共享的事实链；只翻译 ResultPresentation，不重新计算安全结论。

import { Tag, Typography } from 'antd'
import type { ResultPresentationIssueDto } from '../../api/results'

function conclusionLabel(issue: ResultPresentationIssueDto) {
  if (issue.verdict === 'VULNERABLE') return '发现权限问题'
  if (issue.verdict === 'INCONCLUSIVE') return '证据不足'
  return '符合当前权限规则'
}

export function ResultFactChain({ issue, presentation = false }: {
  issue: ResultPresentationIssueDto
  presentation?: boolean
}) {
  const facts = [
    { key: 'rule', label: '人确认的权限规则', value: issue.expectation },
    { key: 'identity', label: '目标实际识别的账号', value: issue.actual_identity_status === 'UNAVAILABLE' ? '现有证据无法独立确认' : issue.actual_identity_label || '现有证据无法独立确认' },
    { key: 'surface', label: '页面或接口怎样回应', value: issue.surface_result },
    { key: 'effect', label: '后台真实发生了什么', value: issue.actual_result },
  ]
  return <section className={`result-fact-chain${presentation ? ' is-presentation' : ''}`} aria-label="权限规则到真实结果的完整链路">
    <div className="result-fact-chain-track">{facts.map((fact, index) => <article className={`result-fact-node is-${fact.key}`} key={fact.key}>
      <span className="result-fact-index" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
      <Typography.Text type="secondary">{fact.label}</Typography.Text>
      <Typography.Text strong>{fact.value}</Typography.Text>
    </article>)}</div>
    <article className={`result-fact-conclusion is-${issue.verdict.toLowerCase()}`}>
      <div><Typography.Text type="secondary">界鉴根据正式证据发布的结论</Typography.Text><Typography.Title level={presentation ? 2 : 4}>{issue.conclusion}</Typography.Title></div>
      <Tag>{conclusionLabel(issue)}</Tag>
      <Typography.Paragraph>{issue.claim_boundary?.supported_statement || issue.explanation}</Typography.Paragraph>
    </article>
  </section>
}
