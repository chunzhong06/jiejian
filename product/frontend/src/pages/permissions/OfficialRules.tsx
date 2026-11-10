import {useMilestone} from '../../shared/lib/milestone'
import {useState} from 'react'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'
import {experienceApi,type OfficialBoundaryDraftDto} from '../../entities/application/api/experience'
import type {BoundaryProposalDto} from '../../entities/permission/api/businessBoundaries'
import {assertProject} from '../../shared/model/page'
import {useRead} from '../../shared/lib/useRead'
import {scopedPath,returnDestinationLabel} from '../../shared/lib/navigation'
import {Button,ActionLink} from '../../shared/ui/actions'
import {Choice} from '../../shared/ui/Choice'
import {Badge,ErrorNote,Loading,Notice} from '../../shared/ui/feedback'
import {Heading,ObjectIdentity} from '../../shared/ui/layout'
import './official-rules.css'

/** 只比较实际展示的整份命令；服务端内容变化时转回完整提案审阅。 */
export function matchesOfficialDraft(draft:OfficialBoundaryDraftDto,proposal:BoundaryProposalDto){
  const canonical=(value:unknown):unknown=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).sort(([a],[b])=>a.localeCompare(b)).map(([key,item])=>[key,canonical(item)])):value
  return draft.project_id===proposal.project_id&&(['proposed_actors','proposed_actions','proposed_permissions','unresolved_questions','provenance'] as const).every(key=>JSON.stringify(canonical(draft.command[key]))===JSON.stringify(canonical(proposal[key])))
}

export function OfficialRules({projectId,name,busy,uncertain,pending,onApprove,onReview,onRecover}:{projectId:string;name:string;busy:boolean;uncertain:boolean;pending:{proposal_id:string}[];onApprove:(draft:OfficialBoundaryDraftDto,choice:boolean)=>Promise<void>;onReview:(id:string)=>void;onRecover:()=>void}){
  const key='jiejian.studio.official-choice:'+projectId
  const [choice,setChoice]=useState(()=>sessionStorage.getItem(key)!=='DENY')
  const read=useRead(`official-rules:${projectId}:${choice}`,async()=>{const value=await experienceApi.boundaryDraft(choice);assertProject(value.project_id,projectId);return value})
  const draft=read.data,command=draft?.command
  const actors=new Map(command?.proposed_actors.map(item=>[item.item_id,item]))
  const actions=new Map(command?.proposed_actions.map(item=>[item.item_id,item]))
  return <div className="jj-official-rules-review">
    <div className="jj-back-link"><ActionLink kind="quiet" href={'#'+scopedPath('/environment',projectId)}><ArrowLeftOutlined aria-hidden="true"/>返回官方示例</ActionLink></div>
    <Heading title={`确认${name}的访问规则`}/>
    <p className="jj-muted">示例已启动。核对预置规则，批准后继续准备检查材料。</p>
    {read.error&&<ErrorNote error={read.error}/>}
    {uncertain&&<Notice tone="caution">上次提交的结果尚未确认。先读取待审提案，避免重复提交。<Button busy={busy} onClick={onRecover}>读取待审提案</Button></Notice>}
    {pending.length>0&&<div className="jj-official-pending"><p>已有待审提案，可以从原记录继续。</p>{pending.map(item=><Button kind="quiet" key={item.proposal_id} disabled={busy} onClick={()=>onReview(item.proposal_id)}>继续审阅原提案</Button>)}</div>}
    {!command?(!read.error&&<Loading>正在读取预置访问规则</Loading>):<>
      <section className="jj-official-rule-section" aria-label="示例权限要求"><ObjectIdentity name={<h2>示例权限要求</h2>} status={<Badge tone="accent">待你确认</Badge>}/>
        <table className="jj-content-table jj-official-rule-table" aria-label="示例权限要求"><colgroup><col/><col/><col/></colgroup><thead><tr><th scope="col">谁可以做什么</th><th scope="col" className="jj-table-state">数据范围</th><th scope="col" className="jj-table-state">访问要求</th></tr></thead><tbody>{command.proposed_permissions.map(rule=>{
          const actor=actors.get(rule.subject_actor_item_id),owner=actors.get(rule.resource_owner_actor_item_id),action=actions.get(rule.business_action_item_id)
          const scope=rule.relation==='OWNS'?'自己的资源':rule.relation==='SAME_ROLE_OTHER_ACCOUNT'?`其他${owner?.display_name??'同角色'}账号的资源`:`${owner?.display_name??'指定所有者'}的资源`
          const title=(actor?.display_name??'操作主体')+(action?.display_name??'业务操作')
          return <tr key={rule.item_id}><th scope="row"><strong>{title}</strong><small>{action?.effect_catalog.filter(effect=>rule.protected_effect_item_ids.includes(effect.item_id)).map(effect=>effect.business_label).join('；')}</small></th><td className="jj-table-state" data-label="数据范围">{scope}</td><td className="jj-table-state" data-label="访问要求">{rule.item_id===draft!.choice_permission_item_id?<Choice align="center" className="jj-table-choice" aria-label={title+'的访问要求'} value={choice?'ALLOW':'DENY'} disabled={busy||uncertain||read.loading} onValueChange={value=>{const next=value==='ALLOW';setChoice(next);sessionStorage.setItem(key,value)}}><option value="ALLOW">允许</option><option value="DENY">禁止</option></Choice>:rule.expectation==='ALLOW'?'允许':'禁止'}</td></tr>
        })}</tbody></table>
      </section>
      <details className="jj-official-definitions"><summary>角色与业务定义</summary>{command.proposed_actors.map(actor=><p key={actor.item_id}><strong>{actor.display_name}</strong> · {actor.description}</p>)}{command.proposed_actions.map(action=><p key={action.item_id}><strong>{action.display_name}</strong> · {action.description}</p>)}</details>
      <p className="jj-small jj-muted">批准后，这些要求成为检查依据。调整访问要求会改变判断标准，示例程序仍沿用当前源码。</p>
      <footer className="jj-official-rule-actions"><p className="jj-small jj-muted">批准完成后，继续准备示例账号、操作和结果证明。</p><div className="jj-inline-actions"><ActionLink href={'#'+scopedPath('/environment',projectId)}>返回示例</ActionLink><Button kind="primary" busy={busy} disabled={uncertain||read.loading||!command.proposed_permissions.length} onClick={()=>void onApprove(draft!,choice)}>批准规则并继续</Button></div></footer>
    </>}
  </div>
}

export function OfficialRulesReady({projectId,origin,onRules}:{projectId:string;origin:string|null;onRules:()=>void}){
  const completion=useMilestone<HTMLDivElement>('rules:'+projectId,true,'rules')
  return <div ref={completion} className="jj-official-rules-review"><Heading title="示例规则已确认"/><ObjectIdentity name={<h2>访问规则已生效</h2>} status={<Badge tone="positive">已批准</Badge>}/><p data-milestone-part="facts" className="jj-official-ready-copy">接下来准备示例账号、操作和业务结果证明。先核对本次准备的范围，再开始执行。</p><footer data-milestone-part="actions" className="jj-task-actions"><Button kind="quiet" onClick={onRules}>查看访问规则</Button><ActionLink kind="primary" href={'#'+scopedPath(origin??'/preparation?prepare_example=1',projectId)}>{origin?returnDestinationLabel(origin):'准备示例材料'}<ArrowRightOutlined aria-hidden="true"/></ActionLink></footer></div>
}
