import {Progress} from '../../shared/ui/Progress'
import {taskDestination} from '../../entities/workspace/taskDestination';
import {Continuations} from './Continuations';
import type { WorkspaceViewDto } from '../../entities/workspace/api/workspace';
import type { OfficialExperienceDto } from '../../entities/application/api/experience';
import {workbenchApi} from '../../entities/application/api/workbench';
import {repairsApi} from '../../entities/check/api/repairs';
import './workbench.css';
import { currentChecksApi } from '../../entities/check/api/currentChecks';
import { preparationApi } from '../../entities/preparation/api/preparation';
import { ActionLink } from "../../shared/ui/actions";
import {Heading,ObjectIdentity} from "../../shared/ui/layout"
import {Badge, Loading, ErrorNote,Status} from "../../shared/ui/feedback"
import { assertProject, type PageProps } from '../../shared/model/page';
import { scopedPath, withReturnDestination } from '../../shared/lib/navigation';
import { useRead } from '../../shared/lib/useRead';
export function Home({ projectId, name, workspace, experience }: PageProps & {
    workspace: WorkspaceViewDto | null;
    experience: OfficialExperienceDto | null;
}) {
    const material = useRead('home-material:' + projectId, async (signal) => { const value = await preparationApi.get(projectId, signal); assertProject(value.project_id, projectId); return value; });
    const history = useRead('home-history:' + projectId, signal => currentChecksApi.history(projectId, {}, signal));
    const assets=useRead('home-assets:'+projectId,signal=>Promise.all([workbenchApi.environments(projectId,signal),workbenchApi.sourceSummary(projectId,signal),repairsApi.project(projectId)]));
    const environment=assets.data?.[0],sources=assets.data?.[1],issues=assets.data?.[2].tasks.filter(item=>item.status!=='VERIFIED');
    const task = workspace?.primary_task, active = workspace?.active_check;
    const running = active && ['QUEUED', 'RUNNING'].includes(active.run.lifecycle);
    const stopped = experience?.project_id === projectId && !experience.active;
    const destination = running ? '/reports?run_id=' + active.run.run_id : task ? taskDestination(task) : '/permissions';
    const focusedResult = !running && task?.task_kind==='VIEW_CURRENT_RESULT' && workspace && workspace.latest_result?.run_id===task.run_id ? workspace.latest_result : null;
    const recent = history.data?.items.filter(item => item.status.result_integrity === 'VALID' && item.status.run.run_id!==focusedResult?.run_id).slice(0, 4);
    const count = workspace?.actions.reduce((total, item) => total + item.current_permissions.filter(rule => rule.effective_state === 'ACTIVE').length, 0);
    const environmentAddress=environment?.active_environment?.target.base_url??environment?.confirmed_endpoint;
    const detail = running ? '检查在后台继续执行。可以离开当前页面，稍后回到同一次运行查看进度与结果。' : stopped ? '已保存的权限、场景和报告仍在原应用中；重新启动后可以接着工作。' : task ? task.why_now : '从已有权限、测试场景或检查结果继续当前工作。';
    const destinationHref=(path:string)=>'#'+scopedPath(withReturnDestination(path,'/workspace'),projectId);
    return <><Heading eyebrow="工作台" title={name}>从当前任务继续准备和检查，查看结果，或跟进已经发现的问题。</Heading>
    <div className="jj-home-layout" data-page-pending={!workspace || material.loading || history.loading || assets.loading || undefined}>
      <section className="jj-home-current-task" aria-labelledby="home-current-task">
        <p className="jj-eyebrow">{running ? '正在检查' : stopped ? '示例已停止' : '当前工作'}</p>
        <h2 id="home-current-task">{running ? '正在验证权限与实际业务结果' : stopped ? '启动示例后继续检查' : task?.title ?? (workspace ? workspace.actions.length ? '继续维护权限与检查方案' : '先确认应用需要哪些访问权限' : '正在读取应用状态')}</h2>
        <p className="jj-home-task-description">{detail}</p>{task?.unavailable_reason&&<p className="jj-small jj-muted">{task.user_responsibility}</p>}
        {focusedResult && <div className="jj-home-task-result"><Badge tone={focusedResult.verdict==='PASS'?'positive':focusedResult.verdict==='BLOCK'?'negative':'caution'}>{focusedResult.verdict==='PASS'?'本轮符合规则':focusedResult.verdict==='BLOCK'?'本轮不符合规则':'本轮证据不足'}</Badge><p>{focusedResult.summary}</p></div>}
        {running && active.progress && <div className="jj-home-task-progress"><span>已完成 {active.progress.completed_cases} / {active.progress.planned_cases} 项</span><Progress label="检查进度" value={active.progress.completed_cases} max={active.progress.planned_cases || 1}/></div>}
        <footer><span className="jj-small jj-muted">{running?'离开页面后，当前检查仍会继续。':stopped?'已保存的资料与报告可以继续查阅。':material.data?.actions.length?'材料齐备 '+material.data.actions.filter(item=>item.preparation_complete).length+' / '+material.data.actions.length+' 项操作':'沿用已确认的权限要求'}</span><ActionLink kind="primary" href={destinationHref(stopped ? '/environment' : destination)}>{running ? '查看进度' : stopped ? '打开示例环境' : task?.action_label ?? '查看权限规则'}</ActionLink></footer>
      </section>
      <p className="jj-home-summary" aria-label="业务概况">{count===undefined?'正在读取权限要求':`当前有 ${count} 条生效规则，覆盖 ${workspace?.actions.length??0} 项业务操作。`}{material.data&&`其中 ${material.data.actions.filter(item=>item.preparation_complete).length} 项操作的材料已齐备。`}{Boolean(issues?.length)&&`尚有 ${issues!.length} 项问题待处理。`}</p>
      <div className="jj-home-main">
      <section className="jj-home-check-history" aria-labelledby="home-recent-checks"><header><h2 id="home-recent-checks" className="jj-title-group">{focusedResult?'更早的检查':'最近检查'}</h2><ActionLink href={destinationHref('/reports')}>全部检查记录</ActionLink></header>
        {recent?.length?<p className="jj-home-section-guide">点击记录阅读结果与依据。比较两轮检查时，到全部记录中选择。</p>:null}
        {history.error?<ErrorNote error={history.error}/>:history.loading?<Loading/>:recent?.length?<div className="jj-home-check-list">{recent.map(item=><a className="jj-home-check-row" key={item.status.run.run_id} href={destinationHref('/reports?run_id='+item.status.run.run_id)}><time>{new Date(item.status.run.created_at_us/1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false})}</time><ObjectIdentity name={<strong>{item.action_labels.join('、')||'权限检查'}</strong>} status={<Status className="jj-home-check-outcome" tone={item.status.run.verdict==='PASS'?'positive':item.status.run.verdict==='BLOCK'?'negative':'caution'}>{item.status.run.verdict==='PASS'?'符合规则':item.status.run.verdict==='BLOCK'?'不符合规则':'证据不足'}</Status>}/></a>)}</div>:<p className="jj-small jj-muted">{focusedResult?'后续检查会持续保留各轮范围和依据。':'尚无检查记录。完成准备后，每轮结果都会保留在这里。'}</p>}

      </section>
      <Continuations projectId={projectId} issues={issues} excludeDestination={task?taskDestination(task):undefined}/></div>
      <details className="jj-home-context"><summary>应用连接与共用资料{environmentAddress&&<span>{environmentAddress}</span>}</summary><div><section><h2 className="jj-title-group">这次检查的应用</h2><p>检查使用已确认的地址。更换地址后，需要重新核对账号和材料。</p><dl className="jj-facts"><div><dt>连接情况</dt><dd>{environment?.endpoint_reachable?'最近核验可达':environment?.endpoint_reachable===false?'未连通':'待核验'}</dd></div><div><dt>源码</dt><dd>{environment?.source_available?'已关联本地目录':'尚未关联'}</dd></div></dl><ActionLink href={destinationHref('/application?view=environment')}>核对应用连接</ActionLink></section><section><h2 className="jj-title-group">共用资料</h2><nav aria-label="应用资料快捷入口"><ActionLink href={destinationHref('/application?view=sources')}>接口资料{sources&&<small>{sources.request_count} 个请求</small>}</ActionLink><ActionLink href={destinationHref('/preparation?identities=1')}>检查账号</ActionLink><ActionLink href={destinationHref('/preparation?proof_sources=1')}>业务结果证明</ActionLink></nav></section></div></details>
      {assets.error&&<ErrorNote error={assets.error}/>}
    </div>{material.error&&<ErrorNote error={material.error}/>}</>;
}
