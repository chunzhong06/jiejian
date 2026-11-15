import type {OperationFlow} from '../api/operationFlows'
import './operation-flow-summary.css'

type FlowMeaning={actionLabel:string;effects?:Array<{effect_id:string;label:string}>;stateChanging?:boolean}

/** 概览读取指定修订，业务名称来自准确动作；不把配置、请求回执或缺失上下文解释为业务结论。 */
export function OperationFlowSummary({flow,accounts,actionLabel,effects=[],focus,stateChanging}:{flow:OperationFlow;accounts:Array<{identity_id:string;label:string}>;focus?:'execution'|'resource'|'recovery'}&FlowMeaning){
  const label=(id:string)=>accounts.find(item=>item.identity_id===id)?.label??'原账号（请核对当前资料）'
  const showExecution=!focus||focus==='execution',showOutcome=focus!=='resource'
  return <div className="jj-flow-summary">
    <section><h3>{focus==='recovery'?'恢复哪项操作':'操作与使用对象'}</h3><p className="jj-flow-summary-purpose">{actionLabel}</p><dl className="jj-facts jj-flow-summary-facts">
      {focus!=='recovery'&&<div><dt>操作账号</dt><dd>{label(flow.subject_test_identity_id)}</dd></div>}
      <div><dt>使用的数据</dt><dd><code>{flow.actual_resource_id||'尚未填写'}</code><small>归属于 {label(flow.resource_owner_test_identity_id)}</small></dd></div>
      {focus==='recovery'&&<div><dt>恢复执行账号</dt><dd>{label(flow.resource_owner_test_identity_id)}</dd></div>}
    </dl></section>
    {showExecution&&<section><h3>执行安排</h3><ol className="jj-flow-summary-steps" aria-label="流程执行顺序">{flow.workflow.steps.map((step,index)=><li key={step.id}><span>{String(index+1).padStart(2,'0')}</span><div><strong>{step.purpose==='TARGET'?actionLabel:'准备本次操作'}</strong><p>{step.purpose==='TARGET'?'使用本次操作账号，对上方数据执行受检操作。':'在受检操作前执行已保存的准备请求。'}</p></div></li>)}</ol></section>}
    {showOutcome&&<section><h3>{focus==='recovery'?'检查后的处理':'结果核对与恢复'}</h3><div className="jj-flow-summary-outcome">
      {focus!=='recovery'&&(flow.entity_evidence??[]).map(item=><div key={item.effect_id}><strong>{effects.find(effect=>effect.effect_id===item.effect_id)?.label??'业务结果（'+item.effect_id+'）'}</strong><p>由数据所有者独立查询，用于核对操作后的业务结果。</p></div>)}
      <div><strong>检查后恢复</strong><p>{flow.recovery?'由数据所有者提交已配置的恢复请求。执行反馈在试运行或正式检查中查看。':stateChanging===false?'只读操作，无需恢复。':'尚未配置恢复请求。'}</p></div>
    </div></section>}
    {(showExecution||showOutcome&&Boolean(flow.recovery||flow.entity_evidence?.length))&&<details className="jj-flow-summary-technical"><summary>查看请求与核对配置</summary><dl className="jj-facts is-stacked">
      {showExecution&&flow.workflow.steps.map((step,index)=><div key={step.id}><dt>第 {index+1} 步 · {step.purpose==='TARGET'?'受检操作':'准备请求'}</dt><dd><code>{step.request_template.method} {step.request_template.path}</code></dd></div>)}
      {showOutcome&&focus!=='recovery'&&(flow.entity_evidence??[]).map((item,index)=><div key={item.effect_id}><dt>结果查询{(flow.entity_evidence?.length??0)>1?' '+(index+1):''}</dt><dd><code>{String(item.query.request.method??'GET')} {String(item.query.request.path??'')}</code></dd></div>)}
      {showOutcome&&flow.recovery&&<div><dt>恢复请求</dt><dd><code>{flow.recovery.method} {flow.recovery.relative_path}</code></dd></div>}
    </dl></details>}
  </div>
}
