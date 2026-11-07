import {useId,useLayoutEffect,useRef,useState,type ReactNode} from 'react'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import CheckOutlined from '@ant-design/icons/CheckOutlined'
import CloseOutlined from '@ant-design/icons/CloseOutlined'
import type {BoundaryProposalViewDto,BoundaryReviewValueDto} from '../../entities/permission/api/businessBoundaries'
import {conditionLabels} from '../../entities/permission/ui/RuleConditions'
import {fieldMutationLabel} from '../../entities/permission/ui/FieldMutation'
import {text} from '../../shared/lib/format'
import {Button} from '../../shared/ui/actions'
import {Badge,Notice} from '../../shared/ui/feedback'
import {Heading} from '../../shared/ui/layout'
import {Inspector} from '../../shared/ui/Inspector'
import {Tabs} from '../../shared/ui/Tabs'

type ReviewItem=NonNullable<BoundaryProposalViewDto['review']>['items'][number]
const changes={CREATE:'新增',UPDATE:'调整',RETIRE:'停用',REFERENCE:'沿用'}
function resource(value:BoundaryReviewValueDto){
  return value.relation==='OWNS'?'自己的资源':value.relation==='SAME_ROLE_OTHER_ACCOUNT'?`其他${text(value.resource_owner??'同角色')}账号的资源`:`${text(value.resource_owner??'其他角色')}的资源`
}
function itemLabel(item:ReviewItem){
  const value=item.after
  return item.entity_kind==='PERMISSION'?`${text(value.subject??'操作人')}${value.expectation==='ALLOW'?'可以':'不得'}${text(value.action??'执行此操作')}`:text(value.display_name)
}

/** 仅持有阅读选择；整份提案的批准、未知回执和确认仍由 Permissions 持有。 */
export function ProposalReview({value,onBack,children}:{value:BoundaryProposalViewDto;onBack:()=>void;children:ReactNode}){
  const [view,setView]=useState('rules'),[ruleId,setRuleId]=useState(''),[definitionId,setDefinitionId]=useState(''),[detailOpen,setDetailOpen]=useState(false)
  const collection=useRef<HTMLElement>(null),returnFocus=useRef<HTMLButtonElement|null>(null)
  const panelId=useId(),tabId=useId()
  const rules=value.review?.items.filter(item=>item.entity_kind==='PERMISSION')??[]
  const definitions=value.review?.items.filter(item=>item.entity_kind!=='PERMISSION')??[]
  const items=view==='definitions'?definitions:rules
  const current=items.find(item=>item.item_id===(view==='definitions'?definitionId:ruleId))??items[0]
  const select=(id:string)=>{(view==='definitions'?setDefinitionId:setRuleId)(id);setDetailOpen(true)}
  const close=()=>{returnFocus.current=collection.current?.querySelector<HTMLButtonElement>('.jj-object-select[aria-pressed=true]')??null;setDetailOpen(false)}
  useLayoutEffect(()=>{
    // 窄窗关闭详情后先恢复概览，再把键盘焦点交还原条目。
    if(!detailOpen){returnFocus.current?.focus({preventScroll:true});returnFocus.current=null}
    else if(window.matchMedia('(max-width:800px)').matches)collection.current?.querySelector<HTMLButtonElement>('.jj-inspector .jj-button')?.focus({preventScroll:true})
  },[detailOpen])
  const groups=new Map<string,ReviewItem[]>()
  for(const item of items){
    const group=view==='definitions'?(item.entity_kind==='ACTOR'?'业务角色':'业务操作与结果'):text(item.after.action??item.before?.action??'访问规则')
    groups.set(group,[...(groups.get(group)??[]),item])
  }
  const accepted=value.decision?.decision==='APPROVED'
  const status=value.decision?(accepted?'已批准':'已放弃'):'尚未生效'
  return <>
    <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={onBack}>全部权限规则</Button></div>
    <Heading eyebrow={value.decision?'权限变更记录':'权限审阅'} title={value.decision?'查看这次权限变更':'核对规则将如何改变'}>
      <div className="jj-proposal-summary"><Badge tone={value.decision?(accepted?'positive':'neutral'):'accent'}>{status}</Badge><span>{rules.length} 条访问规则</span><span>{definitions.length} 项业务定义</span></div>
    </Heading>
    <div className="jj-proposal-review">
      <Tabs label="权限提案内容" value={view} onValueChange={setView} divider={false} panelId={panelId} idPrefix={tabId} items={[{value:'rules',label:`访问规则 ${rules.length}`},{value:'definitions',label:`业务定义 ${definitions.length}`},{value:'source',label:'提案来源'}]}/>
      <section id={panelId} role="tabpanel" aria-labelledby={tabId+'-'+view} className="jj-proposal-panel">
        {view==='source'?<div className="jj-proposal-source"><h2>提案来源</h2><p>{text(value.proposal.provenance)}</p></div>:<section ref={collection} className="jj-collection jj-proposal-workspace" data-detail-open={Boolean(current)&&detailOpen} aria-label={view==='rules'?'访问规则概览':'业务定义概览'}>
          <div className="jj-collection-layout"><div className="jj-collection-main">
            {items.length?<div className="jj-scroll-table"><table className="jj-object-table"><thead><tr><th scope="col">{view==='rules'?'访问要求与资源':'角色与业务操作'}</th><th scope="col" className="jj-proposal-summary-column">{view==='rules'?'业务结果':'定义内容'}</th><th scope="col" className="jj-table-state">变更</th></tr></thead>
              {[...groups].map(([name,group])=><tbody key={name} aria-label={name}><tr className="jj-proposal-group"><th colSpan={3}>{name}<small>{group.length} 项</small></th></tr>{group.map(item=><tr key={item.item_id} data-selected={detailOpen&&current?.item_id===item.item_id}>
                <th scope="row"><button type="button" className="jj-object-select" aria-pressed={detailOpen&&current?.item_id===item.item_id} onClick={()=>select(item.item_id)}><strong>{itemLabel(item)}</strong><small>{view==='rules'?resource(item.after):(item.entity_kind==='ACTOR'?'业务角色':'业务操作')}</small></button></th>
                <td className="jj-proposal-summary-column">{view==='rules'?item.after.protected_effects.map((effect,index)=><p key={index}>{text(effect)}</p>):text(item.after.description||item.after.effects.map(effect=>effect.business_label).join('、'))||'未补充说明'}</td>
                <td className="jj-table-state"><span className="jj-proposal-change-label">{changes[item.change_kind]}</span></td>
              </tr>)}</tbody>)}
            </table></div>:<p className="jj-proposal-empty jj-muted">这份提案没有{view==='rules'?'调整访问规则':'角色或业务操作定义'}。</p>}
          </div>{current&&detailOpen&&<Inspector identity={view+':'+current.item_id} title={view==='rules'?text(current.after.action??'访问规则'):text(current.after.display_name)} caption={view==='rules'?'当前访问规则':'当前业务定义'} status={<span className="jj-proposal-change-label">{changes[current.change_kind]}</span>} onClose={close}>
            <ReviewChange item={current} accepted={accepted}/>
          </Inspector>}</div>
        </section>}
      </section>
      {children}
    </div>
  </>
}

