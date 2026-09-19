// 工作台围绕唯一服务端 PrimaryTask 组织当前任务，最近结果只作历史上下文。
import { Button } from 'antd'
import type { ReactNode } from 'react'
import type { OfficialExperienceDto } from '../../api/experience'
import type { ProjectDto } from '../../api/projects'
import type { WorkspaceViewDto } from '../../api/workspace'
import type { SystemStatus } from '../../api/system'
import type { MCPAccessView } from '../../api/mcp'
import { taskDestination } from '../../app/taskDestination'
import { formatTimestamp } from '../../app/presentation'
import { EditorialHeader, EditorialPage, TaskFocus } from '../../shared/ui/Editorial'

function endpointLabel(workspace: WorkspaceViewDto) {
  if (workspace.connection.endpoint_status === 'CONFIRMED') return '应用连接已确认'
  if (workspace.connection.endpoint_status === 'UNAVAILABLE') return '应用当前不可达'
  return '应用连接待确认'
}

function sourceLabel(workspace: WorkspaceViewDto) {
  if (workspace.connection.source_analysis_status === 'COMPLETED') return '当前源码分析已完成'
  if (workspace.connection.source_analysis_status === 'PENDING') return '源码分析等待运行'
  return '源码分析尚未授权'
}

// 辅助事实在操作区之后复用；历史结论不覆盖当前服务端任务。
export function WorkbenchContext({ workspace, onNavigate }: { workspace: WorkspaceViewDto | null; onNavigate: (path: string) => void }) {
  return <div className="workbench-context-grid">
    <section aria-label="最近可信结果"><h2>最近一次检查</h2>
      <p className="editorial-muted">{workspace?.latest_result ? formatTimestamp(workspace.latest_result.created_at_us) : '当前没有正式检查结果'}</p>
      <p>{workspace?.latest_result?.summary ?? '完成准备并开始检查后，结果会保存在这里。'}</p>
      <Button type="link" onClick={() => onNavigate(workspace?.latest_result ? `/history?run_id=${encodeURIComponent(workspace.latest_result.run_id)}` : '/history')}>{workspace?.latest_result ? '查看最近结果' : '查看检查历史'}<span aria-hidden="true"> →</span></Button>
      {workspace?.latest_result && <small>结论只覆盖当时的权限与源码。</small>}
    </section>
    <section aria-label="项目情况"><h2>项目情况</h2>{workspace && <><p>{endpointLabel(workspace)}</p><p className="editorial-muted">{sourceLabel(workspace)}</p></>}
      {workspace?.source_change && <p className="editorial-muted">最近登记：{workspace.source_change.submitted_by || '来源未提供'}</p>}
      <Button type="link" onClick={() => onNavigate('/changes')}>查看变化与修复<span aria-hidden="true"> →</span></Button>
    </section>
  </div>
}

