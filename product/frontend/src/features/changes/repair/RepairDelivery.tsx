// 修复依据带回原客户端；复制不派发任务，原题状态与检查入口只读服务端精确关联。
import { Button, Input } from 'antd'
import { useEffect, useRef, useState } from 'react'
import type { ProjectRepair } from '../../../api/checks/repairs'
import { repairLabels, repairReference } from '../../../api/checks/repairs'
import type { SourceChangeViewDto } from '../../../api/changes/sourceChanges'
import { EditorialHeader, EditorialPage } from '../../../shared/ui/Editorial'
import { RepairComparison } from './RepairComparison'
import '../styles/lightweight.css'
export type RepairTask=ProjectRepair['tasks'][number]
export function RepairDelivery({task,change,onNavigate,onBack,onViewChange,loadingChange}:{task:RepairTask;change?:SourceChangeViewDto;onNavigate:(path:string)=>void;onBack:()=>void;onViewChange:()=>void;loadingChange?:boolean}){
 const rows=task.comparison??[],deny=rows.filter(row=>row.role==='DENY'),retained=[...new Map(rows.filter(row=>row.role!=='DENY').map(row=>[row.source_case_id,row])).values()]
 const [message,setMessage]=useState(''),root=useRef<HTMLDivElement>(null)
 const text=['请基于界鉴记录的事实修复这个权限问题，继续在当前对话中开发。',`项目：${task.contract.project_id}`,`原检查：${task.contract.source_run_id}；原题：${task.contract.source_case_id}`,`repair_reference：${JSON.stringify(repairReference(task.contract))}`,'通过 jiejian_repair_show 读取精确原题及证据，不凭本摘要重判。',...deny.map(row=>`需要消除：${row.subject_label??'原操作账号'}对${row.resource_owner_label??'原资源所有者'}的资源执行${row.action_label}时，禁止发生${row.effect_labels.join('、')}。`),...retained.map(row=>`必须保留：${row.subject_label??'原操作账号'}执行${row.action_label}的正常业务结果（${row.effect_labels.join('、')}）。`),'原权限、账号、资源归属和证明标准不变。不能关闭正常功能或减少考题来掩盖问题。','修改后先用 jiejian_change_registration_preview 核对范围，再用 jiejian_change_register 携带返回指纹、稳定 operation_id 与 repair_reference 一次登记。回执未知时用 jiejian_receipt_show 按 DELIVER 和原 operation_id 查询，不换新键试探。','执行检查前核对当前授权；修复成功只以精确原题复验与正常业务对照为准。'].join('\n')
 useEffect(()=>{setMessage('');const heading=root.current?.querySelector('h1');if(heading){heading.tabIndex=-1;heading.focus()}},[task.task_reference])
 return <div ref={root}><EditorialPage label="修复依据"><Button className="light-back" type="link" onClick={onBack}>← 返回修改与验证</Button><EditorialHeader eyebrow="修改与验证 / 原问题" title="修复依据"><p className="editorial-muted">把已经核对的事实带回原来的 Agent 对话，继续修改。</p></EditorialHeader>
  <section className="light-detail"><header className="light-detail-heading"><div><p className="editorial-eyebrow">原问题</p><h2>{deny[0]?.action_label??'已记录的权限问题'}</h2><p>{repairLabels[task.status]}</p></div><Button type="link" onClick={()=>onNavigate(`/history?run_id=${encodeURIComponent(task.contract.source_run_id)}&case_id=${encodeURIComponent(task.contract.source_case_id)}`)}>查看原始证据</Button></header>
   <div className="light-detail-body"><section><h3>需要消除的后果</h3>{deny.length?deny.map(row=><p key={row.source_case_id}>{row.subject_label??'原操作账号'}操作{row.resource_owner_label??'原资源所有者'}的资源时，不应发生{row.effect_labels.join('、')}。</p>):<p>逐项说明暂未取得，请查看完整原题。</p>}</section><section><h3>必须保留的正常业务</h3>{retained.length?retained.map(row=><p key={row.source_case_id}>{row.subject_label??'原操作账号'} · {row.action_label} · {row.effect_labels.join('、')}</p>):<p>保留原正常对照与全部已通过回归，不以关闭功能代替修复。</p>}</section>
    {task.status==='VERIFIED'?<p>原题与要求保留的业务通过验证</p>:task.status==='STALE'?<p role="status">原题引用已失效，请核对当前权限与原记录。</p>:<><Input.TextArea className="light-repair-copy" aria-label="修复依据内容" readOnly value={text} autoSize={{minRows:7,maxRows:16}}/><p className="light-meta">复制后粘贴到当前客户端；界鉴不会发送消息或另建聊天。</p><div className="light-actions"><Button type={task.change_id?'default':'primary'} onClick={async()=>{try{await navigator.clipboard.writeText(text);setMessage('修复依据已复制，尚未发送给 Agent。')}catch{setMessage('剪贴板不可用，请从上方手动复制。')}}}>复制修复依据</Button></div></>}
    {message&&<p role="status">{message}</p>}
    <div className="light-repair-status"><span>{task.change_id?'关联修改已登记':'等待新的修改记录'} · {repairLabels[task.status]}</span><div className="light-actions">{task.status==='READY_TO_VERIFY'&&task.change_id?<><Button type="link" loading={loadingChange} onClick={onViewChange}>查看本批修改</Button><Button type="primary" onClick={()=>onNavigate('/tests?change_id='+encodeURIComponent(task.change_id!))}>复验原题</Button></>:task.run_id?<Button type="primary" onClick={()=>onNavigate('/history?run_id='+encodeURIComponent(task.run_id!))}>{task.verification?'查看关联复验结果':'查看关联检查记录'}</Button>:task.change_id?<Button type="primary" loading={loadingChange} onClick={onViewChange}>查看本批修改</Button>:null}</div></div>
    <details className="delivery-technical"><summary>查看完整要求与前后对照</summary><RepairComparison rows={rows} sourceRunId={task.contract.source_run_id} onNavigate={onNavigate}/>{change&&<p>{change.manifest.reason}</p>}</details>
   </div></section>
 </EditorialPage></div>
}
