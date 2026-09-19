// 展示同一已发布检查的要求与证据对应；等级和观察状态均来自服务端。
import { Button } from 'antd'
import type { StoryProofCoverage } from '../../api/currentChecks'
const labels = { CONFIRMED: '已观察到', ABSENT: '闭合观察中未发现', UNKNOWN: '尚不能确认' }

export function ProofCoverage({ rows, onEvidence }: { rows: StoryProofCoverage[]; onEvidence: (row: StoryProofCoverage, refs: string[]) => void }) {
  if (!rows.length) return null
  return <section className="proof-coverage" aria-label="本轮要求与证据对应"><header><p className="editorial-eyebrow">回看证明依据</p><h3>每项要求，由什么证据支持</h3><p className="editorial-muted">以下对应关系保存在本轮记录中，不随当前配置改变。</p></header>
    {rows.map((row, index) => <article className="proof-coverage-row" key={`${row.proof_fingerprint}:${row.effect_id}:${index}`} aria-label={`${row.business_label}的证据对应`}>
      <div><span className="proof-coverage-level">{row.required_level === 'VERDICT_REQUIRED' ? '必要证明' : '辅助材料'}</span><h4>{row.business_label}</h4><p className="editorial-muted">{row.source_label}</p></div>
      <div><strong>{labels[row.observed_state]}</strong>{row.limitations.map(text => <p key={text} className="editorial-muted">{text}</p>)}<div className="proof-coverage-links">
        {!!row.evidence_refs.length && <Button onClick={() => onEvidence(row, row.evidence_refs)}>查看必要证明记录</Button>}
        {!!row.supporting_evidence_refs.length && <Button onClick={() => onEvidence(row, row.supporting_evidence_refs)}>查看辅助观察记录</Button>}
        {!row.evidence_refs.length && !row.supporting_evidence_refs.length && <span className="editorial-muted">本轮没有可查看的对应证据</span>}
      </div></div>
    </article>)}
    <p className="editorial-muted">辅助记录可以补充解释，不能替代必要证明。单项观察状态不等于整轮安全结论。</p>
  </section>
}
