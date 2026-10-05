// 概览集中显示下一步与权限、材料、最近结果；推荐动作来自服务端。
import { Button } from 'antd'
import { ArrowRightOutlined, RightOutlined, SafetyCertificateOutlined, FileSearchOutlined, FolderOpenOutlined } from '@ant-design/icons'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { OfficialExperienceDto } from '../../api/applications/experience'
import type { ProjectDto } from '../../api/applications/projects'
import type { WorkspaceViewDto } from '../../api/workspace'
import type { SystemStatus } from '../../api/system/system'
import { ApiError } from '../../api/http'
import { preparationApi, type PreparationView } from '../../api/preparation/preparation'
import { currentChecksApi, type CheckHistoryItem } from '../../api/checks/currentChecks'
import { taskDestination } from '../../shared/navigation/taskDestination'
import { useLiveRead } from '../../shared/runtime/useLiveRead'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import './workbench.css'
import '../../shared/styles/collections.css'

const verdictLabel = { PASS: '本次范围内的权限要求已验证', BLOCK: '发现权限问题', INCONCLUSIVE: '证据不足，暂不能判断' }

export function WorkbenchPage({ selected, workspace, systemStatus, experience, onNavigate, samplePanel, workspaceSyncFailed }: {
  selected: ProjectDto | null; workspace: WorkspaceViewDto | null; systemStatus: SystemStatus
  experience: OfficialExperienceDto | null; onNavigate: (path: string) => void; samplePanel?: ReactNode
  workspaceSyncFailed?: boolean
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
  if (!selected) return <EditorialPage label="建立权限基线" width="welcome">
    <section className="welcome-hero"><p className="editorial-eyebrow">界鉴 · 轻量权限验证</p><h1>让权限要求，<br />有真实业务事实支撑。</h1><p>开发仍在你已有的工具中完成。界鉴帮你确认权限、核对结果，并沿原题复验。</p></section>
    <div className="welcome-paths"><section className="welcome-path"><div><h2>接入自己的应用</h2><p>选择本地项目，再确认地址与源码读取范围。</p></div><Button type="primary" onClick={()=>onNavigate('/application')}>选择应用目录 <ArrowRightOutlined aria-hidden="true" /></Button></section>
    <section className="welcome-path"><div><h2>先了解完整过程</h2><p>使用独立的官方示例，体验权限确认、检查与复验。</p></div><Button type="link" onClick={()=>onNavigate('/environment')}>查看官方示例 <ArrowRightOutlined aria-hidden="true" /></Button></section></div>
  </EditorialPage>
  const official = selected.official_sample || [experience?.project_id, experience?.history_project_id].includes(selected.project_id)
  const sampleRunning = experience?.active && experience.project_id === selected.project_id && experience.lifecycle === 'RUNNING'
  // 历史来源与实时实例分开；手动打开旧示例不能复用其过去的连接确认和待办。
  if (official && !sampleRunning) return <EditorialPage label="示例重新开始">
    <EditorialHeader eyebrow="官方示例" title={selected.name || '协作空间'}><p className="editorial-muted">{experience?.project_id === selected.project_id && experience.recovery_state === 'EXITED' ? '该示例已停止。' : '该项目没有已确认正在运行的示例实例。'}已有检查结果与证据保留，过去的地址确认不代表现在仍可连接。</p></EditorialHeader>

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
  const systemIssue = systemStatus.api !== 'available' || systemStatus.worker === 'stopped' || systemStatus.browser === 'unavailable'
  const permissionCount = workspace?.actions.reduce((sum,action)=>sum+action.permission_status.active_permission_count,0)
  return <EditorialPage label="当前应用概览">
    <EditorialHeader eyebrow={selected.name || '当前应用'} title="总览"/>
    {workspaceSyncFailed && <p role="status">总览暂未同步，正在重试。下方保留上次读取的状态。</p>}
    <section className="overview-task" aria-label="当前需要处理的任务">
      <div className="overview-task-copy"><p className="editorial-eyebrow">{active ? '检查进行中' : resultFocus ? '最近检查已完成' : '当前下一步'}</p>
        <h2>{active ? running.progress?.current_case?.action_label ?? '正在检查已确认的权限' : resultFocus ? verdictLabel[result.verdict] : primary?.title ?? (workspace ? '当前没有待处理事项' : '正在读取当前状态')}</h2>
        <p>{active ? '界鉴正在执行并观察业务结果，你可以继续在开发客户端工作。' : resultFocus ? `对应权限版本 ${result.policy_epoch}` : primary?.why_now ?? '查看已确认的要求、准备条件与最近记录。'}</p>
        {active && <p>{running.progress ? `已完成 ${running.progress.completed_cases} / ${running.progress.planned_cases} 项检查` : '等待执行进度'}</p>}
      </div>
      <div className="overview-task-actions">
        {primary?.unavailable_reason && !primary.can_execute && <p role="status">{primary.unavailable_reason}</p>}
        <div className="overview-action">{active ? <Button type="primary" onClick={()=>onNavigate('/tests?run_id='+encodeURIComponent(running.run.run_id))}>查看检查进度 <ArrowRightOutlined aria-hidden="true" /></Button> : changeTask ? <Button type="primary" disabled={!primary.can_execute} onClick={()=>onNavigate('/changes?view=register')}>登记本地修改 <ArrowRightOutlined aria-hidden="true" /></Button> : primary ? <Button type="primary" disabled={!primary.can_execute} onClick={()=>onNavigate(taskDestination(primary))}>{primary.task_kind==='PREPARE_AGENT_REPAIR' ? '查看修复依据' : primary.action_label ?? primary.title}<ArrowRightOutlined aria-hidden="true" /></Button> : null}</div>
      </div>
    </section>
    <section className="overview-records" aria-label="当前应用已有事实">
      <button className="overview-entry" onClick={()=>onNavigate('/permissions')}><SafetyCertificateOutlined aria-hidden="true" /><span><strong>权限约定</strong><small>{workspace ? `${permissionCount} 条启用规则 · ${workspace.actions.length} 项业务动作` : '正在读取权限范围'}</small></span><RightOutlined aria-hidden="true" /></button>
      <button className="overview-entry" onClick={()=>onNavigate('/tests?materials=1')}><FolderOpenOutlined aria-hidden="true" /><span><strong>检查材料</strong><small>{sync.retrying ? '暂时无法核对材料' : materials?.project_id===selected.project_id ? materials.preparation_complete ? '已齐备，执行前仍需核对' : '尚有缺口，继续准备' : '正在读取材料'}</small></span><RightOutlined aria-hidden="true" /></button>
      <button className="overview-entry" onClick={()=>onNavigate(result ? '/history?run_id='+encodeURIComponent(result.run_id) : '/history')}><FileSearchOutlined aria-hidden="true" /><span><strong>最近检查</strong><small>{result ? verdictLabel[result.verdict] : '尚无正式检查结果'}</small></span><RightOutlined aria-hidden="true" /></button>
    </section>
    {systemIssue && <p className="overview-system-issue"><Button type="link" onClick={()=>onNavigate('/settings/system')}>查看系统运行问题</Button></p>}
  </EditorialPage>
}
