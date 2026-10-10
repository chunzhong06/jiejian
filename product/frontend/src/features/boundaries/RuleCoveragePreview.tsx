// 可选规则说明保留在原审阅页；旧来源或旧选项的迟到响应不得覆盖当前匹配。
import { Alert, Button, Select } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { rulePreviewApi, type RulePreview, type RulePreviewReference, type RulePreviewSituation } from '../../api/boundaries/rulePreview'
import './rule-candidates.css'

export function RuleCoveragePreview({projectId,reference}:{projectId:string;reference:RulePreviewReference}) {
  const [open,setOpen]=useState(false),[value,setValue]=useState<RulePreview>(),[situation,setSituation]=useState<Partial<RulePreviewSituation>>({}),[error,setError]=useState<string>(),[busy,setBusy]=useState(false)
  const epoch=useRef(0),scope=JSON.stringify([projectId,reference]),current=useRef(scope)
  current.current=scope
  const read=async(input?:RulePreviewSituation)=>{
    const generation=++epoch.current
    setBusy(true);setError(undefined)
    try {
      const result=await rulePreviewApi.read(projectId,reference,input)
      if(generation!==epoch.current||scope!==current.current)return
      if(result.project_id!==projectId)throw new Error('preview project mismatch')
      setValue(result)
    }catch{if(generation===epoch.current)setError('暂时无法读取这些规则，请重试。')}
    finally{if(generation===epoch.current)setBusy(false)}
  }
  useEffect(()=>{setValue(undefined);setSituation({});if(open)void read();return()=>{epoch.current++}},[scope,open])
  const change=(patch:Partial<RulePreviewSituation>)=>{epoch.current++;setBusy(false);setError(undefined);setSituation(before=>({...before,...patch}));setValue(before=>before?{...before,coverage:null,matches:[]}:undefined)}
  const ready=Boolean(situation.subject_id&&situation.owner_id&&situation.relation&&situation.action_id&&situation.effect_id)
  const same=situation.subject_id===situation.owner_id
  const actorOptions=value?.actors.map(item=>({value:item.id,label:item.label}))
  const selectField=(label:string,field:keyof RulePreviewSituation,options:Array<{value:string;label:string}>|undefined,onChange?:(value:string)=>void)=><label>{label}<Select aria-label={label} placeholder="请选择" value={situation[field]} options={options??[]} onChange={onChange??(next=>change({[field]:next}))}/></label>
  const explanations={ALLOW:'这组规则允许这个角色执行该动作，并取得所选结果。',DENY:'这组规则要求禁止这个角色通过该动作造成所选结果。',UNCOVERED:'这组规则还没有覆盖这个情境。',CONFLICT:'同一情境同时出现允许和禁止要求，需要先整理规则。'}
  return <details className="rule-coverage-preview" open={open} onToggle={event=>setOpen(event.currentTarget.open)}><summary>试一下这些规则怎样适用</summary>
    {open&&<div className="rule-coverage-body"><p className="editorial-muted">选择一种情境，查看这份规则要求什么；真实应用是否遵守，需要执行检查。</p>
      {error&&<Alert type="warning" showIcon message={error} action={<Button onClick={()=>void read()}>重新读取</Button>}/>}
      {!value&&!error&&<p role="status">正在读取规则…</p>}
      {value?.availability==='STALE'&&<p>候选的依据已经变化，请先重新整理。</p>}
      {value?.availability==='NEEDS_DECISION'&&<p>先完成含义核对，再查看规则怎样适用。</p>}
      {value?.availability==='AVAILABLE'&&<><div className="rule-coverage-fields">
        {selectField('谁来操作','subject_id',actorOptions,next=>change({subject_id:next,relation:undefined}))}
        {selectField('资源属于谁','owner_id',actorOptions,next=>change({owner_id:next,relation:undefined}))}
        {selectField('资源关系','relation',!situation.subject_id||!situation.owner_id?[]:same?[{value:'OWNS',label:'自己的资源'},{value:'SAME_ROLE_OTHER_ACCOUNT',label:'同角色另一账号的资源'}]:[{value:'OTHER_ROLE',label:'另一角色的资源'}])}
        {selectField('执行什么动作','action_id',value.actions.map(item=>({value:item.id,label:item.label})),next=>change({action_id:next,effect_id:undefined}))}
        {selectField('观察哪个结果','effect_id',value.actions.find(item=>item.id===situation.action_id)?.effects.map(item=>({value:item.id,label:item.label})))}
      </div><Button disabled={!ready} loading={busy} onClick={()=>void read(situation as RulePreviewSituation)}>查看规则如何适用</Button>
      {value.coverage&&<p className="rule-coverage-answer" role="status">{explanations[value.coverage]}</p>}</>}
    </div>}
  </details>
}
