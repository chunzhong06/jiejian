// 缺口提示共用主次与操作布局；事实和跳转目标由调用方提供，不改变检查门禁。
import { Alert, Button } from 'antd'
import type { BoundaryReviewGap } from '../../api/boundaries/ruleCandidates'
import './requirement-notice.css'

export function RequirementNotice({gaps, purpose, disabled=false, onOpen, listedCandidateIds=[]}: {
  gaps:BoundaryReviewGap[]; purpose:'candidate'|'check'; disabled?:boolean; onOpen:(gap:BoundaryReviewGap)=>void;listedCandidateIds?:string[]
}) {
  // 当前列表已有可见候选时由该行承担入口；归档或未列出的缺口仍保留可达提示。
  const visible=gaps.filter(gap=>!listedCandidateIds.includes(gap.candidate_id))
  if (!visible.length) return null
  const groups=Array.from(new Set(visible.map(gap=>gap.candidate_id))).map(id=>({gap:visible.find(gap=>gap.candidate_id===id)!,count:visible.filter(gap=>gap.candidate_id===id).length}))
  return <Alert className="requirement-notice" data-purpose={purpose} type="warning" message={
    <div className="requirement-notice-heading"><div><h3>{purpose==='check'?'本轮暂不能开始检查':'有候选需要继续核对'}</h3><p>{groups.length} 份候选 · {visible.length} 项待处理。{purpose==='check'?'从对应入口集中处理，完成后重新读取检查范围。':'进入候选统一处理；归档不会清除缺口。'}</p></div>{groups.length===1&&<Button type="link" disabled={disabled} onClick={()=>onOpen(groups[0].gap)}>{purpose==='check'?(groups[0].gap.next_label??'返回候选处理'):'继续核对'} →</Button>}</div>
  } description={groups.length>1?<details className="requirement-notice-groups"><summary>选择要处理的候选</summary>{groups.map(({gap,count},index)=><div className="requirement-notice-item" key={gap.candidate_id}><span>{index+1}</span><p>修订 {gap.revision} · {count} 项待处理</p><Button type="link" disabled={disabled} onClick={()=>onOpen(gap)}>打开候选 →</Button></div>)}</details>:undefined}/>
}
