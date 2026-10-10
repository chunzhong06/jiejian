// 各权限工作面共用只读阶段外观；当前阶段和完成事实均由所在工作面传入。
import { useContext, useEffect } from 'react'
import { WorkPageVisible } from '../runtime/visibility'
import './rule-preparation-stages.css'
export function RulePreparationStages({ phase, complete = false, attention = false, note, connectionPhase }: {
  phase: number; complete?: boolean; attention?: boolean; note?: string; connectionPhase?: 0 | 1
}) {
  const labels = ['接入应用', '授权分析', '核对业务', '整理候选', '审阅提案', '批准生效']
  const current = connectionPhase ?? phase + 2
  const visible = useContext(WorkPageVisible)
  useEffect(() => {
    if (!visible) return
    // 六步共用页首落点；等保留页恢复位置后再定位，不让下方表单焦点拉走视口。
    const frame = requestAnimationFrame(() => {
      document.getElementById('main-content')?.focus({ preventScroll: true })
      window.scrollTo({ top: 0, behavior: 'instant' })
    })
    return () => cancelAnimationFrame(frame)
  }, [visible, current])
  return <div className="rule-preparation-progress">
    <ol className="rule-preparation-stages" aria-label="权限整理阶段">{labels.map((label, index) => {
      const state = complete || index < current ? 'complete' : index === current ? attention ? 'attention' : 'current' : 'waiting'
      const explanation = `${label} · ${state === 'complete' ? '已完成' : state === 'attention' ? '需要核对' : state === 'current' ? '当前阶段' : '等待前序完成'}`
      return <li key={label} data-state={state} aria-current={index === current ? 'step' : undefined} aria-label={explanation} title={explanation}>
        <span className="rule-stage-mark" aria-hidden/>
        <span className="rule-stage-label">{index + 1} · {label}</span>
      </li>
    })}</ol>
    <p key={`${current}:${complete}:${attention}`} className="rule-stage-current"><span>第 {current + 1} / 6 阶段 · {note ?? (complete ? '本轮整理已完成' : attention ? '需要补充后继续' : '当前阶段')}</span></p>
  </div>
}
