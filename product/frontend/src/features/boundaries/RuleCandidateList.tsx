// 候选列表按原文、服务端状态和审阅入口分列；摘要不替代完整候选或人工批准。
import { Button } from 'antd'
import type { RuleCandidateContext } from '../../api/boundaries/ruleCandidates'
import { StatusBadge } from '../../shared/ui/StatusBadge'

export function RuleCandidateList({ candidates, archived, onSelect }: {
  candidates: RuleCandidateContext['candidates']; archived: boolean
  onSelect: (id: string, revision: number) => void
}) {
  if (!candidates.length) return null
  return <table className="rule-candidate-table" aria-label={archived ? '已归档规则候选' : '当前规则候选'}>
    <colgroup><col/><col/><col/></colgroup>
    <thead><tr><th scope="col">规则</th><th scope="col">状态</th><th scope="col">审阅</th></tr></thead>
    <tbody>{candidates.map(item => <tr key={item.candidate_id}>
      <td><p className="rule-candidate-excerpt" title={item.original_text}>{item.original_text}</p>
        <p className="rule-candidate-meta">修订 {item.revision} · {new Date(item.created_at_us/1000).toLocaleString('zh-CN')}</p>
        {item.counts && <p className="rule-candidate-meta">{item.counts.actors} 个角色 · {item.counts.actions} 项动作 · {item.counts.permissions} 条权限 · {item.counts.examples} 个具体情形{item.issue_count ? ` · ${item.issue_count} 项待核对` : ''}</p>}
      </td>
      <td data-label="状态"><StatusBadge kind="preparation" tone={item.assessment==='NEEDS_CHANGES'?'warning':'neutral'}>{item.visibility?.archived ? '已归档' : item.decision==='APPROVED' ? '已批准' : item.decision ? '提案已放弃' : item.proposal_id ? '等待批准' : item.assessment==='NEEDS_CHANGES' ? '需要补充' : item.assessment==='ALREADY_CONFIRMED' ? '与当前规则一致' : item.assessment==='REVIEWABLE' ? '可以审阅' : '待读取核对'}</StatusBadge></td>
      <td><Button type="link" onClick={() => onSelect(item.candidate_id, item.revision)}>{archived ? '查看与恢复' : item.assessment==='NEEDS_CHANGES' ? '查看缺口' : '审阅'}</Button></td>
    </tr>)}</tbody>
  </table>
}
