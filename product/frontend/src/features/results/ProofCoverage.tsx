// 按必要与辅助等级展示已发布证明摘要；不把来源记录或未闭合观察提升为安全结论。
import { Button } from 'antd'
import type { StoryProofCoverage } from '../../api/currentChecks'
const labels = { CONFIRMED: '已观察到', ABSENT: '闭合观察中未发现', UNKNOWN: '尚不能确认' }

export function ProofCoverage({ rows, onEvidence }: { rows: StoryProofCoverage[]; onEvidence: (row: StoryProofCoverage, refs: string[]) => void }) {
  if (!rows.length) return null
  return <section className="result-proof-coverage" aria-label="本轮要求与证据对应">
    {rows.map((row, index) => <article className="result-proof-row" key={`${row.proof_fingerprint}:${row.effect_id}:${index}`} aria-label={`${row.business_label}的证据对应`}>
      <div className="result-proof-title"><h4>{row.business_label}</h4><span>{row.required_level === 'VERDICT_REQUIRED' ? '必要证明' : '辅助材料'}</span></div>
      <p><strong>{labels[row.observed_state]}</strong>{row.source_label !== row.business_label && <span> · {row.source_label}</span>}</p>
      {row.limitations.map(text => <p key={text} className="editorial-muted">{text}</p>)}
      <div className="result-proof-links">
        {!!row.evidence_refs.length && <Button type="link" onClick={() => onEvidence(row, row.evidence_refs)}>查看必要证明记录 →</Button>}
        {!!row.supporting_evidence_refs.length && <Button type="link" onClick={() => onEvidence(row, row.supporting_evidence_refs)}>查看辅助观察记录 →</Button>}
        {!row.evidence_refs.length && !row.supporting_evidence_refs.length && <span className="editorial-muted">本轮没有可查看的对应证据</span>}
      </div>
    </article>)}
  </section>
}
