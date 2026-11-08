import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'
import {purposeLabels,type CollaborationPurpose,type CollaborationTask} from '../api/collaboration'
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
export function CollaborationComposer({goal,setGoal,purpose,setPurpose,target,setTarget,current,context,busy,uncertain,error,onClose,onSubmit}:{goal:string;setGoal:(value:string)=>void;purpose:CollaborationPurpose;setPurpose:(value:CollaborationPurpose)=>void;target:string;setTarget:(value:string)=>void;current?:Pick<CollaborationTask,'task_id'|'goal'>;context?:HandoffContext;busy:boolean;uncertain:boolean;error:unknown;onClose:()=>void;onSubmit:()=>void}){
  return <Dialog title="与 Agent 协作" closeDisabled={busy} onClose={onClose} actions={<><Button disabled={busy} onClick={onClose}>取消</Button><Button kind="primary" busy={busy} disabled={!goal.trim()} onClick={onSubmit}>{uncertain?'核对原交接请求':target?'补充到原任务':'建立协作任务'}<ArrowRightOutlined aria-hidden="true"/></Button></>}>
      <p>先说明目标，界鉴会带入当前应用及相关资料。建立任务后，再选择启动本机 Agent 或复制给开发工具。</p>
      <div className="jj-collaboration-starting-points" role="group" aria-label="协作目标示例">{startingPoints.map(([kind,example])=><Button key={kind} disabled={busy||uncertain} aria-pressed={purpose===kind&&goal===example} onClick={()=>{setPurpose(kind);setGoal(example)}}>{purposeLabels[kind]}</Button>)}</div>
      <Field label="任务类型"><Choice value={purpose} disabled={busy||uncertain} onValueChange={value=>setPurpose(value as CollaborationPurpose)}>{Object.entries(purposeLabels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</Choice></Field>
      <Field label="希望 Agent 完成什么"><textarea rows={3} maxLength={2000} disabled={busy||uncertain} value={goal} onChange={event=>setGoal(event.target.value)} placeholder="说明业务目标，已有配置会沿用，缺少的信息再向你询问"/></Field>
      {current&&<Field label="接续位置"><Choice value={target} disabled={busy||uncertain} onValueChange={setTarget}><option value={current.task_id}>补充到：{current.goal}</option><option value="">建立独立任务</option></Choice></Field>}
      <section className="jj-handoff-context" aria-label="本次交接内容"><strong>{context?.label??'当前应用与页面'}</strong><p>{context?.editor?.kind==='FLOW'?`${context.editor.steps.length} 个请求的结构、参数来源及当前流程修订`:context?.editor?.kind==='PROOF'?'当前操作、判断结果与已选字段':'当前业务对象和返回位置'}</p>{context?.editor&&<small>任务会带入结构和已选对象，参数原值、凭据和文件不会进入任务历史。未保存的草稿保留在当前浏览器窗口，可从原位置继续编辑。</small>}{target&&<small>补充会更新原任务的目标，已有操作与产物继续保留。</small>}</section>
      {uncertain&&<Notice tone="caution">交接结果尚未确认。已保留原目标和请求编号，请核对原请求。</Notice>}
      {Boolean(error)&&<ErrorNote error={error}/>}
    </Dialog>
}
