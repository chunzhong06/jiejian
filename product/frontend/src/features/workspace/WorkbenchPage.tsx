// 概览集中显示下一步与权限、材料、最近结果；推荐动作来自服务端。
import { Button } from 'antd'
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
import { useLiveRead } from '../../app/useLiveRead'
import { EditorialHeader, EditorialPage, TaskFocus } from '../../shared/ui/Editorial'
import './workbench.css'
import '../changes/lightweight.css'

const verdictLabel = { PASS: '本次范围内的权限要求已验证', BLOCK: '发现权限问题', INCONCLUSIVE: '证据不足，暂不能判断' }

export function WorkbenchPage({ selected, workspace, systemStatus, experience, onNavigate, samplePanel, mcpStatus, workspaceSyncFailed }: {
  selected: ProjectDto | null; workspace: WorkspaceViewDto | null; systemStatus: SystemStatus
  experience: OfficialExperienceDto | null; onNavigate: (path: string) => void; samplePanel?: ReactNode
  workspaceSyncFailed?: boolean; taskContent?: ReactNode; mcpStatus?: MCPAccessView | null
}) {
  const [materials, setMaterials] = useState<PreparationView | null>(null)
  const [recent, setRecent] = useState<CheckHistoryItem[]>([])
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
  const official = selected.official_sample || [experience?.project_id, experience?.history_project_id].includes(selected.project_id)
  const sampleRunning = experience?.active && experience.project_id === selected.project_id && experience.lifecycle === 'RUNNING'
  // 历史来源与实时实例分开；手动打开旧示例不能复用其过去的连接确认和待办。
  if (official && !sampleRunning) return <EditorialPage label="示例历史">
    <EditorialHeader eyebrow="官方示例 · 历史项目" title={selected.name || '协作空间'}><p className="editorial-muted">{experience?.project_id === selected.project_id && experience.recovery_state === 'EXITED' ? '该示例已停止。' : '该项目没有已确认正在运行的示例实例。'}已有检查结果与证据保留，过去的地址确认不代表现在仍可连接。</p></EditorialHeader>
    <TaskFocus title="查看示例历史" responsibility="回看本项目的检查结果与证据；开始新的示例会创建独立项目。" action={{ label: '查看检查历史', onClick: () => onNavigate('/history') }}/>
    <section aria-label="官方示例"><h2>开始新的示例</h2>{samplePanel ?? <Button onClick={() => onNavigate('/environment')}>管理示例环境</Button>}</section>
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
  const resultFocus = !active && primary?.task_kind === 'VIEW_CURRENT_RESULT' && result && (primary.run_id ? primary.run_id === result.run_id : Boolean(workspace?.latest_result))
  const connected = mcpStatus?.connection_state === 'CONNECTED'
  const systemIssue = systemStatus.api !== 'available' || systemStatus.worker === 'stopped' || systemStatus.browser === 'unavailable'
  const permissionCount = workspace?.actions.reduce((sum,action)=>sum+action.permission_status.active_permission_count,0)
  return <EditorialPage label="当前应用概览">
    <div className="light-page-heading"><EditorialHeader eyebrow={selected.name || '当前应用'} title="概览"><p className="editorial-muted">需要你关注的权限与检查，集中在这里。</p></EditorialHeader><Button onClick={()=>onNavigate('/environment')}>应用与环境</Button></div>
    {workspaceSyncFailed&&<p role="status">概览暂未同步，正在重试。下方保留上次读取的状态。</p>}
    <section className="light-focus" aria-label="当前需要处理的任务"><div><p className="editorial-eyebrow">{active?'检查进行中':resultFocus?'最近检查已完成':'当前需要关注'}</p><h2>{active?running.progress?.current_case?.action_label??'正在检查已确认的权限':resultFocus?verdictLabel[result.verdict]:primary?.title??(workspace?'当前没有待处理事项':'正在读取当前状态')}</h2><p>{active?'界鉴正在执行并观察业务结果，你可以继续在原客户端工作。':resultFocus?result.summary:primary?.why_now??'查看已确认的要求、准备条件与最近记录。'}</p>{primary?.unavailable_reason&&!primary.can_execute&&<p role="status">{primary.unavailable_reason}</p>}{active&&<p role="status">{running.progress?'已完成 '+running.progress.completed_cases+' / '+running.progress.planned_cases+' 项检查':'等待执行进度'}</p>}</div><div>{active?<Button type="primary" onClick={()=>onNavigate('/tests?run_id='+encodeURIComponent(running.run.run_id))}>查看检查进度</Button>:changeTask?<Button type="primary" onClick={()=>onNavigate('/changes?view=register')}>登记本地修改</Button>:primary?<Button type="primary" disabled={!primary.can_execute} onClick={()=>onNavigate(taskDestination(primary))}>{primary.task_kind==='PREPARE_AGENT_REPAIR'?'查看修复依据':primary.action_label??primary.title}</Button>:null}</div><footer><span>{primary?.system_will_do??'规则与材料继续复用，失效时再补齐。'}</span><Button type="link" onClick={()=>onNavigate('/changes')}>修改与验证</Button></footer></section>
    <div className="light-section-heading"><div><h2>当前应用</h2><p>用少量事实，判断下一步</p></div></div>
    <dl className="light-overview-records"><div><dt>权限要求</dt><dd>{workspace?`${permissionCount} 条启用规则 · ${workspace.actions.length} 项业务动作`:'正在读取权限范围'}</dd><Button type="link" onClick={()=>onNavigate('/permissions')}>查看要求</Button></div><div><dt>检查材料</dt><dd>{sync.retrying?'暂时无法核对材料':materials?.project_id===selected.project_id?materials.preparation_complete?'已齐备，执行前仍需核对':'尚有缺口，继续准备':'正在读取材料'}</dd><Button type="link" onClick={()=>onNavigate('/tests?materials=1')}>管理材料</Button></div><div><dt>最近结果</dt><dd>{result?verdictLabel[result.verdict]:'尚无正式检查结果'}{result&&<small>只对应当时的权限与源码</small>}</dd><Button type="link" onClick={()=>onNavigate(result?'/history?run_id='+encodeURIComponent(result.run_id):'/history')}>{result?'查看对应结果':'查看检查记录'}</Button></div></dl>
    <p className="light-meta">上次结果属于当时的源码。新的修改尚未检查时，历史结论不代表当前安全。</p>
    <footer className="light-footer">{workspace?.connection.endpoint_status==='CONFIRMED'&&<span>应用地址已确认</span>}<span>{connected?'客户端连接已验证；这不表示 Agent 正在编码。':'可连接原来的开发客户端，读取权限要求和检查事实。'}</span><Button type="link" onClick={()=>onNavigate('/tools')}>Agent 连接与授权</Button>{systemIssue&&<Button type="link" onClick={()=>onNavigate('/settings/system')}>查看运行环境问题</Button>}</footer>
  </EditorialPage>
}
