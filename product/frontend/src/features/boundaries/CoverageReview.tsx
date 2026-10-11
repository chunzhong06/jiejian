// 人确认要求与具体检查入口的对应关系；就绪只由服务端计划和证明核验，不提供手工完成开关。
import {useEffect,useState} from 'react'
import {Button,Input,Select,Checkbox} from 'antd'
import type {BoundaryReview, CoverageChoice, RuleCandidateView} from '../../api/boundaries/ruleCandidates'
import {useTaskGuard} from '../../shared/runtime/editGuard'
import './rule-scope.css'

type Target=CoverageChoice['targets'][number]
const emptyTarget=():Target=>({permission_item_id:'',method:'GET',path:'',proof:'EFFECT'})
export function CoverageReview({item,value,disabled,onSave}:{item:BoundaryReview;value:RuleCandidateView;disabled:boolean;onSave:(choice:CoverageChoice)=>void}) {
  const saved=value.coverage_review?.find(link=>link.issue_id===item.issue_id)
  const suggestion=value.candidate.content.coverage_suggestions?.find(link=>link.issue_id===item.issue_id)
  const savedKey=JSON.stringify(saved?.link),suggestionKey=JSON.stringify(suggestion)
  const [targets,setTargets]=useState<Target[]>(saved?.link.targets??suggestion?.targets??[emptyTarget()])
  const [time,setTime]=useState<CoverageChoice['time_scope']>()
  const [reason,setReason]=useState('')
  const [dirty,setDirty]=useState(false)
  const [complete,setComplete]=useState(false)
  useTaskGuard(dirty)
  useEffect(()=>{setTargets(saved?.link.targets??suggestion?.targets??[emptyTarget()]);setTime(undefined);setReason('');setDirty(false);setComplete(false)},[item.issue_fingerprint,item.decision?.output_revision,savedKey,suggestionKey])
  if (!item.decision || item.status!=='OPEN' || !['PREPARATION_DEPENDENCY','EVIDENCE_GAP','COVERAGE_GAP'].includes(item.decision.outcome)) return null
  const change=(index:number,patch:Partial<Target>)=>{setTargets(rows=>rows.map((row,i)=>i===index?{...row,...patch}:row));setDirty(true);setComplete(false)}
  const options=value.candidate.content.permissions.filter(rule=>rule.effective_state==='ACTIVE').map(rule=>({value:rule.item_id,label:`${rule.expectation==='ALLOW'?'允许':'禁止'} · ${value.candidate.content.examples.find(v=>v.permission_item_id===rule.item_id)?.description??rule.item_id}`}))
  return <div className="coverage-link">
    {saved && <div className="scope-saved"><span>{saved.status==='PLANNED'?'已明确检查要求 · 待准备':saved.status==='DRAFT'?'关联草稿 · 还需补全':saved.status==='STALE'?'关联依据已变化':'历史范围尚不支持'}</span><p>{saved.message}</p><small>{saved.link.targets.length} 项权限与入口关联；不代表已经取证或通过。</small></div>}
    <header className="coverage-intro"><div><h3>把业务要求变成可执行的检查</h3><p>要求已经保留；现在需要明确查哪个入口、查多久、用什么证明。</p></div><span>当前：确定检查方式<br/>下一步：审阅规则与准备材料</span></header>
    <details className="coverage-form-details"><summary>{saved?'查看或调整检查方式':'填写这条要求的检查方式'}</summary><div className="scope-editor coverage-editor">
      <p className="editorial-muted">可请 Agent 提供接口与证明建议，再逐项核对。多个入口分别填写，正常使用对照也必须保留。</p>
      {suggestion&&<p className="editorial-muted">Agent 已填写检查建议，等待你核对：{suggestion.explanation}</p>}
      <h4>1. 确定要观察的时间</h4>
      <label htmlFor={`${item.issue_id}-window`}>要求覆盖哪个时间范围？</label><Select id={`${item.issue_id}-window`} placeholder="请选择，系统不会自动缩小历史范围" value={time} onChange={v=>{setTime(v);setDirty(true);setComplete(false)}} disabled={disabled} options={[{value:'CHECK_WINDOW',label:'本次检查过程，包含中间发生后又撤回的变化'},{value:'HISTORY',label:'包含此前历史，当前仍需补充能力'}]}/>
      <h4>2. 列出需要检查的入口与证明</h4>
      {targets.map((target,index)=><div className="coverage-target" key={index}><label htmlFor={`${item.issue_id}-permission-${index}`}>对应权限 · {index+1}</label><Select id={`${item.issue_id}-permission-${index}`} placeholder="选择这条要求对应的权限" value={target.permission_item_id||undefined} options={options} onChange={v=>change(index,{permission_item_id:v})} disabled={disabled}/>
        <div className="coverage-target-fields"><div><label htmlFor={`${item.issue_id}-method-${index}`}>请求方式</label><Select id={`${item.issue_id}-method-${index}`} value={target.method} options={['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'].map(value=>({value,label:value}))} onChange={v=>change(index,{method:v})} disabled={disabled}/></div><div><label htmlFor={`${item.issue_id}-path-${index}`}>实际检查入口</label><Input id={`${item.issue_id}-path-${index}`} value={target.path} placeholder="例如 /api/galleries/{resource_id}/internal" maxLength={256} onChange={e=>change(index,{path:e.target.value})} disabled={disabled}/></div></div>
        <label htmlFor={`${item.issue_id}-proof-${index}`}>需要什么证明？</label><Select id={`${item.issue_id}-proof-${index}`} value={target.proof} onChange={v=>change(index,{proof:v})} disabled={disabled} options={[{value:'EFFECT',label:'对应业务结果的有效证明'},{value:'PROCESS_RECORD',label:'过程记录：发生后撤回也必须被发现'}]}/>
        {targets.length>1 && <div className="scope-actions"><Button type="text" disabled={disabled} onClick={()=>{setTargets(rows=>rows.filter((_,i)=>i!==index));setDirty(true);setComplete(false)}}>移除这条关联</Button></div>}
      </div>)}
      <Button type="link" disabled={disabled||targets.length>=100} onClick={()=>{setTargets(rows=>[...rows,emptyTarget()]);setDirty(true);setComplete(false)}}>添加另一个权限或入口</Button>
      <h4>3. 说明依据，保存本次整理</h4>
      <label htmlFor={`${item.issue_id}-coverage-reason`}>这些检查能覆盖什么，还有什么待补？</label><Input.TextArea id={`${item.issue_id}-coverage-reason`} value={reason} maxLength={512} autoSize={{minRows:2,maxRows:4}} onChange={e=>{setReason(e.target.value);setDirty(true)}} disabled={disabled}/>
      <div className="coverage-confirm"><Checkbox checked={complete} disabled={disabled} onChange={e=>{setComplete(e.target.checked);setDirty(true)}}>我已列全这条要求需要检查的权限与入口</Checkbox><p>尚未列全时先存草稿，问题会继续保留。</p></div>
      <div className="coverage-save"><p>{complete?'保存后可继续审阅规则；开始检查前，系统仍会核验入口、正常对照和证明。':'草稿用于继续补充，保存后仍不能开始完整检查。'}</p><Button type="primary" disabled={disabled||!time||!reason.trim()||targets.some(t=>!t.permission_item_id||!t.path.startsWith('/'))} onClick={()=>time&&onSave({issue_id:item.issue_id,issue_fingerprint:item.issue_fingerprint,review_revision:item.decision!.output_revision,time_scope:time,targets,reason,complete})}>{complete?'确认检查方式':'保存草稿'}</Button></div>
    </div></details>
  </div>
}