export function WorkbenchPage({
  selected,
  workspace,
  systemStatus,
  experience,
  onNavigate,
  samplePanel,
  taskContent,
  mcpStatus,
}: {
  selected: ProjectDto | null
  workspace: WorkspaceViewDto | null
  systemStatus: SystemStatus
  experience: OfficialExperienceDto | null
  onNavigate: (path: string) => void
  samplePanel?: ReactNode
  taskContent?: ReactNode
  mcpStatus?: MCPAccessView | null
}) {
  const systemIssue = systemStatus.api === 'unknown' || systemStatus.worker === 'stopped' || systemStatus.browser === 'unavailable'
  if (!selected) return <EditorialPage label="建立权限基线">
    <EditorialHeader eyebrow="开始使用界鉴" title="建立第一份权限基线">
      <p className="editorial-muted">连接你的本地 Web 应用，用业务语言确认谁可以对谁的资源做什么。</p>
    </EditorialHeader>
    <TaskFocus title="接入自己的应用" responsibility="先确认应用地址，再整理业务动作和必须保护的真实结果。" action={{ label: '接入自己的应用', onClick: () => onNavigate('/application') }} />
    <section aria-label="官方示例"><p className="editorial-eyebrow">也可以从准备好的示例了解流程</p>
      {samplePanel ?? <p>{experience?.unavailable_reason ?? '当前没有可用的官方示例环境。'}</p>}
    </section>
  </EditorialPage>

  const primary = workspace?.primary_task ?? null
  const projectName = (workspace?.project.name ?? selected.name?.trim()) || '未命名应用'
  // 只转交服务端已给出的运行/变化上下文，不从本地材料状态选择下一任务。
  const taskPath = primary ? taskDestination(primary) : null
  const connected = mcpStatus?.connection_state === 'CONNECTED'
  const grant = mcpStatus?.project_grants.find(item => item.project_id === selected.project_id)?.level
  const agentCanPrepare = connected && (grant === 'PREPARE' || grant === 'EXECUTE')
  const changeTask = primary?.task_kind === 'REGISTER_SOURCE_CHANGE'
  // 任务主体在同一个工作入口装配；权限编辑、准备与检查仍使用唯一生产组件。
  if (taskContent) return <div className="current-work">
    {taskContent}
    <WorkbenchContext workspace={workspace} onNavigate={onNavigate} />
    <details className="work-context-details"><summary>项目与协作状态</summary>
      {workspace && <p>{endpointLabel(workspace)} · {sourceLabel(workspace)}</p>}
      <p>{connected ? `已连接 ${mcpStatus?.client_name || 'Coding Agent'}；连接本身不代表正在修改代码。` : 'Coding Agent 尚未连接。'}</p>
      {workspace?.source_change && <p>最近代码变化：{workspace.source_change.reason} · {workspace.source_change.submitted_by || '来源未提供'}</p>}
      <Button type="link" onClick={() => onNavigate('/tools')}>Agent 连接与授权</Button><Button type="link" onClick={() => onNavigate('/changes')}>查看变化与修复</Button>
    </details>
    {(!experience?.active || experience.project_id === selected.project_id) && <div className="work-sample-tools">{samplePanel}</div>}
  </div>
  return <EditorialPage label="当前应用工作台">
    <EditorialHeader eyebrow={`当前工作 / ${projectName}`} title={!workspace ? '正在读取当前工作' : changeTask ? '等待下一次代码变化' : '当前工作'}>
      {primary && <p className="editorial-muted">{primary.why_now}</p>}
    </EditorialHeader>
    {workspace && <TaskFocus title={changeTask ? '等待代码变化登记' : primary?.title ?? '当前没有需要你处理的事项'} responsibility={changeTask ? agentCanPrepare ? '已连接的 Agent 可以通过 MCP 提交修改。你不需要重复登记。' : 'Coding Agent 可以通过 MCP 提交修改；也可以手动接管。' : primary?.user_responsibility ?? '已确认的权限保持有效，新的事实到来后会更新当前任务。'} systemWillDo={changeTask ? '登记后重新核对实际源码，再检查原权限与复验条件。' : primary?.system_will_do}
      action={!changeTask && primary && taskPath ? { label: primary.title, disabled: !primary.can_execute, onClick: () => onNavigate(taskPath) } : undefined} />}
    {changeTask && <div className="work-agent-controls"><Button onClick={() => onNavigate('/tools')}>Agent 连接与授权</Button><details><summary>手动接管</summary><p>没有通过 Agent 登记本次修改时，可以在此提交变化说明。</p><Button disabled={!primary?.can_execute} onClick={() => onNavigate('/changes')}>登记本次变化</Button></details></div>}
    <WorkbenchContext workspace={workspace} onNavigate={onNavigate} />
    <nav className="editorial-links" aria-label="自由进入相关工作">
      <Button type="link" onClick={() => onNavigate('/permissions')}>查看与维护权限</Button>
      <Button type="link" onClick={() => onNavigate('/history')}>查看检查历史</Button>
      <Button type="link" onClick={() => onNavigate('/changes')}>查看变化与修复</Button>
    </nav>
    {systemIssue && <Button type="link" onClick={() => onNavigate('/settings/system')}>运行环境中有服务暂不可用，查看详情</Button>}
    {(!experience?.active || experience.project_id === selected.project_id) && samplePanel}
  </EditorialPage>
}
