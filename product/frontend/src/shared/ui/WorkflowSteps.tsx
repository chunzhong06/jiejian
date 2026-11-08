import type {ReactNode} from 'react'
import CheckOutlined from '@ant-design/icons/CheckOutlined'
import ExclamationOutlined from '@ant-design/icons/ExclamationOutlined'

export type WorkflowStep={id:string;label:string;description?:ReactNode;state:'pending'|'current'|'complete'|'blocked'|'error';disabled?:boolean}
const states={pending:'待进行',current:'当前阶段',complete:'已完成',blocked:'需要处理',error:'未完成'}

/** 仅表达调用方确认的阶段事实；不按当前位置推断完成，也不放开业务门禁。 */
export function WorkflowSteps({label,steps,onStepChange,className=''}:{label:string;steps:WorkflowStep[];onStepChange?:(id:string)=>void;className?:string}){
  return <div className={'jj-stage-guide '+className} data-count={steps.length}><ol aria-label={label}>{steps.map((step,index)=>{
    const content=<><span className="jj-stage-marker" aria-hidden="true">{step.state==='complete'?<CheckOutlined/>:step.state==='error'||step.state==='blocked'?<ExclamationOutlined/>:index+1}</span><span className="jj-stage-copy"><span className="jj-stage-label">{step.label}</span>{step.description&&<small>{step.description}</small>}<span className="jj-sr-only">{states[step.state]}</span></span></>
    return <li key={step.id} data-state={step.state} aria-current={step.state==='current'?'step':undefined}>{onStepChange?<button type="button" disabled={step.disabled} className="jj-stage-item" onClick={()=>onStepChange(step.id)}>{content}</button>:<div className="jj-stage-item">{content}</div>}</li>
  })}</ol></div>
}
