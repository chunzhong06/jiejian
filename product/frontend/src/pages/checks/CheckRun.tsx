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
export function Run({ projectId, name, runId, route, onError, refresh, archive = false }: ReportsProps & {
    runId: string;
}) {
    const state = useRead('run:' + projectId + ':' + runId, async (signal) => { const status = await api.status(runId, signal); assertProject(status.run.project_id, projectId); if (status.run.run_id !== runId)
        throw new Error('检查记录不匹配。'); if (status.result_integrity !== 'VALID')
        return { status, story: null }; const story = await api.story(runId, signal); assertProject(story.project_id, projectId); if (story.run_id !== runId || story.verdict !== status.run.verdict)
        throw new Error('报告与检查记录不一致。'); return { status, story }; }, data => data && ['QUEUED', 'RUNNING'].includes(data.status.run.lifecycle) ? 2000 : 0);
    const completion=useMilestoneTransition<HTMLDivElement>('report:'+runId,state.data?Boolean(state.data.story):undefined,state.data?.story?.repair_verification?.status==='VERIFIED'?'repair':'report');
    const finalizing=Boolean(state.data&&['RUNNING','QUEUED'].includes(state.data.status.run.lifecycle)&&state.data.status.progress&&state.data.status.progress.planned_cases>0&&state.data.status.progress.completed_cases>=state.data.status.progress.planned_cases);
    const origin = archive ? null : returnDestination(route.query.get('return_to'));
    const originLabel = origin ? returnDestinationLabel(origin) : '全部检查记录';
    const [busy, setBusy] = useState(false);
    useEffect(() => { if (state.data?.story)
        refresh(); }, [Boolean(state.data?.story)]);
    if (state.loading)
        return <PageSkeleton view="/reports" title="检查报告"/>;
    if (state.error && !state.data)
        return <PageError title="本次检查" error={state.error}/>;
    if (!state.data)
        return null;
    const { status, story } = state.data, running = ['RUNNING', 'QUEUED'].includes(status.run.lifecycle);
    const stale=state.error?<Notice tone="caution">更新失败，显示上次读取的检查状态{state.receivedAt?`（${new Date(state.receivedAt).toLocaleTimeString('zh-CN')}）`:''}。恢复网络后可使用右上角刷新，已提交的检查仍沿原记录查询。</Notice>:null;
    if (story)
        return <div ref={completion}>{stale}<Report archiveName={archive?name:undefined} story={story} checkedAt={status.run.created_at_us} selectedCaseId={route.query.get('case_id')} tab={route.query.get('tab')} evidenceId={route.query.get('evidence_id')} recordId={route.query.get('record_id')} proofId={route.query.get('proof_id')} stepId={route.query.get('step_id')} readOnly={archive} basePath={archive ? '/archive?project_id=' + encodeURIComponent(projectId) : '/reports'+(origin?'?return_to='+encodeURIComponent(origin):'')} returnPath={archive ? '/archive?project_id=' + encodeURIComponent(projectId) : origin ?? historyLocation(projectId)} returnLabel={origin?originLabel:undefined} onError={onError}/></div>;
    return <>{stale}<div className="jj-back-link jj-report-navigation"><ActionLink navigationScope="page" href={'#'+scopedPath(archive ? '/archive?project_id=' + encodeURIComponent(projectId) : origin ?? historyLocation(projectId))} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}{origin?originLabel:'全部检查记录'}</ActionLink>{archive&&<ActionLink href="#/environment">返回官方示例</ActionLink>}</div><Heading eyebrow={archive?'已归档：'+name:'本次检查'} title={running ? finalizing?'正在整理并发布报告':'正在核对业务结果' : status.result_integrity === 'INVALID' ? '报告未通过完整性校验' : '本次检查未形成可用结论'}/><RoutineRunContext projectId={projectId} routine={status.routine} environment={status.environment} origin={'/reports?run_id='+runId} readOnly={archive}/><section className="jj-panel jj-run-status"><div className="jj-run-status-content" data-has-failure={Boolean(!running && status.job?.error_code)}><div className="jj-run-status-progress"><header><div className="jj-object-line"><h2 className="jj-title-group">执行进展</h2><Badge tone={running ? 'accent' : 'caution'}>{running ? finalizing?'正在汇总':'执行中' : '检查已结束'}</Badge></div></header>{status.progress && <><h3 className="jj-plan-summary">{status.progress.planned_cases>0?`已完成 ${status.progress.completed_cases} / ${status.progress.planned_cases} 项`:'正在整理检查事项'}</h3><Progress value={status.progress.planned_cases>0?status.progress.completed_cases:undefined} max={status.progress.planned_cases} active={running} label="检查进度"/>{status.progress.current_case && <p className="jj-small jj-muted">{text(status.progress.current_case.action_label)}</p>}</>}{running ? <p className="jj-progress-note">{finalizing?'逐项执行已结束，正在核对记录并形成正式报告。报告发布后，这里会显示结论。':'结果将在记录核对完成后显示。你可以继续其他工作。'}</p> : <p className="jj-progress-note">目前没有可读取的完整报告，请先查看执行情况。权限结果需以正式报告为准。</p>}</div>{!running && status.job?.error_code && <div className="jj-run-failure"><h3>{status.job.cause_code === 'TARGET_UNREACHABLE' ? '应用运行地址不可访问' : status.job.failure_phase === 'PREPARE_RECOVERY' ? '操作恢复准备未完成' : '执行中遇到问题'}</h3><p className="jj-small jj-muted">{status.job.cause_code === 'TARGET_UNREACHABLE' ? '先确认应用正在运行，再核对检查范围。' : '保留已有材料，核对当前运行和材料条件后重试。'}</p><details><summary>诊断信息</summary><dl className="jj-facts"><div><dt>失败阶段</dt><dd>{status.job.failure_phase ?? '尚未记录'}</dd></div><div><dt>错误编号</dt><dd>{status.job.error_code}</dd></div>{status.job.cause_code && <div><dt>原因</dt><dd>{status.job.cause_code}</dd></div>}</dl></details></div>}</div><footer>{!archive && !running && <ActionLink navigationScope="page" href={'#'+scopedPath('/reports?'+new URLSearchParams({view:'plan',resume_run:runId,...(origin?{return_to:origin}:{})}))}  kind="default">重新核对检查范围</ActionLink>}{!archive && running && status.job && <Button kind="danger" busy={busy} disabled={status.job.cancel_requested} onClick={() => void (async () => { setBusy(true); try {
        await api.cancel(status.job!.job_id);
        state.reload();
    }
    catch (error) {
        onError(error);
    }
    finally {
        setBusy(false);
    } })()}>{status.job.cancel_requested ? '正在停止' : '停止这次检查'}</Button>}</footer></section><ScenarioProgress nodes={status.scenario_execution??[]}/></>;
}
