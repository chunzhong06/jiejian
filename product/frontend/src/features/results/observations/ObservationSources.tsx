// 每个来源保留全部阶段及精确证据入口；概览不隐藏早期缺口，也不以恢复状态覆盖操作后果。
import { Button } from 'antd'
import type { EvidenceExplanation } from '../../../api/checks/currentChecks'
import { StatusBadge } from '../../../shared/ui/StatusBadge'
import { observationGroups, phaseLabels, sourceLabels, sourceReading } from './observationPresentation'

export function ObservationSources({ sources, onEvidence }: { sources: EvidenceExplanation[]; onEvidence: (source: EvidenceExplanation) => void }) {
  if (!sources.length) return null
  return <section className="result-observation-sources" aria-label="观察来源与阶段">
    <h3>观察来源与阶段</h3>
    <p className="editorial-muted">观察状态描述业务事实，权限结论由本轮完整检查给出；辅助记录不替代必要证明。</p>
    {observationGroups(sources).map(group => {
      const source = group.latest
      const reading = sourceReading(source)
      const name = sourceLabels[source.source_label] ?? source.source_label
      const role = { VERDICT_REQUIRED: '必要证明', SUPPORTING: '辅助观察', DIAGNOSIS_REQUIRED: '诊断记录' }[source.observed_fact.level]
      return <article className="result-observation-source" key={group.key} aria-label={`${name}的阶段记录`}>
        <details className="result-observation-stages"><summary className="result-observation-heading">
          <span className="result-observation-name"><strong>{name}</strong><small>{role}</small></span>
          <span className="result-observation-reading"><StatusBadge kind="lifecycle" tone={reading.attention || reading.kind === 'WAITING' ? 'warning' : 'neutral'}>{reading.label}</StatusBadge>
          {reading.attention && <small>{reading.detail}</small>}
          {!!group.gaps.length && <small className="result-observation-gap">{group.gaps.length} 个阶段有记录缺口</small>}
          </span>
          <span className="result-observation-toggle">查看 {group.stages.length} 个阶段</span>
        </summary>
          {!reading.attention && <p className="editorial-muted">{reading.detail}</p>}
          <ol>{group.stages.map((item,index) => {
            const status = sourceReading(item)
            const phase = phaseLabels[item.observed_fact.phase]
            return <li key={index}><span className="result-observation-phase">{phase}</span><div><strong>{status.label}</strong>{status.detail !== reading.detail && <p>{status.detail}</p>}</div>
              <Button type="link" disabled={!item.evidence_refs.length} aria-label={`查看${name}${phase}记录`} onClick={() => onEvidence(item)}>查看记录</Button>
            </li>
          })}</ol>
        </details>
      </article>
    })}
  </section>
}
