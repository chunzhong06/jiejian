import type {CheckPreview} from '../../check/api/currentChecks'
import {Badge} from '../../../shared/ui/feedback'
import {ActionLink} from '../../../shared/ui/actions'
import {readRoute,scopedPath,withReturnDestination} from '../../../shared/lib/navigation'

const materials={identity:'测试账号',execution:'操作流程',resource:'测试资源',evidence:'结果证明',recovery:'恢复方式'}
const treatments={KEEP:'沿用',ADD:'补充',RECHECK:'重新核对',DECIDE:'需要决定'}
const people={SYSTEM:'程序核对',USER:'用户确认',AGENT_AND_USER:'Agent 整理，用户确认'}

/** 只阅读同次预览的完整材料处理；原目录继续拥有编辑、授权和执行入口。 */
export function PreparationReview({preview}:{preview:CheckPreview}){
  const route=readRoute(),origin=route.path+'?'+route.query
  const work=preview.preparation_work
  if(work?.project_id!==preview.project_id||work.plan_fingerprint!==preview.plan_fingerprint)return null
  const items=work.impacts.filter(item=>item.handling&&item.explanation&&item.next_step)
  if(!items.length)return null
  const destination=(item:typeof items[number])=>{
    const query=new URLSearchParams({action_id:item.action_id,material_kind:item.kind})
    if(item.member_id)query.set(item.kind==='identity'?'identity_id':'member_id',item.member_id)
    if(item.kind==='identity'&&item.slot_id)query.set('account_slot',item.slot_id)
    return '#'+scopedPath(withReturnDestination('/preparation?'+query,origin),preview.project_id)
  }
  return <details className="jj-preparation-review"><summary>本次材料处理方案</summary>
    <p className="jj-small jj-muted">按本次要求保留兼容材料，补充或重核其余部分。具体配置与授权继续在原材料入口完成。</p>
    <div className="jj-scroll-table"><table className="jj-content-table" data-density="compact"><thead><tr><th>业务操作与材料</th><th>本次处理</th><th>依据与下一步</th><th>由谁处理</th></tr></thead><tbody>{items.map((item,index)=><tr key={item.action_id+':'+item.kind+':'+(item.member_id??index)}><td>{item.action_label}<small className="jj-table-secondary">{item.member_label||materials[item.kind]}</small></td><td><Badge tone={item.handling==='KEEP'?'positive':item.handling==='DECIDE'?'caution':'neutral'}>{treatments[item.handling!]}</Badge></td><td>{item.explanation}<small className="jj-table-secondary">{item.next_step}</small>{Boolean(item.prerequisites?.length)&&<small className="jj-table-secondary">先核对账号槽位：{item.prerequisites!.join('、')}</small>}{item.handling!=='KEEP'&&<ActionLink href={destination(item)}>核对这份材料</ActionLink>}</td><td>{item.handler?people[item.handler]:'按原材料入口核对'}</td></tr>)}</tbody></table></div>
  </details>
}
