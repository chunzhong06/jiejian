import type {ResultStory} from '../../../entities/check/api/currentChecks'
import {ActionLink,Button} from '../../../shared/ui/actions'
import {scopedPath,withReturnDestination} from '../../../shared/lib/navigation'

const kinds={PERMISSION:'权限边界',NORMAL:'正常功能',REPAIR:'原题修复',UNCHECKED:'本次未执行',UNRESOLVED:'业务待核对',RUNTIME:'运行对应'}

export function DeliverySummary({story,origin,onInspect,readOnly=false}:{story:ResultStory;origin:string;onInspect:(id:string)=>void;readOnly?:boolean}){
  const items=story.delivery_summary
  if(!items?.length)return null
  const labels=new Map(items.filter(item=>item.kind==='NORMAL'||item.kind==='PERMISSION')
    .flatMap(item=>item.case_ids.map(id=>[id,item.label] as const)))
  return <details className="jj-delivery-summary">
    <summary>本次交付摘要</summary>
    <p className="jj-small jj-muted">按这次报告列出检查、正常功能、修复及待处理项。每项保留原依据。</p>
    <div className="jj-scroll-table"><table className="jj-content-table">
      <thead><tr><th>内容</th><th>本次结果</th><th>依据</th></tr></thead>
      <tbody>{items.map((item,index)=><tr key={index}>
        <td>{kinds[item.kind]}<small className="jj-table-secondary">{item.label}</small></td>
        <td>{item.kind==='REPAIR'&&item.result==='VERIFIED'?'原题修复已验证':item.result}</td>
        <td>
          {item.case_ids.length===1&&<Button kind="quiet" onClick={()=>onInspect(item.case_ids[0])}>阅读本项事实</Button>}
          {item.case_ids.length>1&&<details><summary>阅读本次 {item.case_ids.length} 项事实</summary>
            <ul>{item.case_ids.map((id,position)=><li key={id}><Button kind="quiet" onClick={()=>onInspect(id)}>{labels.get(id)??'本次检查项 '+(position+1)}</Button></li>)}</ul>
          </details>}
          {item.source_run_id&&<ActionLink href={'#'+scopedPath(withReturnDestination('/reports?run_id='+item.source_run_id+(item.source_case_id?'&case_id='+item.source_case_id:''),origin),story.project_id)}>阅读原问题</ActionLink>}
          {item.review_url&&!readOnly&&<ActionLink href={'#'+scopedPath(withReturnDestination(item.review_url,origin),story.project_id)}>{item.kind==='UNCHECKED'?'核对要求并安排检查':'继续核对这项业务'}</ActionLink>}{item.source_key&&<details><summary>原事项引用</summary><code>{item.source_key}</code></details>}{item.permission&&(item.case_ids.length?<small className="jj-table-secondary">本次冻结要求 · 修订 {item.permission.revision}</small>:<details>
            <summary>查看准确要求引用</summary><p className="jj-small">修订 {item.permission.revision}</p><code>{item.permission.intent_id}</code><p className="jj-small">内容摘要：{item.permission.intent_hash}</p>
          </details>)}
        </td>
      </tr>)}</tbody>
    </table></div>
  </details>
}
