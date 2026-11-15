import type {RepairComparisonRow} from '../api/repairs'
import {groupRepairComparisons} from '../model/repairComparisons'
import {Badge} from '../../../shared/ui/feedback'
import './repair-cases.css'

const verdict={SAFE:'符合规则',VULNERABLE:'不符合规则',INCONCLUSIVE:'证据不足'}
const purpose=(roles:RepairComparisonRow['role'][])=>roles.includes('DENY')?'原禁止场景':roles.includes('SELECTED_ALLOW')?roles.includes('REGRESSION')?'正常对照与功能回归':'正常对照':'正常功能回归'

/** 原题与预览共用同一业务身份；分组只合并用途，不改变服务端结果或前后对应。 */
export function RepairCases({rows,compare=false}:{rows:RepairComparisonRow[];compare?:boolean}){
  const cases=groupRepairComparisons(rows)
  const identity=(row:RepairComparisonRow,roles?:RepairComparisonRow['role'][])=><div className="jj-repair-case-identity"><div className="jj-object-line"><strong>{row.action_label}</strong>{roles&&<small className="jj-repair-case-purpose">{purpose(roles)}</small>}</div><p>账号：{row.subject_label??'名称未记录'}{compare?<> · 数据：<code>{row.resource_id}</code><span>归属于 {row.resource_owner_label??'名称未记录'}</span></>:<span>数据所有者：{row.resource_owner_label??'名称未记录'}</span>}</p>{!compare&&<p>测试数据：<code>{row.resource_id}</code></p>}<small>核对后果：{row.effect_labels.join('、')||'见原问题证据'}</small></div>
  if(!compare)return <div className="jj-repair-cases">{cases.map(({key,row,roles})=><article key={key}><h4>{purpose(roles)}</h4>{identity(row)}</article>)}</div>
  return <div className="jj-repair-comparison-frame"><div className="jj-scroll-table"><table className="jj-content-table jj-repair-comparison"><thead><tr><th scope="col">原题与保留功能</th><th scope="col" className="jj-table-state">原检查</th><th scope="col" className="jj-table-state">关联复验</th></tr></thead><tbody>{cases.map(({key,row,roles})=><tr key={key}><td>{identity(row,roles)}</td><td className="jj-table-state" data-label="原检查">{verdict[row.before_verdict]}</td><td className="jj-table-state" data-label="关联复验">{row.after_verdict?<>{verdict[row.after_verdict]}{row.match_status!=='MATCHED'&&<Badge tone="caution">对应待核对</Badge>}</>:'尚无关联结果'}</td></tr>)}</tbody></table></div></div>
}
