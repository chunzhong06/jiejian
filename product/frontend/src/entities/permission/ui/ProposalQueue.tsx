import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'
import type {BoundaryEditorDto} from '../api/businessBoundaries'
import type {RuleCandidateContext} from '../api/ruleCandidates'
import {Button} from '../../../shared/ui/actions'
import {SectionHeading} from '../../../shared/ui/layout'
import './ProposalQueue.css'

/** 待审提案是可选择的业务事项；摘要和时间区分原对象，打开仍由原审阅用例负责。 */
export function ProposalQueue({items,busy=false,onReview}:{items:BoundaryEditorDto['pending_proposals'];busy?:boolean;onReview:(id:string)=>void}){
  if(!items.length)return null
  return <section className="jj-proposal-queue" aria-label="待审阅的权限变更"><SectionHeading title="待审阅的权限变更" appearance="group" meta={items.length+' 份'}/>
    <div>{items.map((item,index)=>{
      const summary=item.change_summary,parts:string[]=[]
      if(summary){
        if(summary.new_actor_count)parts.push(`新增 ${summary.new_actor_count} 个角色`)
        if(summary.new_action_count)parts.push(`新增 ${summary.new_action_count} 项操作`)
        const rules=summary.permission_updates.length+summary.permission_retirements.length
        if(rules)parts.push(`调整 ${rules} 条访问要求`)
        const definitions=summary.business_revision_updates.length+summary.retirements.length
        if(definitions)parts.push(`调整 ${definitions} 项业务定义`)
      }
      return <Button kind="quiet" className="jj-proposal-queue-row" key={item.proposal_id} disabled={busy} onClick={()=>onReview(item.proposal_id)}>
        <span><strong>{parts.join('，')||'核对权限与业务定义的变更'}</strong><small>第 {index+1} 份 · {new Date(item.created_at_us/1000).toLocaleString('zh-CN',{hour12:false})}</small></span><span>审阅<ArrowRightOutlined aria-hidden="true"/></span>
      </Button>
    })}</div>
  </section>
}

/** 原业务要求和待批准提案分组阅读；继续时带回要求的准确修订。 */
export function RequirementQueue({items,busy=false,onReview}:{items:RuleCandidateContext['candidates'];busy?:boolean;onReview:(id:string,revision:number)=>void}){
  const pending=items.filter(item=>!item.decision&&!item.visibility?.archived)
  if(!pending.length)return null
  return <section className="jj-proposal-queue" aria-label="待整理的业务要求"><SectionHeading title="待整理的业务要求" appearance="group" meta={pending.length+' 项'}/><div>{pending.map(item=><Button kind="quiet" className="jj-proposal-queue-row" key={item.candidate_id} disabled={busy} onClick={()=>onReview(item.candidate_id,item.revision)}><span><strong>{item.original_text.trim()||'核对业务访问要求'}</strong><small>第 {item.revision} 修订 · {new Date(item.created_at_us/1000).toLocaleString('zh-CN',{hour12:false})}</small></span><span>整理<ArrowRightOutlined aria-hidden="true"/></span></Button>)}</div></section>
}
