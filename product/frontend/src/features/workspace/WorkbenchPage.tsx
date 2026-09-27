// 工作台以业务为索引呈现全局事实；推荐动作来自服务端，不推导安全结论。
import { Button, Input } from 'antd'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { OfficialExperienceDto } from '../../api/experience'
import type { ProjectDto } from '../../api/projects'
import type { WorkspaceViewDto } from '../../api/workspace'
import type { SystemStatus } from '../../api/system'
import type { MCPAccessView } from '../../api/mcp'
import { ApiError } from '../../api/http'
import { preparationApi, type PreparationView } from '../../api/preparation'
import { currentChecksApi, type CheckHistoryItem } from '../../api/currentChecks'
import { taskDestination } from '../../app/taskDestination'
import { formatTimestamp } from '../../app/presentation'
import { useLiveRead } from '../../app/useLiveRead'
import { EditorialHeader, EditorialPage, TaskFocus } from '../../shared/ui/Editorial'
import './workbench.css'

const verdictLabel = { PASS: '本次范围内的权限要求已验证', BLOCK: '发现权限问题', INCONCLUSIVE: '证据不足，暂不能判断' }

export function WorkbenchPage({ selected, workspace, systemStatus, experience, onNavigate, samplePanel, mcpStatus, workspaceSyncFailed }: {
  selected: ProjectDto | null; workspace: WorkspaceViewDto | null; systemStatus: SystemStatus
  experience: OfficialExperienceDto | null; onNavigate: (path: string) => void; samplePanel?: ReactNode
  workspaceSyncFailed?: boolean; taskContent?: ReactNode; mcpStatus?: MCPAccessView | null
}) {
  const [materials, setMaterials] = useState<PreparationView | null>(null)
  const [recent, setRecent] = useState<CheckHistoryItem[]>([])
  const [query, setQuery] = useState('')
  const project = useRef(selected?.project_id)
  project.current = selected?.project_id
  const generation = useRef(0)
  useEffect(() => { generation.current += 1; setMaterials(null); setRecent([]); return () => { generation.current += 1 } }, [selected?.project_id])
  const sync = useLiveRead(selected?.project_id, async () => {
    const id = selected!.project_id, epoch = generation.current
    const [preparation, history] = await Promise.all([preparationApi.get(id), currentChecksApi.history(id)])
    if (project.current !== id || generation.current !== epoch) return
    if (preparation.project_id !== id || history.project_id !== id || history.items.some(item=>item.status.run.project_id !== id)) throw new ApiError('STATE_PRECONDITION','工作台信息所属应用不一致。')
    setMaterials(preparation); setRecent(history.items)
  }, 10000)
  if (!selected) return <EditorialPage label="建立权限基线">
    <EditorialHeader eyebrow="开始使用界鉴" title="建立第一份权限基线"><p className="editorial-muted">连接本地 Web 应用，确认权限要求，再用真实操作检验业务结果。</p></EditorialHeader>
    <TaskFocus title="接入自己的应用" responsibility="先确认应用地址，再整理业务动作和必须保护的真实结果。" action={{label:'接入自己的应用',onClick:()=>onNavigate('/application')}}/>
    <section aria-label="官方示例"><p className="editorial-eyebrow">也可以从准备好的示例了解流程</p>{samplePanel ?? <p>{experience?.unavailable_reason ?? '当前没有可用的官方示例环境。'}</p>}</section>
  </EditorialPage>
  const primary = workspace?.primary_task
  const running = workspace?.active_check
  const active = running && ['RUNNING','QUEUED'].includes(running.run.lifecycle)
  const changeTask = primary?.task_kind === 'REGISTER_SOURCE_CHANGE'
  // 当前工作区可能因源码变化不再提供可信结果；历史已发布事实仍可回看，不能误报为从未检查。
  const published = recent.find(item=>item.status.result_integrity === 'VALID' && item.status.run.verdict)
  const result = workspace?.latest_result ?? (published?.status.run.verdict ? {
    run_id: published.status.run.run_id, verdict: published.status.run.verdict,
    policy_epoch: published.status.run.policy_epoch, created_at_us: published.status.run.created_at_us,
    summary: verdictLabel[published.status.run.verdict],
  } : null)
  const latest = recent.find(item => item.status.run.run_id === result?.run_id)
  const resultFocus = !active && primary?.task_kind === 'VIEW_CURRENT_RESULT' && result && (primary.run_id ? primary.run_id === result.run_id : Boolean(workspace?.latest_result))
  const connected = mcpStatus?.connection_state === 'CONNECTED'
  const actions = workspace?.actions.filter(action => (action.display_name+' '+action.description).includes(query.trim())) ?? []
  const systemIssue = systemStatus.api !== 'available' || systemStatus.worker === 'stopped' || systemStatus.browser === 'unavailable'
  return <EditorialPage label="当前应用工作台">
    <header className="workbench-heading"><div><p className="editorial-eyebrow">工作台</p><h1>{workspace?.project.name || selected.name || '未命名应用'}</h1><p className="workbench-meta"><span>{experience?.active && experience.project_id === selected.project_id ? '官方示例' : '本地 Web 应用'}</span><span>{!workspace ? '正在核对连接' : workspace.connection.endpoint_status === 'CONFIRMED' ? '应用连接已确认' : workspace.connection.endpoint_status === 'UNAVAILABLE' ? '应用暂不可达' : '应用地址待确认'}</span><span>{workspace?.connection.source_analysis_status === 'COMPLETED' ? '源码分析已完成' : '源码分析待完成'}</span></p></div><Button onClick={()=>onNavigate('/environment')}>应用与环境</Button></header>
    {workspaceSyncFailed && <p role="status" className="workbench-sync">工作台暂未同步，正在重试。下方为上次读取的状态。</p>}
    <nav className="workbench-shortcuts" aria-label="自由进入相关工作"><button onClick={()=>onNavigate('/tests')}>检查与材料<span>{workspace?.actions.length ?? 0} 项业务动作</span></button><button onClick={()=>onNavigate('/history')}>检查历史<span>{result ? '已有检查结果' : '尚无正式结果'}</span></button><button onClick={()=>onNavigate('/changes')}>代码变化与复验<span>{workspace?.source_change ? '已有变化登记' : '尚无变化登记'}</span></button></nav>
    <section className="workbench-focus" aria-label="当前需要处理的任务" data-running={Boolean(active)}>
      <div className="workbench-focus-copy"><p className="editorial-eyebrow">{active ? '检查进行中' : resultFocus ? '最近检查已完成' : '建议先处理'}</p><h2>{active ? running.progress?.current_case?.action_label ?? '正在检查已确认的权限' : resultFocus ? verdictLabel[result.verdict] : primary?.title ?? (workspace ? '当前没有待处理任务' : '正在读取当前工作')}</h2><p>{active ? running.progress?.phase === 'FINALIZING' ? '正在核验并保存结果，正式结论形成后会自动更新。' : '界鉴正在执行并观察真实业务结果，你可以继续浏览其他内容。' : resultFocus ? latest?.action_labels.join('、') || result.summary : primary?.why_now ?? '从下方业务列表查看权限与准备情况。'}</p>
      {active ? <><p className="workbench-run-progress" role="status">{running.progress ? '已完成 '+running.progress.completed_cases+' / '+running.progress.planned_cases+' 项检查' : '等待执行进度'}</p><Button type="primary" onClick={()=>onNavigate('/tests?run_id='+encodeURIComponent(running.run.run_id))}>查看检查进度</Button></> : primary && !changeTask ? <Button type="primary" disabled={!primary.can_execute} onClick={()=>onNavigate(taskDestination(primary))}>{primary.action_label ?? primary.title}<span aria-hidden="true"> →</span></Button> : changeTask ? <><p>{connected ? 'Agent 已连接，代码修改通过 MCP 登记后会自动同步。' : '连接 Coding Agent，由它提交代码修改记录。'}</p><Button type="primary" onClick={()=>onNavigate('/tools')}>Agent 连接与授权</Button><Button type="text" onClick={()=>onNavigate('/changes')}>查看变化与手动接管</Button></> : null}
      {primary?.unavailable_reason && !primary.can_execute && primary.unavailable_reason !== primary.why_now && <p role="status">{primary.unavailable_reason}</p>}</div>
      {resultFocus ? <aside className="workbench-focus-context"><p className="editorial-eyebrow">本次结果范围</p><strong>权限版本 {result.policy_epoch}</strong><p>{formatTimestamp(result.created_at_us)}</p><p>对应本次冻结的权限与源码。后续修改需要新的检查。</p><Button type="link" onClick={()=>onNavigate('/history')}>查看全部记录 →</Button></aside> : <aside className="workbench-focus-context"><p className="editorial-eyebrow">本次工作</p>{primary?.business_action_id && <strong>{workspace?.actions.find(item=>item.action_id===primary.business_action_id)?.display_name}</strong>}<dl><div><dt>{active ? '进度说明' : '完成条件'}</dt><dd>{active ? '执行进度不代表安全结论；结果核验完成后才能查看证明。' : primary?.completion_criteria || primary?.user_responsibility || '查看已有业务权限与检查事实。'}</dd></div>{!active && primary?.system_will_do && primary.system_will_do !== primary.why_now && <div><dt>完成后</dt><dd>{primary.system_will_do}</dd></div>}</dl></aside>}
    </section>
    <section className="workbench-business" aria-label="业务检查概况"><div className="workbench-section-heading"><div><h2>业务检查概况</h2><p>从业务出发，查看规则与材料的准备情况。</p></div><Input allowClear aria-label="搜索业务进展" placeholder="搜索业务动作" value={query} onChange={e=>setQuery(e.target.value)}/></div>
      <div className="workbench-business-columns" aria-hidden="true"><span>业务动作</span><span>权限规则</span><span>检查材料</span><span>下一步</span></div>
      {actions.map(action => {
        const preparation = materials?.project_id === selected.project_id ? materials.actions.find(item=>item.action_id===action.action_id && item.action_revision===action.action_revision) : undefined
        const focused = primary?.business_action_id === action.action_id
        return <div className="workbench-business-row" key={action.action_id}><div><strong>{action.display_name}</strong><p>{action.description}</p></div><span><small>权限规则</small>{action.permission_status.permission_semantics_confirmed ? '已确认' : '需要确认'}<em>{action.permission_status.active_permission_count} 条启用规则</em></span><span><small>检查材料</small>{sync.retrying ? '暂未同步' : !preparation ? '待核对' : preparation.preparation_complete ? '已齐备' : '尚有缺口'}</span><Button type="link" disabled={Boolean(focused && !primary.can_execute)} onClick={()=>onNavigate(focused ? taskDestination(primary!) : '/permissions?action_id='+encodeURIComponent(action.action_id))}>{focused ? '继续处理' : '查看权限'} →</Button></div>
      })}
      {!actions.length && <p className="workbench-empty">{query ? '没有匹配的业务动作。' : '还没有已确认的业务动作。从当前任务开始建立权限范围。'}</p>}
      <p className="workbench-sync" role="status">{sync.retrying ? sync.stopped ? '读取校验未通过，请重新打开页面核对。' : '暂时无法同步，正在重试。已有记录保留。' : sync.updatedAt ? '状态自动同步 · 材料齐备不等于检查通过' : '正在核对材料与记录'}</p>
    </section>
    {!resultFocus && <section className="workbench-latest" aria-label="最近可信结果"><div><p className="editorial-eyebrow">最近已发布结果</p><h2>{latest?.action_labels.join('、') || (result ? '最近一次权限检查' : '当前没有正式检查结果')}</h2><p className="workbench-verdict" data-verdict={result?.verdict}>{result ? verdictLabel[result.verdict] : '检查完成后，在这里查看结果与证据。'}</p>{result && <p className="editorial-muted">权限版本 {result.policy_epoch} · {formatTimestamp(result.created_at_us)}<br/>对应本次冻结的权限与源码；不代表后续修改已通过检查。</p>}</div><Button onClick={()=>onNavigate(result ? '/history?run_id='+encodeURIComponent(result.run_id) : '/history')}>{result ? '查看结果与证据' : '查看检查历史'} →</Button></section>}
    <footer className="workbench-support"><span>{connected ? '协作：'+(mcpStatus?.client_name || 'Coding Agent')+' 已连接' : '可连接 Coding Agent 协同修改与复验'}</span><Button type="text" onClick={()=>onNavigate('/tools')}>协作管理</Button>{systemIssue && <Button onClick={()=>onNavigate('/settings/system')}>查看运行环境问题</Button>}</footer>
  </EditorialPage>
}
