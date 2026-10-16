// 按必要与辅助等级展示已发布证明摘要；不把来源记录或未闭合观察提升为安全结论。
import { Button } from 'antd'
import type { StoryProofCoverage } from '../../../api/checks/currentChecks'
import { effectSentence, effectScope, effectTopic } from './resultLanguage'

export function ProofCoverage({ rows, onEvidence }: { rows: StoryProofCoverage[]; onEvidence: (row: StoryProofCoverage, refs: string[]) => void }) {
  if (!rows.length) return null
  return <section className="result-proof-coverage" aria-label="本轮实际结果与证据">
    {rows.map((row, index) => <article className="result-proof-row" key={`${row.proof_fingerprint}:${row.effect_id}:${index}`} aria-label={`${row.business_label}的证据对应`}>
      <div className="result-proof-title"><h4>{effectTopic(row.business_label)}</h4><span>{row.required_level === 'VERDICT_REQUIRED' ? '判断所需证据' : '辅助材料'}</span></div>
      <div className="result-proof-reading"><p className="result-proof-outcome"><strong>{effectSentence(row.business_label, row.observed_state)}</strong></p><p>{effectScope(row.observed_state)}</p>{row.source_label !== row.business_label && <p>证据来自：{row.source_label}</p>}
        {row.limitations.map(text => <p key={text} className="editorial-muted">{text}</p>)}
      </div>
      <div className="result-proof-links">
        {!!row.evidence_refs.length && <Button type="link" onClick={() => onEvidence(row, row.evidence_refs)}>查看判断所用记录</Button>}
        {!!row.supporting_evidence_refs.length && <Button type="link" onClick={() => onEvidence(row, row.supporting_evidence_refs)}>查看辅助观察记录</Button>}
        {!row.evidence_refs.length && !row.supporting_evidence_refs.length && <span className="editorial-muted">本轮没有可查看的对应证据</span>}
      </div>
    </article>)}
  </section>
}
