import type {RepairHistoryEvent} from '../../entities/check/api/repairs'
import {date} from '../../shared/lib/format'
import {withReturnDestination,scopedPath} from '../../shared/lib/navigation'
import {ActionLink} from '../../shared/ui/actions'

const labels:Record<RepairHistoryEvent['kind'],string>={FOUND:'首次确认问题',CHECKED:'再次检查',VERIFIED:'原问题验证通过',RECURRED:'问题再次出现',CONDITIONS_CHANGED:'检查条件已变化',CHECK_PENDING:'复验尚未完成',CHECK_INTERRUPTED:'复验已中断'}
const observed=(event:RepairHistoryEvent)=>!['CHECK_PENDING','CHECK_INTERRUPTED'].includes(event.kind)

export function IssueHistory({events,origin}:{events:RepairHistoryEvent[];origin:string}){
 // 事件来自修复投影；只呈现已有事实，不用浏览器中最近一轮的结果推断问题状态。
 const rows=[...events].sort((a,b)=>a.created_at_us-b.created_at_us)
 if(!rows.length)return null
 const row=(event:RepairHistoryEvent,index:number)=>{
  const previous=rows.slice(0,index).reverse().find(item=>observed(item)&&item.run_id!==event.run_id)
  return <li key={event.run_id+':'+event.kind+':'+event.created_at_us}><div><strong>{labels[event.kind]}</strong><time>{date(event.created_at_us)}</time></div><div>
   <ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/reports?run_id='+encodeURIComponent(event.run_id),origin))} kind="quiet">阅读这次记录</ActionLink>
   {previous&&observed(event)&&<ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/reports?'+new URLSearchParams({view:'compare',baseline:previous.run_id,current:event.run_id}),origin))} kind="quiet">与上次观察比较</ActionLink>}
  </div></li>
 }
 return <section className="jj-issue-history"><h3>连续检查记录</h3><ol>{row(rows[rows.length-1],rows.length-1)}</ol>{rows.length>1&&<details><summary>查看更早的 {rows.length-1} 次记录</summary><ol>{rows.slice(0,-1).map(row)}</ol></details>}<p className="jj-small jj-muted">未完成或中断的复验保留记录，不计为修复；比较仍会核对身份、资源与检查要求。</p></section>
}
