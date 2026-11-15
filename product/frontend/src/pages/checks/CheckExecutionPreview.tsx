import type {CheckPreview} from '../../entities/check/api/currentChecks'
import type {ActionPreparation} from '../../entities/preparation/api/preparation'
import {conditionLabels} from '../../entities/permission/ui/RuleConditions'
import {TaskSurface} from '../../shared/ui/TaskSurface'
import {Button} from '../../shared/ui/actions'
import {Badge,Notice} from '../../shared/ui/feedback'
import {SectionHeading} from '../../shared/ui/layout'
import {text} from '../../shared/lib/format'

/** 阅读服务已形成的实际安排；提交仍由原计划所有者重核指纹与原操作回执。 */
export function CheckExecutionPreview({preview,actions,identities,busy,disabled,onBack,onScope,onSubmit}:{preview:CheckPreview;actions:ActionPreparation[];identities:Array<{identity_id:string;label:string}>;busy:boolean;disabled:boolean;onBack:()=>void;onScope:()=>void;onSubmit:()=>void}){
 const identity=(id:string|null)=>id===null?'未登录访客':text(identities.find(item=>item.identity_id===id)?.label??'所选测试账号')
 return <TaskSurface width="wide" title="确认这次检查" description="核对实际使用的账号、测试数据与预期结果。开始后会执行真实业务操作，并读取独立记录形成报告。" onBack={onBack} backLabel="返回检查准备" backDisabled={busy} actions={<><Button disabled={busy} onClick={onScope}>调整检查范围</Button><Button kind="primary" busy={busy} disabled={disabled||!preview.can_execute} onClick={onSubmit}>开始检查</Button></>}>
  <div className="jj-execution-preview">
   <section className="jj-execution-summary"><SectionHeading title="本次执行范围" level={2} meta={<Badge tone={preview.can_execute?'positive':'caution'}>{preview.can_execute?'具备执行条件':'仍需处理准备事项'}</Badge>}/><dl className="jj-facts" data-layout="columns"><div><dt>业务操作</dt><dd>{preview.action_count} 项</dd></div><div><dt>实际检查</dt><dd>{preview.case_count} 项</dd></div><div><dt>规则范围</dt><dd>{preview.selection?`选定 ${preview.selection.selected.length} 条，另加正常对照 ${preview.selection.added_controls.length} 条`:'当前可执行的完整权限范围'}</dd></div></dl>{Boolean(preview.selection?.omitted.length)&&<p className="jj-muted">另有 {preview.selection!.omitted.length} 条规则未纳入本次检查。</p>}</section>
   {!preview.can_execute&&<Notice tone="caution">本次准备条件已变化。返回检查准备处理缺项后，再核对实际执行安排。</Notice>}
   <section><SectionHeading title="实际执行安排" level={2}/><p className="jj-execution-note">允许与禁止的操作一同保留，用于核对权限要求和正常功能。</p>{preview.actions.map(action=><section className="jj-execution-action" key={action.action_id}><SectionHeading title={text(actions.find(item=>item.action_id===action.action_id&&item.action_revision===action.action_revision)?.display_name??'当前业务操作')} level={3} appearance="group"/><div className="jj-execution-table-wrap"><table className="jj-content-table jj-execution-table"><thead><tr><th scope="col">操作账号</th><th scope="col">预期业务结果</th><th scope="col">资源所有者</th><th scope="col">测试数据与条件</th></tr></thead><tbody>{action.cases.map(item=><tr key={item.case_id}><td data-label="操作账号">{identity(item.subject_test_identity_id)}</td><td data-label="预期业务结果">{item.batch_effect_expectation==='ABSENT'?'不应产生效果':item.permission.expectation==='DENY'?'不应完成':'应当完成'}</td><td data-label="资源所有者">{identity(item.resource_owner_test_identity_id)}</td><td data-label="测试数据与条件">{item.resource_id}{conditionLabels(item.permission.conditions).length>0&&<p className="jj-small jj-muted">{conditionLabels(item.permission.conditions).join('，')}</p>}</td></tr>)}</tbody></table></div></section>)}</section>
   {preview.scenario&&<section><SectionHeading title="组合场景" level={2}/><p>{text(preview.scenario.document.label)}。基础检查之后执行所选实验，各实验保留正常对照与恢复安排。</p></section>}
   <section className="jj-execution-consequence"><SectionHeading title="开始后会发生什么" level={2}/><p>按上述范围执行操作，核对实际身份、业务结果与必要恢复。可以离开页面，再从原检查记录继续查看；停止请求与实际结束分别反馈。</p><p className="jj-muted">执行中的请求状态用于说明过程，权限结论在正式报告形成后给出。</p></section>
  </div>
 </TaskSurface>
}
