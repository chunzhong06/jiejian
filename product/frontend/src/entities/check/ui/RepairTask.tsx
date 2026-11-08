
import {WorkflowSteps} from '../../../shared/ui/WorkflowSteps'
import {useState} from 'react'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'

import type {RuleItem} from '../../permission/api/ruleWorkspace'
import {repairReference,type ProjectRepair} from '../api/repairs'
import {AgentHandoff} from '../ui/AgentHandoff'
import {ChangeRegistration,changeTargetOptions} from '../../source-change/ui/ChangeRegistration'
import {sourceChangesApi} from '../../source-change/api/sourceChanges'
import {developmentApi} from '../../source-change/api/development'
import {RuntimeActivation} from '../../source-change/ui/RuntimeActivation'
import {Button,ActionLink} from '../../../shared/ui/actions'
import {Badge,ErrorNote,Loading,Notice,ResultList} from '../../../shared/ui/feedback'
import {go,withReturnDestination,scopedPath} from '../../../shared/lib/navigation'
import {useRead} from '../../../shared/lib/useRead'
import {text,date} from '../../../shared/lib/format'
import {assertProject} from '../../../shared/model/page'

type Issue=ProjectRepair['tasks'][number]
export function RepairTask({rule,rules,issue,projectId,changeId,onError,onReload,returnTo,embedded=false,location}:{rule:RuleItem;rules:RuleItem[];issue:Issue;projectId:string;changeId?:string|null;returnTo?:string;embedded?:boolean;location?:string;onError:(error:unknown)=>void;onReload:()=>void}) {
    const [register,setRegister]=useState(false),[assist,setAssist]=useState(false),[runtimeReady,setRuntimeReady]=useState(false)
    const selected=changeId??issue.change_id
    const plainPath='/permissions?rule_id='+encodeURIComponent(rule.permission.intent_id)+'&view=repair&repair_reference='+encodeURIComponent(issue.contract.repair_fingerprint)
    const basePath=location??(returnTo?withReturnDestination(plainPath,returnTo):plainPath)
    const path=basePath+(selected?'&change_id='+encodeURIComponent(selected):'')
    const original='/reports?run_id='+encodeURIComponent(issue.contract.source_run_id)+'&case_id='+encodeURIComponent(issue.contract.source_case_id)+'&return_to='+encodeURIComponent(path)
    const detail=useRead(selected?'repair-change:'+projectId+':'+selected:null,async()=>{
        const [change,delivery]=await Promise.all([sourceChangesApi.show(projectId,selected!),developmentApi.details(projectId,selected!)])
        assertProject(change.manifest.project_id,projectId)
        if(delivery)assertProject(delivery.project_id,projectId)
        return{change,delivery}
    })
    const linked=detail.data&&((detail.data.change.manifest.repair_reference?.repair_fingerprint===issue.contract.repair_fingerprint)||detail.data.change.rule_targets?.some(target=>target.repair?.repair_fingerprint===issue.contract.repair_fingerprint))
    const verified=Boolean(selected&&issue.status==='VERIFIED'&&selected===issue.change_id&&issue.verification&&issue.verification.verification_scope!=='EXTERNAL_OBSERVATION'), failed=issue.status==='NOT_VERIFIED'&&selected===issue.change_id, stale=issue.status==='STALE'
    // 修改登记后进入条件核对；流程提示不替代运行加载和材料就绪门禁。
    const phase=verified?3:!selected||failed?1:2
    const gaps=detail.data?.change.revalidation.preparation_gaps??[]
    const plan='/reports?'+new URLSearchParams({view:'plan',change_id:selected??'',rule_id:rule.permission.intent_id,repair_reference:issue.contract.repair_fingerprint,return_to:path})
    const reload=()=>{detail.reload();onReload()}
    // 嵌入态沿用父页的问题标题，主动作留在当前任务内，原题依据作为辅助内容。
    const SectionTitle=embedded?'h3':'h2'
    const originalLink=<ActionLink navigationScope="page" href={'#'+scopedPath(original)} kind="quiet">查看原问题与证据<ArrowRightOutlined aria-hidden="true"/></ActionLink>
    const advance=!register&&(verified||!failed&&runtimeReady&&linked)?<div className="jj-repair-task-advance">{verified?<ActionLink navigationScope="page" href={'#'+scopedPath('/reports?run_id='+encodeURIComponent(issue.verification!.run_id)+'&return_to='+encodeURIComponent(path))} kind="primary">查看复验结果<ArrowRightOutlined aria-hidden="true"/></ActionLink>:<Button kind="primary" disabled={stale} onClick={()=>go(plan)}>{gaps.length?'补齐复验材料':'核对原问题复验范围'}<ArrowRightOutlined aria-hidden="true"/></Button>}</div>:null
    return <>
        {!embedded&&<div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(returnTo?withReturnDestination('/permissions?rule_id='+encodeURIComponent(rule.permission.intent_id),returnTo):'/permissions?rule_id='+encodeURIComponent(rule.permission.intent_id))} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}返回这条权限规则</ActionLink></div>}
        <section className="jj-repair-task" data-embedded={embedded||undefined}>
            {!embedded&&<header><div><span className="jj-eyebrow">权限问题处理</span><div className="jj-object-line"><h1>{text(rule.title)}</h1><Badge tone={verified?'positive':failed?'negative':stale?'caution':selected?'accent':'neutral'}>{verified?'修复已验证':failed?'原问题仍存在':selected?'继续修复与复验':'等待代码修改'}</Badge></div><p>{text(rule.resource_scope)}</p></div></header>}
            <WorkflowSteps className="jj-repair-task-progress" label="修复流程" steps={['登记代码修改','核对复验条件','查看复验结果'].map((label,index)=>({id:String(index),label,state:verified||phase>index+1?'complete' as const:phase===index+1?stale?'blocked' as const:'current' as const:'pending' as const}))}/>
            {stale&&<Notice tone="caution">权限规则已经变化，原问题暂不能按旧条件复验。请返回权限规则核对当前要求。</Notice>}<div className={'jj-repair-task-layout'+(verified?' is-verified':'')}><div className="jj-repair-task-main">
                {register?<ChangeRegistration options={changeTargetOptions(rules)} initialTargets={[{permission:rule.permission,repair:repairReference(issue.contract)}]} projectId={projectId} closeLabel="返回修复任务" onClose={()=>setRegister(false)} onError={onError} onSaved={id=>{setRegister(false);onReload();go(basePath+'&change_id='+encodeURIComponent(id))}}/>:
                verified?<section className="jj-repair-task-result"><SectionTitle className={embedded?"jj-title-group":undefined}>原问题已解决，正常功能保留</SectionTitle><p>这次复验已确认登记的代码修改解决了原问题。以下列出已核对的业务范围，完整依据保留在报告中。</p><ResultList label="复验结果" items={(['DENY','SELECTED_ALLOW','REGRESSION'] as const).map(role=>{const rows=issue.comparison?.filter(item=>item.role===role)??[];return {label:role==='DENY'?'原权限问题':role==='SELECTED_ALLOW'?'正常功能':'相关回归',status:<Badge tone={rows.length&&rows.every(item=>item.after_verdict==='SAFE'&&item.match_status==='MATCHED')?'positive':'neutral'}>{rows.length&&rows.every(item=>item.after_verdict==='SAFE'&&item.match_status==='MATCHED')?'已验证':'查看报告确认范围'}</Badge>} })}/></section>:
                !selected||failed?<section className="jj-repair-task-start"><SectionTitle className={embedded?"jj-title-group":undefined}>{failed?'继续修改原问题':'先完成代码修改'}</SectionTitle><p>{failed?'上次复验仍发现违反权限要求的结果。修改后继续登记，原问题和正常功能对照都会保留。':'在开发工具中完成修改，再回来登记实际文件变化。随后加载修改后的代码，验证原问题和正常功能。'}</p><div className="jj-repair-task-next"><Button kind="quiet" onClick={()=>setAssist(true)}>交给 Agent 协助</Button><Button kind="primary" disabled={stale} onClick={()=>setRegister(true)}>登记已完成的修改<ArrowRightOutlined aria-hidden="true"/></Button></div></section>:
                detail.loading?<Loading>正在读取这次修改</Loading>:detail.error?<ErrorNote error={detail.error}/>:detail.data&&!linked?<Notice tone="caution">这次修改没有关联当前原问题。请返回核对修复目标。</Notice>:detail.data&&<>
                    <section className="jj-repair-task-change"><div className="jj-section-header"><SectionTitle className={embedded?"jj-title-group":undefined}>已登记的修改</SectionTitle><span className="jj-small jj-muted">{date(detail.data.change.manifest.created_at_us)}</span></div><p>{text(detail.data.change.manifest.reason)}</p>
                    {detail.data.delivery?<RuntimeActivation key={selected} projectId={projectId} details={detail.data.delivery} onError={onError} onChanged={reload} onReady={setRuntimeReady}/>:<Notice tone="caution">这次修改缺少可读取的运行交付，请核对修改记录。</Notice>}
                    </section>
                    {runtimeReady&&<section className="jj-repair-task-readiness"><SectionTitle className={embedded?"jj-title-group":undefined}>{gaps.length?'复验前需要处理':'可以核对原问题复验范围'}</SectionTitle>{gaps.length?<p>{gaps.length} 项材料条件需要重新核对。已有账号设置、操作流程与证明配置会保留。</p>:<p>继续后核对原问题、正常功能和相关回归，再明确开始检查。</p>}</section>}
                </>}
                {embedded&&advance}
            </div><aside className="jj-repair-task-context"><SectionTitle className={embedded?"jj-title-caption":"jj-title-group"}>{verified?'复验范围与修改':'复验依据'}</SectionTitle><dl className="jj-facts" data-layout="columns"><div><dt>原问题</dt><dd>{text(rule.title)}</dd></div><div><dt>测试数据</dt><dd>{issue.contract.deny.identity.resource_id}</dd></div><div><dt>正常功能</dt><dd>原来允许的操作仍能完成</dd></div></dl><div className="jj-repair-task-context-actions">{detail.data&&<details><summary>查看修改文件</summary>{(['modified_paths','added_paths','removed_paths'] as const).flatMap(key=>detail.data!.change.change_set[key]).map(file=><p className="jj-path" key={file}>{file}</p>)}</details>}{embedded&&originalLink}{selected&&<ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/changes?change_id='+encodeURIComponent(selected),path))} kind="quiet">查看变更归档<ArrowRightOutlined aria-hidden="true"/></ActionLink>}</div></aside></div>
                {!embedded&&!register&&<footer>{originalLink}{advance}</footer>}
        </section>
        {assist&&<AgentHandoff projectId={projectId} runId={issue.contract.source_run_id} caseId={issue.contract.source_case_id} targets={[repairReference(issue.contract)]} repair onClose={()=>setAssist(false)}/>}
    </>
}
