// 修复依据带回开发客户端；复制不派发任务，原题状态与检查入口只读服务端精确关联。
import { Button, Input } from 'antd'
import { useEffect, useRef, useState } from 'react'
import type { ProjectRepair } from '../../../api/checks/repairs'
import { repairLabels, repairReference } from '../../../api/checks/repairs'
import type { SourceChangeViewDto } from '../../../api/changes/sourceChanges'
import { EditorialHeader, EditorialPage } from '../../../shared/ui/Editorial'
import { StatusBadge } from '../../../shared/ui/StatusBadge'
import { RepairComparison } from './RepairComparison'
import '../../../shared/styles/collections.css'
export type RepairTask=ProjectRepair['tasks'][number]
export function RepairDelivery({task,change,onNavigate,onBack,onViewChange,loadingChange}:{task:RepairTask;change?:SourceChangeViewDto;onNavigate:(path:string)=>void;onBack:()=>void;onViewChange:()=>void;loadingChange?:boolean}){
 const rows=task.comparison??[],deny=rows.filter(row=>row.role==='DENY'),retained=[...new Map(rows.filter(row=>row.role!=='DENY').map(row=>[row.source_case_id,row])).values()]
 const [message,setMessage]=useState(''),root=useRef<HTMLDivElement>(null)
 const text=['请基于界鉴记录的事实修复这个权限问题，继续在当前对话中开发。',`项目：${task.contract.project_id}`,`原检查：${task.contract.source_run_id}；原题：${task.contract.source_case_id}`,`repair_reference：${JSON.stringify(repairReference(task.contract))}`,'通过 jiejian_repair_show 读取精确原题及证据，不凭本摘要重判。',...deny.map(row=>`需要消除：${row.subject_label??'原操作账号'}对${row.resource_owner_label??'原资源所有者'}的资源执行${row.action_label}时，禁止发生${row.effect_labels.join('、')}。`),...retained.map(row=>`必须保留：${row.subject_label??'原操作账号'}执行${row.action_label}的正常业务结果（${row.effect_labels.join('、')}）。`),'原权限、账号、资源归属和证明标准不变。不能关闭正常功能或减少考题来掩盖问题。','修改后先用 jiejian_change_registration_preview 核对范围，再用 jiejian_change_register 携带返回指纹、稳定 operation_id 与 repair_reference 一次登记。回执未知时用 jiejian_receipt_show 按 DELIVER 和原 operation_id 查询，不换新键试探。','执行检查前核对当前授权；修复成功只以精确原题复验与正常业务对照为准。'].join('\n')
 useEffect(()=>{setMessage('');const heading=root.current?.querySelector('h1');if(heading){heading.tabIndex=-1;heading.focus()}},[task.task_reference])
 const copy=async()=>{try{await navigator.clipboard.writeText(text);setMessage('修复依据已复制，尚未发送给 Agent。')}catch{setMessage('剪贴板不可用，请展开修复说明手动复制。')}}
 const resultAvailable=Boolean(task.verification&&task.run_id)
 const currentAction=task.status==='STALE'?<Button onClick={()=>onNavigate('/permissions')}>核对当前权限</Button>
  :task.status==='READY_TO_VERIFY'&&task.change_id?<Button type="primary" onClick={()=>onNavigate('/tests?materials=1&change_id='+encodeURIComponent(task.change_id!))}>准备复验原题</Button>
  :task.run_id?<Button type="primary" onClick={()=>onNavigate('/history?run_id='+encodeURIComponent(task.run_id!))}>{resultAvailable?'查看关联复验结果':'查看关联检查记录'}</Button>
  :task.change_id?<Button type="primary" loading={loadingChange} onClick={onViewChange}>查看本批修改</Button>
  :<Button type="primary" onClick={()=>void copy()}>复制修复依据</Button>
 return <div ref={root}><EditorialPage label="修复依据">
  <Button type="link" onClick={onBack}>← 返回源码改动</Button>
  <EditorialHeader eyebrow="源码改动 / 修复依据" title="修复与复验" status={<StatusBadge kind={task.status==='VERIFIED'?'verdict':'lifecycle'} tone={task.status==='VERIFIED'?'success':['STALE','NOT_VERIFIED','REPAIR_REQUIRED'].includes(task.status)?'danger':'neutral'}>{repairLabels[task.status]}</StatusBadge>}/>
  <section className="repair-origin"><div><h2>{deny[0]?.action_label??'已记录的权限问题'}</h2><p className="editorial-muted">原检查 · 权限版本 {task.contract.original_policy_epoch}</p></div><Button type="link" onClick={()=>onNavigate(`/history?run_id=${encodeURIComponent(task.contract.source_run_id)}&case_id=${encodeURIComponent(task.contract.source_case_id)}`)}>查看原始证据</Button></section>
  {task.status==='VERIFIED'?<section className="repair-published"><p>原题与要求保留的业务通过验证</p><RepairComparison rows={rows} sourceRunId={task.contract.source_run_id} onNavigate={onNavigate}/></section>:<div className="repair-requirement-columns">
    <section aria-label="需要消除的后果"><h3>需要消除的后果</h3>{deny.length?deny.map(row=><div className="repair-business-rule" key={row.source_case_id}><dl><div><dt>操作账号</dt><dd>{row.subject_label??'原操作账号'}</dd></div><div><dt>资源归属</dt><dd>{row.resource_owner_label??'原资源所有者'}</dd></div></dl><p><strong>不应发生：</strong>{row.effect_labels.join('、')}。</p></div>):<p>逐项说明暂未取得，请查看原始证据。</p>}</section>
    <section aria-label="必须保留的正常业务"><h3>必须保留的正常业务</h3>{retained.length?<ul className="repair-retained-business">{retained.map(row=><li key={row.source_case_id}><strong>{row.action_label}</strong><p>{row.subject_label??'原操作账号'}</p><p className="editorial-muted">{row.effect_labels.join('、')}</p></li>)}</ul>:<p>保留原正常对照与全部已通过回归。</p>}</section>
  </div>}
  {task.status!=='VERIFIED'&&<section className="repair-current-batch" aria-label="当前修复进展"><div><h3>{task.status==='STALE'?'先核对原题范围':task.change_id?'当前修改批次':'交给开发工具修复'}</h3><p>{task.status==='STALE'?'原权限已经变化，请先核对当前权限和原记录。':task.change_id?change?.manifest.reason??'已关联修复修改，继续核对本批准备条件。':'复制修复依据，粘贴到当前开发对话；修改完成后由 Agent 登记新批次。'}</p></div>{task.change_id&&task.status!=='CHANGE_SUBMITTED'&&<Button onClick={onViewChange} loading={loadingChange}>查看本批修改</Button>}</section>}
  {task.status!=='VERIFIED'&&<details className="repair-reference-details"><summary>查看完整修复说明</summary><Input.TextArea className="light-repair-copy" aria-label="修复依据内容" readOnly value={text} autoSize={{minRows:7,maxRows:16}}/>{task.change_id&&<Button onClick={()=>void copy()}>复制修复依据</Button>}<RepairComparison rows={rows} sourceRunId={task.contract.source_run_id} onNavigate={onNavigate}/></details>}
  {message&&<p role="status">{message}</p>}
  <footer className="repair-page-actions"><Button onClick={onBack}>返回源码改动</Button>{task.status==='VERIFIED'?<><Button onClick={()=>onNavigate('/history?run_id='+encodeURIComponent(task.contract.source_run_id))}>查看原检查结果</Button>{task.change_id&&<Button type="primary" onClick={onViewChange}>查看本次修改</Button>}</>:currentAction}</footer>
 </EditorialPage></div>
}