function ReviewChange({item,accepted}:{item:ReviewItem;accepted:boolean}){
  if(item.change_kind==='UPDATE'||item.change_kind==='RETIRE')return <div className="jj-rule-compare">
    <section><p className="jj-eyebrow">现在</p>{item.basis_available&&item.before?<RuleMeaning value={item.before} retiredLabel="已停用"/>:<Notice tone="caution">原版本不可用，无法核对变化。</Notice>}</section>
    <section><p className="jj-eyebrow">批准后</p><RuleMeaning value={item.after} retiredLabel={accepted?'已停用':'将停用'}/></section>
  </div>
  return <RuleMeaning value={item.after} retiredLabel={accepted?'已停用':'将停用'}/>
}

function RuleMeaning({value,retiredLabel}:{value:BoundaryReviewValueDto;retiredLabel:string}){
  return <article className="jj-rule-meaning">
    {value.expectation?<>
      <div className="jj-rule-definition">
        <div className="jj-rule-title"><span className="jj-rule-direction" aria-hidden="true">{value.expectation==='ALLOW'?<CheckOutlined/>:<CloseOutlined/>}</span><h3>{text(value.subject??'操作人')}{value.expectation==='ALLOW'?'可以':'不得'}{text(value.action??'执行此操作')}</h3></div>
        <p>{resource(value)}</p>
        {conditionLabels(value.conditions).length>0&&<p>{conditionLabels(value.conditions).join('，')}</p>}
      </div>
      <div className="jj-rule-effects"><h3>{value.expectation==='ALLOW'?'允许的业务结果':'禁止的业务结果'}</h3><ul>{value.protected_effects.map((effect,index)=><li key={index}>{text(effect)}</li>)}</ul></div>
    </>:<div className="jj-rule-definition">
      {value.description&&<p>{text(value.description)}</p>}
      {value.resource_concept&&<p>资源：{text(value.resource_concept)}</p>}
      {value.effects.map((effect,index)=><div className="jj-definition-effect" key={index}><h3>{text(effect.business_label)}</h3>{effect.field_mutation&&<p>{fieldMutationLabel(effect.field_mutation)}</p>}{effect.description&&<p>{text(effect.description)}</p>}</div>)}
    </div>}
    {value.effective_state==='RETIRED'&&<p className="jj-proposal-change-label">{retiredLabel}</p>}
  </article>
}
