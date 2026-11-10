import { useEffect } from 'react';
import LoadingOutlined from '@ant-design/icons/LoadingOutlined';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import ExclamationCircleOutlined from '@ant-design/icons/ExclamationCircleOutlined';
import ClockCircleOutlined from '@ant-design/icons/ClockCircleOutlined';
import { projectsApi } from '../../entities/application/api/projects';
import { useRead } from '../../shared/lib/useRead';
import { assertProject } from '../../shared/model/page';
import {scopedPath} from '../../shared/lib/navigation'
import {ActionLink} from '../../shared/ui/actions'

const needsAttention = (phase: string) => ['FAILED', 'BLOCKED', 'CLEANUP_REQUIRED'].includes(phase);
const phaseLabels: Record<string, string> = { STARTING: '正在准备', WAITING_FOR_LOGIN: '等待登录', SAVING: '正在保存', RUNNING: '正在执行', PENDING: '等待执行', RETRY_WAIT: '等待重试', CANCELLING: '正在停止并清理', FAILED: '未完成', BLOCKED: '需要处理', CLEANUP_REQUIRED: '待清理' };

export function Activity({ projectId }: { projectId: string }) {
    // 任务恢复入口来自服务端持久状态，不从当前页面是否 busy 推断后台任务是否仍在执行。
    const state = useRead('application-activity:' + projectId, async signal => {
        const value = await projectsApi.activity(projectId, signal);
        assertProject(value.project_id, projectId);
        return value;
    }, value => value?.items.some(item => !needsAttention(item.phase)) ? 2000 : 0);
    useEffect(() => {
        // 无活动任务时停止轮询；可能改变任务的写请求完成后由事件触发一次重新读取。
        window.addEventListener('jiejian:activity-changed', state.reload);
        return () => window.removeEventListener('jiejian:activity-changed', state.reload);
    }, [state.reload]);
    if (state.error && !state.data) return <aside className="jj-activity"><span className="jj-small jj-muted">当前任务未能读取，可使用右上角刷新。</span></aside>;
    if (!state.data?.items.length) return null;
    return <aside className="jj-activity" aria-label="当前应用的任务"><span className="jj-small jj-muted">当前任务</span>{state.error&&<div className="jj-small jj-muted" role="status">更新失败<details><summary>最后读取的状态</summary>{state.receivedAt&&<p>{new Date(state.receivedAt).toLocaleTimeString('zh-CN')}</p>}<p>原任务保留，可使用右上角刷新。</p></details></div>}{state.data.items.map(item => <ActionLink navigationScope="page" href={'#'+scopedPath(item.destination,projectId)} key={item.id} kind="quiet" data-attention={needsAttention(item.phase)}>{needsAttention(item.phase) ? <ExclamationCircleOutlined aria-hidden="true"/> : ['WAITING_FOR_LOGIN','PENDING','RETRY_WAIT'].includes(item.phase) ? <ClockCircleOutlined aria-hidden="true"/> : state.error?<ClockCircleOutlined aria-hidden="true"/>:<LoadingOutlined spin aria-hidden="true"/>}<span className="jj-activity-label"><strong>{item.label}</strong>{phaseLabels[item.phase] && <small>{phaseLabels[item.phase]}</small>}</span><ArrowRightOutlined aria-hidden="true"/></ActionLink>)}</aside>;
}
