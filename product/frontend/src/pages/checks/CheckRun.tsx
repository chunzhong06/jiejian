import {useMilestoneTransition} from '../../shared/lib/milestone'
import {Progress} from '../../shared/ui/Progress'
import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import { useEffect, useState } from 'react';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import { currentChecksApi as api } from '../../entities/check/api/currentChecks';
import {ActionLink,Button} from '../../shared/ui/actions'
import {PageError, Notice, Badge, } from "../../shared/ui/feedback";
import { Heading } from "../../shared/ui/layout";
import { assertProject } from '../../shared/model/page';
import { text } from '../../shared/lib/format';
import {historyLocation,returnDestination,returnDestinationLabel,scopedPath} from '../../shared/lib/navigation'
import { useRead } from '../../shared/lib/useRead';
import { Report } from './report/Report';
import type { ReportsProps } from './types';
import {ScenarioProgress} from './ScenarioProgress';
import {RoutineRunContext} from '../../entities/check/ui/RoutineRunContext';
import {WorkflowSteps} from '../../shared/ui/WorkflowSteps';
import {SectionHeading,TaskActions} from '../../shared/ui/layout';
import {useExampleJourney} from '../../entities/application/model/exampleJourney';
import {OfficialResultContext} from './OfficialResultContext';
export function Run({ projectId, name, official, runId, route, onError, refresh, archive = false }: ReportsProps & {
    runId: string;
}) {
    const state = useRead('run:' + projectId + ':' + runId, async (signal) => { const status = await api.status(runId, signal); assertProject(status.run.project_id, projectId); if (status.run.run_id !== runId)
        throw new Error('检查记录不匹配。'); if (status.result_integrity !== 'VALID')
        return { status, story: null }; const story = await api.story(runId, signal); assertProject(story.project_id, projectId); if (story.run_id !== runId || story.verdict !== status.run.verdict)
        throw new Error('报告与检查记录不一致。'); return { status, story }; }, data => data && ['QUEUED', 'RUNNING'].includes(data.status.run.lifecycle) ? 2000 : 0);
    const completion=useMilestoneTransition<HTMLDivElement>('report:'+runId,state.data?Boolean(state.data.story):undefined,state.data?.story?.repair_verification?.status==='VERIFIED'?'repair':'report');
    const finalizing=Boolean(state.data&&['RUNNING','QUEUED'].includes(state.data.status.run.lifecycle)&&state.data.status.progress?.phase==='FINALIZING');
    const requestedOrigin=returnDestination(route.query.get('return_to'));
    // 归档报告只接续本归档项目的阅读位置，避免当前应用的回程覆盖历史上下文。
    const origin = archive ? requestedOrigin?.startsWith('/archive?')&&new URLSearchParams(requestedOrigin.split('?')[1]).get('project_id')===projectId?requestedOrigin:null : requestedOrigin;
    const originLabel = origin ? returnDestinationLabel(origin) : '全部检查记录';
    const [busy, setBusy] = useState(false);
    const journey=useExampleJourney(projectId,official&&!archive,state.data?.story?.run_id);
    // 历史报告不继承当前示例阶段；仅准确对应起始检查时接续演练。
    const continuation=!journey.error&&journey.data?.stage==='BASELINE_RESULT'&&journey.data.run_id===runId?{
        note:<><strong>正常起点已建立。</strong> 接下来保留访问要求，检查一次移除了内部包限制的代码修改。</>,
        action:<ActionLink navigationScope="page" kind="primary" href={'#'+scopedPath('/environment?view=change',projectId)}>查看错误修改</ActionLink>,
    }:undefined;
    useEffect(() => { if (state.data?.story)
        refresh(); }, [Boolean(state.data?.story)]);
    if (state.loading)
        return <PageSkeleton layout="report" view="/reports" title="本次检查"/>;
    if (state.error && !state.data)
        return <PageError title="本次检查" error={state.error} actions={<ActionLink href={'#'+scopedPath(origin??(archive?'/archive?project_id='+encodeURIComponent(projectId):historyLocation(projectId)))}>{origin?originLabel:archive?'返回归档检查记录':'返回检查记录'}</ActionLink>}/>;
    if (!state.data)
        return null;
    const { status, story } = state.data, running = ['RUNNING', 'QUEUED'].includes(status.run.lifecycle);
    const stopping=Boolean(status.job?.cancel_requested&&running);
    const phase=status.run.lifecycle==='QUEUED'?-1:({PREPARING:0,EXECUTING:1,FINALIZING:2}[status.progress?.phase??'PREPARING']);
    const currentCase=status.progress?.current_case;
    const stale=state.error?<Notice tone="caution">更新失败，显示上次读取的检查状态{state.receivedAt?`（${new Date(state.receivedAt).toLocaleTimeString('zh-CN')}）`:''}。恢复网络后可使用右上角刷新，已提交的检查仍沿原记录查询。</Notice>:null;
    if (story)
        return <div ref={completion}>{stale}<Report context={official?<OfficialResultContext story={story} implementation={!journey.error&&journey.data?.run_id===runId?journey.data.implementation:undefined}/>:undefined} continuation={continuation} archiveName={archive?name:undefined} story={story} checkedAt={status.run.created_at_us} selectedCaseId={route.query.get('case_id')} tab={route.query.get('tab')} evidenceId={route.query.get('evidence_id')} recordId={route.query.get('record_id')} proofId={route.query.get('proof_id')} stepId={route.query.get('step_id')} readOnly={archive} basePath={archive ? '/archive?project_id=' + encodeURIComponent(projectId) : '/reports'+(origin?'?return_to='+encodeURIComponent(origin):'')} returnPath={origin ?? (archive ? '/archive?project_id=' + encodeURIComponent(projectId) : historyLocation(projectId))} returnLabel={origin?originLabel:undefined} onError={onError}/></div>;
    return <>{stale}<div className="jj-back-link jj-report-navigation"><ActionLink navigationScope="page" href={'#'+scopedPath(archive ? '/archive?project_id=' + encodeURIComponent(projectId) : origin ?? historyLocation(projectId))} kind="quiet"><ArrowLeftOutlined aria-hidden="true"/>{origin?originLabel:'全部检查记录'}</ActionLink>{archive&&<ActionLink href="#/environment">返回官方示例</ActionLink>}</div>
    <Heading eyebrow={archive?'已归档：'+name:'本次检查'} title={running?stopping?'正在停止这次检查':status.run.lifecycle==='QUEUED'?'已提交，等待执行':finalizing?'正在收尾并核对记录':status.progress?.phase==='PREPARING'?'正在准备本次执行':'正在核对业务结果':status.result_integrity==='INVALID'?'报告未通过完整性校验':'本次检查未形成可用结论'}/>
    <RoutineRunContext projectId={projectId} routine={status.routine} environment={status.environment} origin={'/reports?run_id='+runId} readOnly={archive}/>
    <section className="jj-run-workspace" aria-label="本次检查进展">
      <WorkflowSteps label="检查执行进展" steps={['准备执行','核对业务结果','汇总报告'].map((label,index)=>({id:String(index),label,state:index<phase?'complete' as const:index===phase?(running?'current' as const:'error' as const):'pending' as const}))}/>
      <div className="jj-run-reading"><section className="jj-run-progress"><SectionHeading title="执行进展" level={2} meta={<Badge tone={running?'accent':'caution'}>{stopping?'正在停止':running?status.run.lifecycle==='QUEUED'?'等待执行':finalizing?'正在汇总':'执行中':'检查已结束'}</Badge>}/>
        {status.progress&&<><p className="jj-run-count">{status.progress.planned_cases>0?`已完成 ${status.progress.completed_cases} / ${status.progress.planned_cases} 项`:'正在整理检查事项'}</p><Progress value={status.progress.planned_cases>0?status.progress.completed_cases:undefined} max={status.progress.planned_cases} active={running&&!stopping} label="检查进度"/></>}
        <p className="jj-progress-note">{stopping?'停止请求已提交，正在等待执行进程结束。已发送的操作与已形成的记录按实际结果保留。':running?finalizing?'逐项记录已返回，正在核对恢复情况并形成正式报告。':status.run.lifecycle==='QUEUED'?'原检查已被接纳，等待执行资源。离开页面后仍可从这条检查记录继续。':'正在执行原定范围并核对实际业务结果。你可以继续其他工作。':'目前没有可读取的完整报告，请根据执行情况处理后继续。'}</p>
      </section>
      {running?<section className="jj-run-current"><SectionHeading title="当前事项" level={2}/>{currentCase?<><h3>{text(currentCase.action_label)}</h3><dl className="jj-facts" data-layout="columns"><div><dt>操作账号</dt><dd>{text(currentCase.planned_subject_label)}</dd></div><div><dt>资源所有者</dt><dd>{text(currentCase.planned_resource_owner_label)}</dd></div><div><dt>测试资源</dt><dd>{currentCase.resource_id}</dd></div><div><dt>预期业务结果</dt><dd>{currentCase.expectation==='DENY'?'不应完成':'应当完成'}</dd></div></dl>{currentCase.effect_labels.length>0&&<p className="jj-small jj-muted">将核对：{currentCase.effect_labels.map(text).join('、')}</p>}</>:<p className="jj-muted">{finalizing?'实际记录已收齐，正在核对报告发布条件。':'开始具体检查后，这里显示正在使用的账号、资源与预期结果。'}</p>}</section>:<section className="jj-run-resolution"><SectionHeading title={status.job?.cause_code==='TARGET_UNREACHABLE'?'应用运行地址不可访问':status.job?.failure_phase==='PREPARE_RECOVERY'?'操作恢复准备未完成':'继续处理这次检查'} level={2}/><p>{status.job?.cause_code==='TARGET_UNREACHABLE'?'先确认应用正在运行，再核对检查范围。':'保留已有材料，核对当前运行和材料条件后继续。'}</p>{!archive&&status.job?.cause_code==='TARGET_UNREACHABLE'&&<ActionLink href={'#'+scopedPath('/application?'+new URLSearchParams({view:'environment',return_to:'/reports?run_id='+runId}),projectId)}>核对应用连接</ActionLink>}{status.job?.error_code&&<details><summary>诊断信息</summary><dl className="jj-facts"><div><dt>失败阶段</dt><dd>{status.job.failure_phase??'尚未记录'}</dd></div><div><dt>错误编号</dt><dd>{status.job.error_code}</dd></div>{status.job.cause_code&&<div><dt>原因</dt><dd>{status.job.cause_code}</dd></div>}</dl></details>}</section>}
      </div>
      <TaskActions separated note={running?'过程反馈用于说明执行情况，权限结论在正式报告中给出。':'这条检查记录与已经形成的材料继续保留。'}>{!archive&&!running&&<ActionLink navigationScope="page" href={'#'+scopedPath('/reports?'+new URLSearchParams({view:'plan',resume_run:runId,...(origin?{return_to:origin}:{})}))} kind="primary">重新核对检查范围</ActionLink>}{!archive&&running&&status.job&&<Button kind="danger" busy={busy} disabled={status.job.cancel_requested} onClick={()=>void(async()=>{setBusy(true);try{await api.cancel(status.job!.job_id);state.reload()}catch(error){onError(error)}finally{setBusy(false)}})()}>{status.job.cancel_requested?'正在停止':'停止这次检查'}</Button>}</TaskActions>
    </section><ScenarioProgress nodes={status.scenario_execution??[]}/></>;

}
