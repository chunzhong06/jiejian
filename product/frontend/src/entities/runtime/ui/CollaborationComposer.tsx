import {useState} from 'react'
import {collaborationTitle} from '../model/taskReading'
import {purposeLabels,type CollaborationPurpose,type CollaborationTask,type CollaborationBrief} from '../api/collaboration'
import type {HandoffContext} from '../model/handoff'
import {Button} from '../../../shared/ui/actions'
import {Choice} from '../../../shared/ui/Choice'
import {Dialog} from '../../../shared/ui/Dialog'
import {Field} from '../../../shared/ui/layout'
import {ErrorNote,Notice} from '../../../shared/ui/feedback'

const startingPoints:[CollaborationPurpose,string][]=[
  ['RULES','根据当前应用的接口资料，整理业务操作与权限要求，提交待我确认的候选。'],
  ['SETUP','根据已确认的权限要求，整理测试账号、资源与执行场景，指出需要我提供的材料。'],
  ['CHECK','检查当前应用权限要求对应的行为，保留正常操作对照，整理已确认的问题和证据缺口。'],
]
export function CollaborationComposer({goal,setGoal,purpose,setPurpose,target,setTarget,current,context,busy,uncertain,error,onClose,onSubmit}:{goal:string;setGoal:(value:string)=>void;purpose:CollaborationPurpose;setPurpose:(value:CollaborationPurpose)=>void;target:string;setTarget:(value:string)=>void;current?:Pick<CollaborationTask,'task_id'|'goal'>&Partial<Pick<CollaborationTask,'purpose'|'brief'>>;context?:HandoffContext;busy:boolean;uncertain:boolean;error:unknown;onClose:()=>void;onSubmit:(brief?:CollaborationBrief)=>void}){
  const [name,setName]=useState('')
  return <Dialog title="与 Agent 协作" closeDisabled={busy} onClose={onClose} actions={dismiss=><><Button disabled={busy} onClick={dismiss}>取消</Button><Button kind="primary" busy={busy} disabled={!goal.trim()} onClick={()=>onSubmit(name.trim()?{title:name.trim(),objective:'',outputs:[]}:undefined)}>{uncertain?'核对原交接请求':target?'补充到原任务':'建立协作任务'}</Button></>}>
      <p>任务会带入当前应用及所选对象。创建后选择执行方式。</p>
      <Field measure="standard" label="任务类型"><Choice value={purpose} disabled={busy||uncertain} onValueChange={value=>{setPurpose(value as CollaborationPurpose);if(!goal||startingPoints.some(([,example])=>example===goal))setGoal(startingPoints.find(([kind])=>kind===value)?.[1]??'')}}>{Object.entries(purposeLabels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</Choice></Field>
      <Field measure="long" label="希望 Agent 完成什么"><textarea rows={3} maxLength={2000} disabled={busy||uncertain} value={goal} onChange={event=>setGoal(event.target.value)} placeholder="说明业务目标，已有配置会沿用，缺少的信息再向你询问"/></Field>
      <details className="jj-collaboration-name"><summary>为任务命名（选填）</summary><Field measure="standard" label="简明任务名称"><input maxLength={80} value={name} disabled={busy||uncertain} onChange={event=>setName(event.target.value)}/></Field></details>
      {!target&&<div className="jj-collaboration-suggestions" aria-label="协作任务建议"><span>也可以从这里开始</span><div>{startingPoints.map(([kind,example])=><Button key={kind} kind="quiet" size="compact" disabled={busy||uncertain} onClick={()=>{setPurpose(kind);setGoal(example)}}>{purposeLabels[kind]}</Button>)}</div></div>}
      {current&&<Field measure="standard" label="任务归属"><Choice value={target} disabled={busy||uncertain} onValueChange={setTarget}><option value={current.task_id}>补充到：{collaborationTitle(current)}</option><option value="">建立独立任务</option></Choice></Field>}
      <section className="jj-handoff-context" aria-label="本次交接内容"><strong>{context?.label??'当前应用与页面'}</strong><p>{context?.editor?.kind==='FLOW'?`${context.editor.steps.length} 个请求的结构、参数来源及当前流程修订`:context?.editor?.kind==='PROOF'?'当前操作、判断结果与已选字段':context?.references.action_id?'已关联当前业务操作，完成后可返回这里继续':context?.references.run_id?'已关联这份检查报告及当前查看的结果':context?.references.rule_id?'已关联这条权限规则和当前修订':'沿用当前应用；可在任务目标中补充要处理的业务对象'}</p>{context?.editor&&<small>任务会带入结构和已选对象，参数原值、凭据和文件不会进入任务历史。未保存的草稿保留在当前浏览器窗口，可从原位置继续编辑。</small>}{target&&<small>补充会更新原任务的目标，已有操作与产物继续保留。</small>}</section>
      {uncertain&&<Notice tone="caution">交接结果尚未确认。已保留原目标和请求编号，请核对原请求。</Notice>}
      {Boolean(error)&&<ErrorNote error={error}/>}
    </Dialog>
}
