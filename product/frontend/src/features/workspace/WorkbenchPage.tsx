// 工作台围绕唯一服务端 PrimaryTask 组织当前任务，最近结果只作历史上下文。
import { Button } from 'antd'
import type { ReactNode } from 'react'
import type { OfficialExperienceDto } from '../../api/experience'
import type { ProjectDto } from '../../api/projects'
import type { WorkspaceViewDto } from '../../api/workspace'
import type { SystemStatus } from '../../api/system'
import { taskDestination } from '../../app/taskDestination'
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

export function WorkbenchPage({
  selected,
  workspace,
  systemStatus,
  experience,
  onNavigate,
  samplePanel,
}: {
  selected: ProjectDto | null
  workspace: WorkspaceViewDto | null
  systemStatus: SystemStatus
  experience: OfficialExperienceDto | null
  onNavigate: (path: string) => void
  samplePanel?: ReactNode
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
  return <EditorialPage label="当前应用工作台">
    <EditorialHeader eyebrow={`当前应用 · ${projectName}`} title={!workspace ? '正在读取当前工作区。' : primary?.why_now ?? '当前没有需要立即处理的权限事项。'}>
      {workspace && <div className="workbench-project-status"><span>{endpointLabel(workspace)}</span><span>{sourceLabel(workspace)}</span></div>}
    </EditorialHeader>
    {workspace && <TaskFocus title={primary?.title ?? '等待新的业务或源码变化'} responsibility={primary?.user_responsibility ?? '当前已确认的权限保持有效；新的事实到来后，界鉴会给出下一项任务。'} systemWillDo={primary?.system_will_do}
      action={primary && taskPath ? { label: primary.title, disabled: !primary.can_execute, onClick: () => onNavigate(taskPath) } : undefined} />}
    <aside className="editorial-context" aria-label="最近可信结果">
      <p className="editorial-eyebrow">最近可信结果 · 供你回看</p>
      <p>{workspace?.latest_result?.summary ?? '当前没有正式检查结果'}</p>
      <p className="editorial-muted">{workspace?.latest_result ? '这份结论只覆盖当时冻结的权限与源码；当前任务仍以本页上方判断为准。' : '完成当前准备后，显式开始检查才会形成结果。'}</p>
      {workspace?.latest_result && <Button type="link" onClick={() => onNavigate(`/tests?run_id=${encodeURIComponent(workspace.latest_result!.run_id)}`)}>查看最近结果</Button>}
    </aside>
    <nav className="editorial-links" aria-label="自由进入相关工作">
      <Button type="link" onClick={() => onNavigate('/permissions')}>查看与维护权限</Button>
      <Button type="link" onClick={() => onNavigate('/tests')}>查看验证与记录</Button>
      <Button type="link" onClick={() => onNavigate('/changes')}>查看变化与修复</Button>
    </nav>
    {systemIssue && <Button type="link" onClick={() => onNavigate('/settings/system')}>运行环境中有服务暂不可用，查看详情</Button>}
    {(!experience?.active || experience.project_id === selected.project_id) && samplePanel}
  </EditorialPage>
}
