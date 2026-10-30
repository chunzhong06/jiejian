import { ArrowRightOutlined, SafetyOutlined, CarryOutOutlined, FileSearchOutlined } from '@ant-design/icons';
import type { WorkspaceViewDto, PrimaryTaskKind } from '../../entities/workspace/api/workspace';
import type { OfficialExperienceDto } from '../../entities/application/api/experience';
import { currentChecksApi } from '../../entities/check/api/currentChecks';
import { preparationApi } from '../../entities/preparation/api/preparation';
import { Button } from "../../shared/ui/actions";
import { Heading } from "../../shared/ui/layout";
import { Badge, Loading, ErrorNote } from "../../shared/ui/feedback";
import { assertProject, type PageProps } from '../../shared/model/page';
import { date } from '../../shared/lib/format';
import { go } from '../../shared/lib/navigation';
import { useRead } from '../../shared/lib/useRead';
const tasks: Partial<Record<PrimaryTaskKind, {
    title: string;
    action: string;
    path: string;
}>> = {
    ESTABLISH_BUSINESS_BOUNDARY: { title: '先约定这份应用的访问权限', action: '设置权限规则', path: '/permissions' }, REVIEW_BOUNDARY_PROPOSAL: { title: '有一份权限变更等待你确认', action: '审阅权限变更', path: '/permissions' }, REVIEW_PERMISSION_REVISION: { title: '业务已变化，需要重新确认权限', action: '查看受影响规则', path: '/permissions' }, COMPLETE_ALLOW_CONTROL: { title: '补充正常访问的对照规则', action: '查看权限规则', path: '/permissions' }, SELECT_ALLOW_CONTROL: { title: '选择用于对照的正常操作', action: '选择对照', path: '/preparation' }, PREPARE_TEST_IDENTITY: { title: '为检查准备真实登录账号', action: '准备测试账号', path: '/preparation' }, DEMONSTRATE_ACTION: { title: '录下一次完整的业务操作', action: '准备操作录制', path: '/preparation' }, PREPARE_ACTION_RESOURCE: { title: '确认本次检查使用的资源', action: '准备测试资源', path: '/preparation' }, COMPLETE_EFFECT_EVIDENCE: { title: '补齐能够核对业务结果的记录', action: '准备结果证明', path: '/preparation' }, COMPLETE_RECOVERY: { title: '为会改变数据的操作准备恢复方式', action: '准备恢复方式', path: '/preparation' }, RUN_CURRENT_CHECK: { title: '材料已就绪，可以预览本次检查', action: '预览检查', path: '/reports?view=plan' }, VERIFY_REPAIR: { title: '用同一组要求验证本次修改', action: '预览复验', path: '/reports?view=plan' }, VIEW_CURRENT_RESULT: { title: '检查已结束，查看实际结果', action: '阅读报告', path: '/reports' }, AUTHORIZE_SOURCE_ANALYSIS: { title: '确认界鉴可以读取的源码范围', action: '核对应用连接', path: '/application' }, CONFIRM_APPLICATION_ENDPOINT: { title: '确认待检查应用的访问地址', action: '核对访问地址', path: '/application' }, RUN_SOURCE_ANALYSIS: { title: '读取业务结构，为权限规则提供线索', action: '读取源码', path: '/application' }, PREPARE_AGENT_REPAIR: { title: '把已确认的问题交给开发工具处理', action: '查看问题报告', path: '/reports' }, REGISTER_SOURCE_CHANGE: { title: '让新代码与检查记录对应起来', action: '核对源码变化', path: '/changes?view=register' }
};
export function Home({ projectId, name, workspace, experience }: PageProps & {
    workspace: WorkspaceViewDto | null;
    experience: OfficialExperienceDto | null;
}) {
    const material = useRead('home-material:' + projectId, async (signal) => { const value = await preparationApi.get(projectId, signal); assertProject(value.project_id, projectId); return value; });
    const history = useRead('home-history:' + projectId, signal => currentChecksApi.history(projectId, {}, signal));
    const task = workspace?.primary_task, active = workspace?.active_check, taskView = task ? tasks[task.task_kind] : undefined;
    const running = active && ['QUEUED', 'RUNNING'].includes(active.run.lifecycle);
    const stopped = experience?.project_id === projectId && !experience.active;
    const target = taskView?.path ?? '/permissions';
    const destination = task?.proposal_id ? '/permissions?proposal_id=' + encodeURIComponent(task.proposal_id) : task?.repair_fingerprint ? '/permissions?repair_reference=' + encodeURIComponent(task.repair_fingerprint) : running ? '/reports?run_id=' + active.run.run_id : task?.run_id ? '/reports?run_id=' + task.run_id : task?.change_id ? target + (target.includes('?') ? '&' : '?') + 'change_id=' + task.change_id : target;
    const recent = history.data?.items.filter(item => item.status.result_integrity === 'VALID').slice(0, 4);
    const count = workspace?.actions.reduce((total, item) => total + item.current_permissions.filter(rule => rule.effective_state === 'ACTIVE').length, 0);
    return <><Heading eyebrow="应用概览" title={name} actions={<Button onClick={() => go('/application')}>管理连接</Button>}/>
    <div className="jj-home-workspace" data-page-pending={!workspace || material.loading || history.loading || undefined}><section className="jj-home-focus"><div><p className="jj-eyebrow">{running ? '正在检查' : stopped ? '示例已停止' : '接下来'}</p><h2>{running ? '正在验证权限与实际业务结果' : stopped ? '启动示例后继续检查' : taskView?.title ?? (workspace ? workspace.actions.length ? '查看权限与最新检查进展' : '先确认应用需要哪些访问权限' : '正在读取应用状态')}</h2>{task?.unavailable_reason && !task.can_execute && <p className="jj-small jj-muted">{task.unavailable_reason}</p>}{running && active.progress && <p className="jj-small jj-muted">已完成 {active.progress.completed_cases} / {active.progress.planned_cases} 项</p>}</div><Button kind="primary" disabled={Boolean(task && taskView && !task.can_execute && !running && !stopped)} onClick={() => go(stopped ? '/environment' : destination)}>{running ? '查看进度' : stopped ? '打开示例环境' : taskView?.action ?? '查看权限规则'}<ArrowRightOutlined aria-hidden="true"/></Button></section>
    {material.error && <ErrorNote error={material.error} onRetry={material.reload}/>}<div className="jj-home-cards"><button onClick={() => go('/permissions')}><SafetyOutlined aria-hidden="true"/><strong>访问权限</strong><span>{count ?? '—'} 条生效规则</span><small>{workspace?.actions.length ?? '—'} 项业务动作</small></button><button onClick={() => go('/preparation')}><CarryOutOutlined aria-hidden="true"/><strong>检查材料</strong><span>{material.data ? !material.data.actions.length ? '等待确认权限' : material.data.preparation_complete ? '已齐备' : '仍有待准备项' : '正在核对'}</span><small>{material.data?.actions.length ? `${material.data.actions.filter(item => item.preparation_complete).length} / ${material.data.actions.length} 项动作已准备` : ''}</small></button><button onClick={() => go('/reports')}><FileSearchOutlined aria-hidden="true"/><strong>检查记录</strong><span>{history.data ? `${history.data.items.length}${history.data.next_cursor ? '+' : ''} 次检查` : '正在读取'}</span><small>按检查时的范围保存</small></button></div></div>
    <section className="jj-home-history"><div className="jj-section-header jj-near-heading"><h2>最近的检查</h2><Button kind="quiet" onClick={() => go('/reports')}>全部报告 <ArrowRightOutlined aria-hidden="true"/></Button></div>{history.error ? <ErrorNote error={history.error} onRetry={history.reload}/> : history.loading ? <Loading /> : recent?.length ? <div className="jj-recent-list">{recent.map(item => <button onClick={() => go('/reports?run_id=' + item.status.run.run_id)} key={item.status.run.run_id}><span className="jj-recent-meta"><span>{date(item.status.run.created_at_us)}</span><Badge tone={item.status.run.verdict === 'PASS' ? 'positive' : item.status.run.verdict === 'BLOCK' ? 'negative' : 'caution'}>{item.status.run.verdict === 'PASS' ? '符合规则' : item.status.run.verdict === 'BLOCK' ? '存在问题' : '待确认'}</Badge></span><strong>{item.action_labels.join('、') || '权限检查'}</strong><span className="jj-card-open">阅读报告 <ArrowRightOutlined aria-hidden="true"/></span></button>)}</div> : <p className="jj-small jj-muted">完成首次检查后，报告会出现在这里。</p>}</section>
  </>;
}
