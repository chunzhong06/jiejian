import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import { useEffect, useState } from 'react';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { currentChecksApi as api } from '../../entities/check/api/currentChecks';
import { Button } from "../../shared/ui/actions";
import { Badge, ErrorNote } from "../../shared/ui/feedback";
import { Heading } from "../../shared/ui/layout";
import { assertProject } from '../../shared/model/page';
import { text } from '../../shared/lib/format';
import { go, historyLocation } from '../../shared/lib/navigation';
import { useRead } from '../../shared/lib/useRead';
import { Report } from './report/Report';
import type { ReportsProps } from './types';
export function Run({ projectId, runId, route, onError, refresh, archive = false }: ReportsProps & {
    runId: string;
}) {
    const state = useRead('run:' + projectId + ':' + runId, async (signal) => { const status = await api.status(runId, signal); assertProject(status.run.project_id, projectId); if (status.run.run_id !== runId)
        throw new Error('检查记录不匹配。'); if (status.result_integrity !== 'VALID')
        return { status, story: null }; const story = await api.story(runId, signal); assertProject(story.project_id, projectId); if (story.run_id !== runId || story.verdict !== status.run.verdict)
        throw new Error('报告与检查记录不一致。'); return { status, story }; }, data => data && ['QUEUED', 'RUNNING'].includes(data.status.run.lifecycle) ? 2000 : 0);
    const [busy, setBusy] = useState(false);
    useEffect(() => { if (state.data?.story)
        refresh(); }, [Boolean(state.data?.story)]);
    if (state.loading)
        return <PageSkeleton view="/reports" title="检查报告"/>;
    if (state.error)
        return <ErrorNote error={state.error} onRetry={state.reload}/>;
    if (!state.data)
        return null;
    const { status, story } = state.data, running = ['RUNNING', 'QUEUED'].includes(status.run.lifecycle);
    if (story)
        return <Report story={story} checkedAt={status.run.created_at_us} selectedCaseId={route.query.get('case_id')} tab={route.query.get('tab')} evidenceId={route.query.get('evidence_id')} recordId={route.query.get('record_id')} proofId={route.query.get('proof_id')} stepId={route.query.get('step_id')} readOnly={archive} basePath={archive ? '/archive?project_id=' + encodeURIComponent(projectId) : '/reports'} returnPath={archive ? '/archive?project_id=' + encodeURIComponent(projectId) : historyLocation(projectId)} onError={onError}/>;
    return <><div><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={() => go(archive ? '/archive?project_id=' + encodeURIComponent(projectId) : historyLocation(projectId))}>全部报告</Button></div><Heading eyebrow="本次检查" title={running ? '正在核对业务结果' : status.result_integrity === 'INVALID' ? '报告未通过完整性校验' : '本次检查未形成可用结论'}/><section className="jj-panel"><Badge tone={running ? 'accent' : 'caution'}>{running ? '执行中' : '检查已结束'}</Badge>{status.progress && <><h2 className="jj-plan-summary">已完成 {status.progress.completed_cases} / {status.progress.planned_cases} 项</h2><progress value={status.progress.completed_cases} max={status.progress.planned_cases || 1}/>{status.progress.current_case && <p className="jj-small jj-muted">{text(status.progress.current_case.action_label)}</p>}</>}{running ? <p className="jj-progress-note">结果将在记录核对完成后显示。你可以继续其他工作。</p> : <p className="jj-progress-note">执行结束状态不代表权限通过或违规。当前没有可供读取的已发布报告。</p>}{!running && status.job?.error_code && <div className="jj-run-failure"><h3>{status.job.cause_code === 'TARGET_UNREACHABLE' ? '应用运行地址不可访问' : status.job.failure_phase === 'PREPARE_RECOVERY' ? '操作恢复准备未完成' : '执行中遇到问题'}</h3><p className="jj-small jj-muted">{status.job.cause_code === 'TARGET_UNREACHABLE' ? '先确认应用正在运行，再核对检查范围。' : '保留已有材料，核对当前运行和材料条件后重试。'}</p><details><summary>诊断信息</summary><dl className="jj-facts"><div><dt>失败阶段</dt><dd>{status.job.failure_phase ?? '尚未记录'}</dd></div><div><dt>错误编号</dt><dd>{status.job.error_code}</dd></div>{status.job.cause_code && <div><dt>原因</dt><dd>{status.job.cause_code}</dd></div>}</dl></details></div>}{!archive && !running && <Button onClick={() => go('/reports?view=plan')}>重新核对检查范围</Button>}{!archive && running && status.job && <Button kind="danger" busy={busy} disabled={status.job.cancel_requested} onClick={() => void (async () => { setBusy(true); try {
        await api.cancel(status.job!.job_id);
        state.reload();
    }
    catch (error) {
        onError(error);
    }
    finally {
        setBusy(false);
    } })()}>{status.job.cancel_requested ? '正在停止' : '停止这次检查'}</Button>}</section></>;
}
