import {useState} from 'react'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'
import CheckOutlined from '@ant-design/icons/CheckOutlined'
import type {RuleItem} from '../../entities/permission/api/ruleWorkspace'
import {repairReference,type ProjectRepair} from '../../entities/check/api/repairs'
import {AgentHandoff} from '../../entities/check/ui/AgentHandoff'
import {ChangeRegistration,changeTargetOptions} from '../../entities/source-change/ui/ChangeRegistration'
import {sourceChangesApi} from '../../entities/source-change/api/sourceChanges'
import {developmentApi} from '../../entities/source-change/api/development'
import {RuntimeActivation} from '../../entities/source-change/ui/RuntimeActivation'
import {Button} from '../../shared/ui/actions'
import {Badge,ErrorNote,Loading,Notice} from '../../shared/ui/feedback'
import {go} from '../../shared/lib/navigation'
import {useRead} from '../../shared/lib/useRead'
import {text,date} from '../../shared/lib/format'
import {assertProject} from '../../shared/model/page'

type Issue=ProjectRepair['tasks'][number]
export function RepairTask({rule,rules,issue,projectId,changeId,onError,onReload}:{rule:RuleItem;rules:RuleItem[];issue:Issue;projectId:string;changeId?:string|null;onError:(error:unknown)=>void;onReload:()=>void}) {
    const [register,setRegister]=useState(false),[assist,setAssist]=useState(false),[runtimeReady,setRuntimeReady]=useState(false)
    const selected=changeId??issue.change_id
    const basePath='/permissions?rule_id='+encodeURIComponent(rule.permission.intent_id)+'&view=repair&repair_reference='+encodeURIComponent(issue.contract.repair_fingerprint)
    const path=basePath+(selected?'&change_id='+encodeURIComponent(selected):'')
    const original='/reports?run_id='+encodeURIComponent(issue.contract.source_run_id)+'&case_id='+encodeURIComponent(issue.contract.source_case_id)+'&return_to='+encodeURIComponent(path)
    const detail=useRead(selected?'repair-change:'+projectId+':'+selected:null,async()=>{
        const [change,delivery]=await Promise.all([sourceChangesApi.show(projectId,selected!),developmentApi.details(projectId,selected!)])
        assertProject(change.manifest.project_id,projectId)
        if(delivery)assertProject(delivery.project_id,projectId)
        return{change,delivery}
    })
    const linked=detail.data&&((detail.data.change.manifest.repair_reference?.repair_fingerprint===issue.contract.repair_fingerprint)||detail.data.change.rule_targets?.some(target=>target.repair?.repair_fingerprint===issue.contract.repair_fingerprint))
    const verified=issue.status==='VERIFIED'&&selected===issue.change_id, failed=issue.status==='NOT_VERIFIED'&&selected===issue.change_id, stale=issue.status==='STALE'
    const phase=verified?3:!selected||failed?1:runtimeReady?2:1
    const gaps=detail.data?.change.revalidation.preparation_gaps??[]
    const prepare='/preparation?'+new URLSearchParams({change_id:selected??'',rule_id:rule.permission.intent_id,return_to:path})
    const plan='/reports?'+new URLSearchParams({view:'plan',change_id:selected??'',rule_id:rule.permission.intent_id,repair_reference:issue.contract.repair_fingerprint,return_to:path})
    const reload=()=>{detail.reload();onReload()}
    return <>
        <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={()=>go('/permissions?rule_id='+encodeURIComponent(rule.permission.intent_id))}>返回这条权限规则</Button></div>
        <section className="jj-repair-task">
            <header><div><span className="jj-eyebrow">权限问题处理</span><div className="jj-item-heading"><h1>{text(rule.title)}</h1><Badge tone={verified?'positive':failed?'negative':stale?'caution':selected?'accent':'neutral'}>{verified?'修复已验证':failed?'原问题仍存在':selected?'继续修复与复验':'等待代码修改'}</Badge></div><p>{text(rule.resource_scope)}</p></div></header>
            <ol className="jj-repair-task-progress" aria-label="修复流程">{['登记代码修改','核对复验条件','查看复验结果'].map((label,index)=><li key={label} aria-current={phase===index+1?'step':undefined} data-complete={phase>index+1||verified}><span>{phase>index+1||verified?<CheckOutlined aria-hidden="true"/>:index+1}</span>{label}</li>)}</ol>
            {stale&&<Notice tone="caution">权限规则已经变化，原问题暂不能按旧条件复验。请返回权限规则核对当前要求。</Notice>}<div className={'jj-repair-task-layout'+(verified?' is-verified':'')}><div className="jj-repair-task-main">
                {register?<ChangeRegistration options={changeTargetOptions(rules)} initialTargets={[{permission:rule.permission,repair:repairReference(issue.contract)}]} projectId={projectId} closeLabel="返回修复任务" onClose={()=>setRegister(false)} onError={onError} onSaved={id=>{setRegister(false);onReload();go(basePath+'&change_id='+encodeURIComponent(id))}}/>:
                verified?<section className="jj-repair-task-result"><h2>原问题已解决，正常功能保留</h2><div className="jj-repair-task-outcomes">{(['DENY','SELECTED_ALLOW','REGRESSION'] as const).map(role=>{const rows=issue.comparison?.filter(item=>item.role===role)??[];return <div key={role}><span>{role==='DENY'?'原权限问题':role==='SELECTED_ALLOW'?'正常功能':'相关回归'}</span><Badge tone={rows.length&&rows.every(item=>item.after_verdict==='SAFE'&&item.match_status==='MATCHED')?'positive':'neutral'}>{rows.length&&rows.every(item=>item.after_verdict==='SAFE'&&item.match_status==='MATCHED')?'已验证':'查看报告确认范围'}</Badge></div>})}</div></section>:
                !selected||failed?<section className="jj-repair-task-start"><h2>{failed?'继续修改原问题':'先完成代码修改'}</h2><p>{failed?'上次复验仍发现违反权限要求的结果。修改后继续登记，原问题和正常功能对照都会保留。':'在开发工具中修复这条权限问题，再回来登记实际文件变化。'}</p><div className="jj-repair-task-next"><Button kind="quiet" onClick={()=>setAssist(true)}>交给 Agent 协助</Button><Button kind="primary" disabled={stale} onClick={()=>setRegister(true)}>登记已完成的修改<ArrowRightOutlined aria-hidden="true"/></Button></div></section>:
                detail.loading?<Loading>正在读取这次修改</Loading>:detail.error?<ErrorNote error={detail.error}/>:detail.data&&!linked?<Notice tone="caution">这次修改没有关联当前原问题。请返回核对修复目标。</Notice>:detail.data&&<>
                    <section className="jj-repair-task-change"><div className="jj-section-header"><h2>已登记的修改</h2><span className="jj-small jj-muted">{date(detail.data.change.manifest.created_at_us)}</span></div><p>{text(detail.data.change.manifest.reason)}</p>
                    {detail.data.delivery?<RuntimeActivation key={selected} projectId={projectId} details={detail.data.delivery} onError={onError} onChanged={reload} onReady={setRuntimeReady}/>:<Notice tone="caution">这次修改缺少可读取的运行交付，请核对修改记录。</Notice>}
                    </section>
                    {runtimeReady&&<section className="jj-repair-task-readiness"><h2>{gaps.length?'复验前需要处理':'可以核对原题复验范围'}</h2>{gaps.length?<p>{gaps.length} 项材料条件需要重新核对。已有账号设置、操作流程与证明配置会保留。</p>:<p>继续后核对原问题、正常功能和相关回归，再明确开始检查。</p>}</section>}
                </>}
            </div><aside className="jj-repair-task-context"><h2 className="jj-title-group">{verified?'复验范围与修改':'这次复验要确认'}</h2><dl><div><dt>原问题</dt><dd>{text(rule.title)}</dd></div><div><dt>测试数据</dt><dd>{issue.contract.deny.identity.resource_id}</dd></div><div><dt>正常功能</dt><dd>原来允许的操作仍能完成</dd></div></dl><div className="jj-repair-task-context-actions"><details><summary>查看修改文件</summary>{detail.data?(['modified_paths','added_paths','removed_paths'] as const).flatMap(key=>detail.data!.change.change_set[key]).map(file=><p className="jj-path" key={file}>{file}</p>):<p>登记修改后显示实际文件变化。</p>}</details>{selected&&<Button kind="quiet" onClick={()=>go('/changes?change_id='+encodeURIComponent(selected))}>查看变更归档<ArrowRightOutlined aria-hidden="true"/></Button>}</div></aside></div>
                {!register&&<footer><Button kind="quiet" onClick={()=>go(original)}>查看原问题与证据<ArrowRightOutlined aria-hidden="true"/></Button><div className="jj-inline-actions">{verified&&<><Button kind="primary" onClick={()=>go('/reports?run_id='+encodeURIComponent(issue.verification!.run_id)+'&return_to='+encodeURIComponent(path))}>查看复验结果<ArrowRightOutlined aria-hidden="true"/></Button></>}{!verified&&!failed&&runtimeReady&&linked&&<Button kind="primary" disabled={stale} onClick={()=>go(gaps.length?prepare:plan)}>{gaps.length?'补齐复验材料':'核对原题复验范围'}<ArrowRightOutlined aria-hidden="true"/></Button>}</div></footer>}
        </section>
        {assist&&<AgentHandoff projectId={projectId} runId={issue.contract.source_run_id} caseId={issue.contract.source_case_id} targets={[repairReference(issue.contract)]} repair onClose={()=>setAssist(false)}/>}
    </>
}
