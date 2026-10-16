// 汇总后端逐动作准备事实；查看其他动作不改变唯一主任务或完整检查门槛。
import { Button } from 'antd'
import type { PreparationGuidance } from '../../../api/preparation/preparationGuidance'
import { materialSuggestionNames } from './MaterialSuggestions'
import './materials.css'

export function PreparationProgress({ progress, currentActionId, selectedActionId, onSelect }: {
  progress: NonNullable<PreparationGuidance['progress']>; currentActionId?: string | null
  selectedActionId?: string; onSelect: (id: string) => void
}) {
  if (!progress.total_actions) return null
  return <section className="preparation-progress" aria-label="全部动作准备进度">
    <div className="material-suggestion-heading"><h2>本轮准备进度</h2><span>{progress.completed_actions} / {progress.total_actions} 项业务材料齐备</span></div>
    <p className="editorial-muted">已齐备的材料会保留。先处理标注“当前待办”的动作；材料齐备后仍需核对完整检查条件。</p>
    <div className="preparation-progress-table"><table>
      <thead><tr><th>业务动作</th><th>材料齐备</th><th>仍需处理</th><th>查看</th></tr></thead>
      <tbody>{progress.actions.map(action => <tr key={action.action_id} aria-current={action.action_id === selectedActionId ? 'true' : undefined}>
        <th scope="row">{action.label}{currentActionId === action.action_id && <small>当前待办</small>}</th>
        <td>{action.satisfied} / {action.required}</td>
        <td>{action.preparation_complete ? '材料已齐备' : action.remaining_kinds.length ? action.remaining_kinds.map(kind => materialSuggestionNames[kind]).join('、') : '材料已齐备，仍需核对允许操作及对应规则'}</td>
        <td><Button type="link" onClick={() => onSelect(action.action_id)}>{action.action_id === selectedActionId ? '正在查看' : '查看材料'}</Button></td>
      </tr>)}</tbody>
    </table></div>
  </section>
}
