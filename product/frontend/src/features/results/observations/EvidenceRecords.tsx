// 按操作阶段排列已经筛选的发布记录；恢复单独展示，不覆盖操作后的观察。
import type { CheckObservation } from '../../../api/checks/currentChecks'
import { formatTimestamp } from '../../../shared/format/time'
import { phaseLabels } from './observationPresentation'

const stages: { label: string; phases: CheckObservation['phase'][] }[] = [
  { label: '操作前', phases: ['BASELINE', 'BEFORE'] },
  { label: '操作后', phases: ['AFTER', 'EVENTUAL'] },
  { label: '恢复后', phases: ['RECOVERY'] },
]

export function EvidenceRecords({ records, reading }: {
  records: CheckObservation[]
  reading: (record: CheckObservation) => { label: string }
}) {
  return <section className="evidence-observations" aria-label="观察记录">
    <h5>观察记录</h5>
    <div className="evidence-stage-grid">
      {stages.map(stage => {
        const values = records.filter(record => stage.phases.includes(record.phase))
        if (!values.length) return null
        return <section key={stage.label} className="evidence-stage" aria-label={stage.label}>
          <h4>{stage.label}{values.length === 1 && phaseLabels[values[0].phase] !== stage.label ? ` · ${phaseLabels[values[0].phase]}` : ''}</h4>
          <ol>{values.map((record, index) => <li key={`${record.observer_id}:${record.phase}:${record.window_end_us}:${index}`}>
            {values.length > 1 && phaseLabels[record.phase] !== stage.label && <span className="evidence-phase">{phaseLabels[record.phase]}</span>}
            <strong>{reading(record).label}</strong>
            <time>{formatTimestamp(record.window_end_us)}</time>
          </li>)}</ol>
        </section>
      })}
    </div>
    {!records.length && <p className="editorial-muted">这份证据没有对应本项要求的观察记录。</p>}
  </section>
}
