import type {SourceChangeViewDto} from '../api/sourceChanges'
import {ActionLink} from '../../../shared/ui/actions'
import {Badge} from '../../../shared/ui/feedback'
import {scopedPath,withReturnDestination} from '../../../shared/lib/navigation'

type Material=NonNullable<SourceChangeViewDto['continuation']>['materials'][number]
const materialNames={identity:'测试账号',execution:'操作流程',resource:'测试资源',evidence:'结果证明',recovery:'恢复方式'}
const handlingLabels={KEEP:'可继续使用',ADD:'需要补充',RECHECK:'需要重新核对',DECIDE:'需要你决定'}
const materialName=(item:Material)=>item.member_label||materialNames[item.kind]
const handlingKey=(item:Material)=>JSON.stringify([item.handling,item.status,item.explanation,item.next_step])

function MaterialRows({items,shared,commonStep}:{items:Material[];shared?:Map<Material,string[]>;commonStep:string|null}){
  // 不同材料保留各自的状态；只有共同核对方式集中说明，避免多个名称共用一个模糊状态。
  return <>{items.map((item,index)=><tr key={index}>
    <th scope="row"><strong>{materialName(item)}</strong>{item.member_label&&item.member_label!==materialNames[item.kind]&&<small>{materialNames[item.kind]}</small>}{shared?.has(item)&&<small>用于：{shared.get(item)!.join('、')}</small>}</th>
    <td className="jj-change-material-state"><Badge tone={item.handling==='KEEP'?'neutral':'caution'}>{handlingLabels[item.handling]}</Badge></td>
    <td><p>{item.explanation}</p>{item.next_step&&item.next_step!==commonStep&&<p className="jj-change-material-next">{item.next_step}</p>}</td>
  </tr>)}</>
}

function MaterialColumns(){
  return <><colgroup><col/><col/><col/></colgroup><thead><tr><th>检查材料</th><th>当前安排</th><th>处理说明</th></tr></thead></>
}

/** 当前处理计划与登记时的影响分开阅读；所有编辑和执行回到原能力入口。 */
export function ChangeContinuation({value,origin}:{value:SourceChangeViewDto;origin:string}){
  const plan=value.continuation
  if(!plan)return null
  const project=value.manifest.project_id
  const href=(path:string)=>'#'+scopedPath(withReturnDestination(path,origin),project)
  // 只有准确账号、名称及处理事实相同才归并；相似角色名不能代表同一个账号。
  const identities=new Map<string,Material[]>()
  for(const item of plan.materials)if(item.kind==='identity'&&item.member_id){
    const key=JSON.stringify([item.member_id,item.member_label,handlingKey(item),item.reason_codes])
    identities.set(key,[...(identities.get(key)??[]),item])
  }
  const shared=[...identities.values()].filter(items=>new Set(items.map(item=>item.action_id)).size>1)
  const sharedItems=new Set(shared.flat()),individual=plan.materials.filter(item=>!sharedItems.has(item))
  const actions=[...new Set(individual.map(item=>item.action_id))]
  const sharedUses=new Map(shared.map(items=>[items[0],[...new Set(items.map(item=>item.action_label))]]))
  const steps=[...new Set(plan.materials.map(item=>item.next_step))]
  const commonStep=steps.length===1&&steps[0]?steps[0]:null
  return <details className="jj-change-continuation"><summary>当前要求与材料的核对依据</summary><div><p>{plan.next_step}</p>
      <section className="jj-change-basis-group"><h3 className="jj-title-group">关联要求</h3><div className="jj-scroll-table"><table className="jj-content-table"><thead><tr><th>关联要求</th><th>当前标准</th><th>源码影响</th><th>继续位置</th></tr></thead><tbody>{plan.requirements.map(item=><tr key={item.permission.intent_id}><td>{item.action_label}<small className="jj-table-secondary">登记时修订 {item.permission.revision}</small></td><td>{item.status==='CURRENT'?'保持一致':item.status==='CHANGED'?'已有新修订':'已移出当前标准'}</td><td>{item.classification==='DIRECTLY_AFFECTED'?'有直接变化证据':item.classification==='MAPPING_REVIEW_REQUIRED'?'需要核对实现对应':'尚无直接映射'}{item.relevant_paths.map(path=><small className="jj-table-secondary" key={path}>{path}</small>)}</td><td><ActionLink href={href('/permissions?rule_id='+item.permission.intent_id)}>核对要求与验证方式</ActionLink></td></tr>)}</tbody></table></div>
      {plan.added_requirements.length>0&&<p>另有 {plan.added_requirements.length} 项新增要求，可独立安排；原题仍按准确引用核对。</p>}
      </section>
      {shared.length>0&&<section className="jj-change-basis-group jj-change-material-section"><header><h3 className="jj-title-group">共用测试账号</h3><p>这些账号由多项操作共用，在账号准备中统一核对。</p></header><div className="jj-scroll-table"><table className="jj-content-table jj-change-material-table"><MaterialColumns/><tbody><MaterialRows items={shared.map(items=>items[0])} shared={sharedUses} commonStep={commonStep}/></tbody></table></div></section>}
      {actions.length>0&&<section className="jj-change-basis-group jj-change-material-section"><header><h3 className="jj-title-group">各项操作的检查材料</h3><p>每行是一份独立材料，按业务操作分组查看当前安排。</p></header><div className="jj-scroll-table"><table className="jj-content-table jj-change-material-table"><MaterialColumns/>{actions.map(actionId=>{
        const materials=individual.filter(item=>item.action_id===actionId)
        return <tbody key={actionId}><tr className="jj-change-material-group"><th scope="rowgroup" colSpan={3}>{materials[0].action_label}<small>{materials.length} 份材料</small></th></tr><MaterialRows items={materials} commonStep={commonStep}/></tbody>
      })}</table></div></section>}
      {commonStep&&<p className="jj-change-material-guidance"><strong>核对方式</strong><span>{commonStep}</span></p>}
      <p className="jj-small jj-muted">{plan.scope}</p>
    </div>
  </details>
}
