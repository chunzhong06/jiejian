// 各权限工作面共用只读阶段外观；当前阶段和完成事实均由所在工作面传入。
import { useContext, useEffect } from 'react'
import { WorkPageVisible } from '../runtime/visibility'
import './rule-preparation-stages.css'
export function RulePreparationStages({ phase, complete = false, attention = false, connectionPhase }: {
  phase: number; complete?: boolean; attention?: boolean; note?: string; connectionPhase?: 0 | 1
}) {
  // 接入中的目录选择和只读授权共用一个阶段；批准仍由独立提案决定，不因阶段合并自动放行。
  const labels = ['接入应用', '核对业务', '整理权限要求', '审阅并批准']
  const current = connectionPhase !== undefined ? 0 : Math.min(phase + 1, 3)
  const visible = useContext(WorkPageVisible)
  useEffect(() => {
    if (!visible) return
    // 四阶段共用页首落点；等保留页恢复位置后再定位，不让下方表单焦点拉走视口。
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
  </div>
}
