import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import type { WorkspaceViewDto, PrimaryTaskKind } from '../../entities/workspace/api/workspace';
import type { OfficialExperienceDto } from '../../entities/application/api/experience';
import {workbenchApi} from '../../entities/application/api/workbench';
import {repairsApi} from '../../entities/check/api/repairs';
import './workbench.css';
import { currentChecksApi } from '../../entities/check/api/currentChecks';
import { preparationApi } from '../../entities/preparation/api/preparation';
import { Button } from "../../shared/ui/actions";
import { Heading } from "../../shared/ui/layout";
import { Badge, Loading, ErrorNote } from "../../shared/ui/feedback";
import { assertProject, type PageProps } from '../../shared/model/page';
import { date } from '../../shared/lib/format';
import { go, scopedPath } from '../../shared/lib/navigation';
import { useRead } from '../../shared/lib/useRead';
const tasks: Partial<Record<PrimaryTaskKind, {
    title: string;
    action: string;
    path: string;
}>> = {
    ESTABLISH_BUSINESS_BOUNDARY: { title: '先约定这份应用的访问权限', action: '设置权限规则', path: '/permissions' }, REVIEW_BOUNDARY_PROPOSAL: { title: '有一份权限变更等待你确认', action: '审阅权限变更', path: '/permissions' }, REVIEW_PERMISSION_REVISION: { title: '业务已变化，需要重新确认权限', action: '查看受影响规则', path: '/permissions' }, COMPLETE_ALLOW_CONTROL: { title: '补充正常访问的对照规则', action: '查看权限规则', path: '/permissions' }, SELECT_ALLOW_CONTROL: { title: '选择用于对照的正常操作', action: '选择对照', path: '/preparation' }, PREPARE_TEST_IDENTITY: { title: '为检查准备真实登录账号', action: '准备测试账号', path: '/preparation' }, DEMONSTRATE_ACTION: { title: '整理要验证的业务操作', action: '打开测试场景', path: '/testing' }, PREPARE_ACTION_RESOURCE: { title: '确认本次检查使用的资源', action: '准备测试资源', path: '/preparation' }, COMPLETE_EFFECT_EVIDENCE: { title: '补齐能够核对业务结果的记录', action: '准备结果证明', path: '/preparation' }, COMPLETE_RECOVERY: { title: '为会改变数据的操作准备恢复方式', action: '准备恢复方式', path: '/preparation' }, RUN_CURRENT_CHECK: { title: '材料已就绪，可以预览本次检查', action: '预览检查', path: '/reports?view=plan' }, VERIFY_REPAIR: { title: '用同一组要求验证本次修改', action: '预览复验', path: '/reports?view=plan' }, VIEW_CURRENT_RESULT: { title: '检查已结束，查看实际结果', action: '阅读报告', path: '/reports' }, AUTHORIZE_SOURCE_ANALYSIS: { title: '确认界鉴可以读取的源码范围', action: '核对应用连接', path: '/application' }, CONFIRM_APPLICATION_ENDPOINT: { title: '确认待检查应用的访问地址', action: '核对访问地址', path: '/application' }, RUN_SOURCE_ANALYSIS: { title: '读取业务结构，为权限规则提供线索', action: '读取源码', path: '/application' }, PREPARE_AGENT_REPAIR: { title: '把已确认的问题交给开发工具处理', action: '查看问题报告', path: '/reports' }, REGISTER_SOURCE_CHANGE: { title: '让新代码与检查记录对应起来', action: '核对源码变化', path: '/changes?view=register' }
};
const taskDetails: Partial<Record<PrimaryTaskKind, string>> = {
    ESTABLISH_BUSINESS_BOUNDARY: '明确角色、资源与访问要求，作为后续验证的依据。',
    REVIEW_BOUNDARY_PROPOSAL: '比较本次变更与当前要求，确认后再让新规则生效。已有规则和历史检查会保留。',
    PREPARE_TEST_IDENTITY: '登录实际测试账号并核对主体，后续场景沿用这些受控会话。',
    DEMONSTRATE_ACTION: '从已有请求或录制整理操作步骤，明确目标请求、资源输入和必要的恢复方式。',
    RUN_CURRENT_CHECK: '预览本次规则、身份、资源和业务结果；确认范围后再发起检查。',
    VIEW_CURRENT_RESULT: '阅读本轮结论和依据，继续调查证据缺口或按原问题验证修改。',
};
export function Home({ projectId, name, workspace, experience }: PageProps & {
    workspace: WorkspaceViewDto | null;
    experience: OfficialExperienceDto | null;
}) {
    const material = useRead('home-material:' + projectId, async (signal) => { const value = await preparationApi.get(projectId, signal); assertProject(value.project_id, projectId); return value; });
    const history = useRead('home-history:' + projectId, signal => currentChecksApi.history(projectId, {}, signal));
    const assets=useRead('home-assets:'+projectId,signal=>Promise.all([workbenchApi.environments(projectId,signal),workbenchApi.sources(projectId,signal),repairsApi.project(projectId)]));
    const environment=assets.data?.[0],sources=assets.data?.[1],issues=assets.data?.[2].tasks.filter(item=>item.status!=='VERIFIED');
    const task = workspace?.primary_task, active = workspace?.active_check, taskView = task ? tasks[task.task_kind] : undefined;
    const running = active && ['QUEUED', 'RUNNING'].includes(active.run.lifecycle);
    const stopped = experience?.project_id === projectId && !experience.active;
    const target = taskView?.path ?? '/permissions';
    let destination = running ? '/reports?run_id=' + active.run.run_id : task?.proposal_id ? '/permissions?proposal_id=' + encodeURIComponent(task.proposal_id) : task?.repair_fingerprint ? '/permissions?repair_reference=' + encodeURIComponent(task.repair_fingerprint) : task?.run_id ? '/reports?run_id=' + task.run_id : task?.change_id ? target + (target.includes('?') ? '&' : '?') + 'change_id=' + task.change_id : target;
    if (!running && task?.business_action_id && ['/preparation', '/testing'].some(path => destination.startsWith(path))) {
        destination += (destination.includes('?') ? '&' : '?') + 'action_id=' + encodeURIComponent(task.business_action_id);
    }
    const focusedResult = !running && task?.task_kind==='VIEW_CURRENT_RESULT' && workspace && workspace.latest_result?.run_id===task.run_id ? workspace.latest_result : null;
    const recent = history.data?.items.filter(item => item.status.result_integrity === 'VALID' && item.status.run.run_id!==focusedResult?.run_id).slice(0, 4);
    const count = workspace?.actions.reduce((total, item) => total + item.current_permissions.filter(rule => rule.effective_state === 'ACTIVE').length, 0);
    const environmentAddress=environment?.active_environment?.target.base_url??environment?.confirmed_endpoint;
    const detail = running ? '检查在后台继续执行。可以离开当前页面，稍后回到同一次运行查看进度与结果。' : stopped ? '已保存的权限、场景和报告仍在原应用中；重新启动后可以接着工作。' : task ? taskDetails[task.task_kind] ?? task.why_now : '从已有权限、测试场景或检查结果继续当前工作。';
    return <><Heading eyebrow="工作台" title={name}>持续维护权限要求、测试场景和实际检查结果。</Heading>
    <div className="jj-home-layout" data-page-pending={!workspace || material.loading || history.loading || assets.loading || undefined}>
      <div className="jj-home-main">
        <section className="jj-home-current-task">
          <p className="jj-eyebrow">{running ? '正在检查' : stopped ? '示例已停止' : '当前工作'}</p>
          <h2>{running ? '正在验证权限与实际业务结果' : stopped ? '启动示例后继续检查' : taskView?.title ?? (workspace ? workspace.actions.length ? '查看权限与最新检查进展' : '先确认应用需要哪些访问权限' : '正在读取应用状态')}</h2>
          <p className="jj-home-task-description">{detail}</p>
          {focusedResult && <div className="jj-home-task-result"><Badge tone={focusedResult.verdict==='PASS'?'positive':focusedResult.verdict==='BLOCK'?'negative':'caution'}>{focusedResult.verdict==='PASS'?'本轮符合规则':focusedResult.verdict==='BLOCK'?'本轮存在问题':'本轮证据不足'}</Badge><p>{focusedResult.summary}</p></div>}
          {running && active.progress && <div className="jj-home-task-progress"><span>已完成 {active.progress.completed_cases} / {active.progress.planned_cases} 项</span><progress aria-label="检查进度" value={active.progress.completed_cases} max={active.progress.planned_cases || 1}/></div>}
          {task?.unavailable_reason && !task.can_execute && !running && <p className="jj-small jj-muted" role="status">{task.unavailable_reason}</p>}
          <footer><span className="jj-small jj-muted">{running?'离开页面后，当前检查仍会继续。':stopped?'已保存的资料与报告可以继续查阅。':'沿用当前已确认的规则与资料'}</span><Button kind="primary" disabled={Boolean(task && taskView && !task.can_execute && !running && !stopped)} onClick={() => go(stopped ? '/environment' : destination)}>{running ? '查看进度' : stopped ? '打开示例环境' : taskView?.action ?? '查看权限规则'}<ArrowRightOutlined aria-hidden="true"/></Button></footer>
        </section>
        <div className="jj-home-metrics">
          <button onClick={()=>go('/permissions')}><span>访问权限</span><strong>{count??'—'}<small>条生效规则</small></strong><small>{workspace?.actions.length??'—'} 项业务动作</small></button>
          <button onClick={()=>go('/testing')}><span>测试准备</span><strong>{material.data?.actions.length?material.data.actions.filter(item=>item.preparation_complete).length:'—'}<small>{material.data?.actions.length?'/ '+material.data.actions.length+' 项动作':'等待确认权限'}</small></strong><small>{material.data?.preparation_complete?'当前材料已齐备':'按场景补齐所需资料'}</small></button>
          <button onClick={()=>go('/issues')}><span>待处理问题</span><strong>{issues?.length??'—'}<small>项</small></strong><small>保留原问题与正常对照</small></button>
        </div>
        <section className="jj-home-check-history"><div className="jj-section-header"><h2>{focusedResult?'更早的检查':'最近的检查'}</h2><Button kind="quiet" onClick={()=>go('/reports')}>全部报告 <ArrowRightOutlined aria-hidden="true"/></Button></div>{history.error?<ErrorNote error={history.error}/>:history.loading?<Loading/>:recent?.length?<div className="jj-home-check-list">{recent.map(item=><button onClick={()=>go('/reports?run_id='+item.status.run.run_id)} key={item.status.run.run_id}><div><strong>{item.action_labels.join('、')||'权限检查'}</strong><small>{date(item.status.run.created_at_us)}</small></div><Badge tone={item.status.run.verdict==='PASS'?'positive':item.status.run.verdict==='BLOCK'?'negative':'caution'}>{item.status.run.verdict==='PASS'?'符合规则':item.status.run.verdict==='BLOCK'?'存在问题':'待确认'}</Badge><ArrowRightOutlined aria-hidden="true"/></button>)}</div>:<p className="jj-small jj-muted">{focusedResult?'后续检查会持续保留各轮范围和依据。':'尚无检查记录。完成准备后，每轮结果都会保留在这里。'}</p>}</section>
      </div>
      <aside className="jj-home-context">
        <section><header><h2>当前环境</h2>{environmentAddress&&<Badge tone={environment?.endpoint_reachable?'positive':'neutral'}>{environment?.endpoint_reachable?'最近核验可达':environment?.endpoint_reachable===false?'未连通':'待核验'}</Badge>}</header>
          {assets.loading?<p className="jj-small jj-muted">正在读取应用资料</p>:<dl className="jj-facts"><div><dt>环境</dt><dd>{environment?.active_environment?.name??'尚未保存环境'}</dd></div>{environmentAddress&&<div><dt>目标地址</dt><dd className="jj-mono">{environmentAddress}</dd></div>}<div><dt>源码</dt><dd>{environment?.source_available?'已关联本地目录':'尚未关联'}</dd></div>{environment?.active_environment?.deployment_label&&<div><dt>部署声明</dt><dd>{environment.active_environment.deployment_label}<small>版本未核对</small></dd></div>}</dl>}
          <Button kind="quiet" onClick={()=>go('/application?view=environment')}>{environmentAddress?'管理运行环境':'设置运行环境'}<ArrowRightOutlined aria-hidden="true"/></Button>
        </section>
        <section><header><h2>应用资料</h2></header><nav aria-label="应用资料快捷入口"><a href={'#'+scopedPath('/application?view=sources',projectId)}><span>接口资料</span><span>{sources?sources.sources.reduce((sum,item)=>sum+item.requests.length,0)+' 个请求':'读取中'}<ArrowRightOutlined aria-hidden="true"/></span></a><a href={'#'+scopedPath('/preparation?identities=1',projectId)}><span>身份与会话</span><ArrowRightOutlined aria-hidden="true"/></a><a href={'#'+scopedPath('/preparation?proof_sources=1',projectId)}><span>业务结果证明</span><ArrowRightOutlined aria-hidden="true"/></a></nav></section>
        {assets.error&&<ErrorNote error={assets.error}/>}
      </aside>
    </div>{material.error&&<ErrorNote error={material.error}/>}</>;
}
