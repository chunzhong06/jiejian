// 动作级工作台：直接渲染服务端 WorkspaceView 与唯一 PrimaryTask，不重算 currentness。

import { Alert, Button, Divider, Typography } from 'antd'
import type { OfficialExperienceDto } from '../../api/experience'
import type { ProjectDto } from '../../api/projects'
import type { WorkspaceViewDto } from '../../api/workspace'
import type { SystemStatus } from '../../api/system'
import { PageTaskHeader } from '../../components/PageTaskHeader'

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
}: {
  selected: ProjectDto | null
  workspace: WorkspaceViewDto | null
  systemStatus: SystemStatus
  experience: OfficialExperienceDto | null
  onNavigate: (path: string) => void
}) {
  const systemIssue = systemStatus.api === 'unknown'
    || systemStatus.worker === 'stopped'
    || systemStatus.browser === 'unavailable'

  if (!selected) return <div className="workbench-page">
    <PageTaskHeader title="工作台" description="接入应用后，界鉴会持续维护业务边界与当前代码实现映射。" status="等待接入应用" />
    <section className="workbench-primary-panel workbench-empty" aria-labelledby="workbench-empty-title">
      <Typography.Title id="workbench-empty-title" level={3}>建立第一份权限安全基线</Typography.Title>
      <Typography.Paragraph type="secondary">先连接本地 Web 应用，再用业务语言确认主体、动作、真实结果与允许/拒绝规则。</Typography.Paragraph>
      <Button type="primary" onClick={() => onNavigate('/application')}>接入自己的应用</Button>
    </section>
    <Divider plain>官方示例</Divider>
    <section className="workbench-sample-entry" aria-labelledby="workbench-sample-entry-title">
      <Typography.Text className="workbench-eyebrow">当前能力</Typography.Text>
      <Typography.Title id="workbench-sample-entry-title" level={3}>{experience?.display_name ?? '协作空间'}</Typography.Title>
      <Typography.Paragraph type="secondary">{experience?.available === false ? experience.unavailable_reason ?? '新的检查主链尚未重新接入。' : '当前版本不从工作台启动旧检查或演示状态机。'}</Typography.Paragraph>
    </section>
  </div>

  const primary = workspace?.primary_task ?? null
  const reviewCount = workspace?.actions.filter((action) =>
    !action.permission_status.permission_semantics_confirmed
    || action.actor_implementation_issue_count > 0
    || action.implementation.binding_exists && action.implementation.status !== 'CURRENT',
  ).length ?? 0
  return <div className="workbench-page">
    <section className="workbench-primary-panel" aria-labelledby="workbench-current-app">
      <div className="workbench-project-heading">
        <div>
          <Typography.Text className="workbench-eyebrow">当前应用</Typography.Text>
          <Typography.Title id="workbench-current-app" level={2}>{(workspace?.project.name ?? selected.name?.trim()) || '未命名应用'}</Typography.Title>
          {workspace && <div className="workbench-project-status"><span>{endpointLabel(workspace)}</span><span>{sourceLabel(workspace)}</span></div>}
        </div>
      </div>
      <div className="workbench-focus-grid">
        <article className="workbench-primary-focus" aria-label="当前判断与主任务">
          <Typography.Text className="workbench-eyebrow">当前判断</Typography.Text>
          <Typography.Title level={3}>{!workspace
            ? '正在读取当前动作工作区。'
            : primary?.why_now ?? '当前没有需要立即处理的业务边界事项。'}</Typography.Title>
          <div className="workbench-primary-action">
            <div className="workbench-primary-action-copy">
              <Typography.Text className="workbench-eyebrow">当前主任务</Typography.Text>
              <Typography.Text strong>{primary?.title ?? '当前业务边界已同步'}</Typography.Text>
              <Typography.Text type="secondary">{primary?.user_responsibility ?? '新的业务或源码事实到来后，界鉴会继续从这里给出下一项真实任务。'}</Typography.Text>
              {primary && <Typography.Text type="secondary">系统接下来会：{primary.system_will_do}</Typography.Text>}
            </div>
            {primary && <Button type="primary" disabled={!primary.can_execute} onClick={() => onNavigate(primary.route)}>前往处理</Button>}
          </div>
        </article>
        <aside className="workbench-trusted-result" aria-label="最近可信结果">
          <Typography.Text className="workbench-eyebrow">最近可信结果</Typography.Text>
          <Typography.Title level={3}>新的检查结果尚未重新接入</Typography.Title>
          <Typography.Paragraph type="secondary">可在权限页维护业务边界，并按工作台提示处理当前待办。</Typography.Paragraph>
        </aside>
      </div>
      {systemIssue && <Button type="link" className="workbench-system-link" onClick={() => onNavigate('/settings/system')}>运行环境中有服务暂不可用，查看详情</Button>}
    </section>

    <section className="workbench-domain-panel" aria-label="当前专项摘要">
      <div className="workbench-domain-grid">
        <article><Typography.Text className="workbench-secondary-label">业务边界</Typography.Text><Typography.Title level={3}>{workspace?.actions.length ?? 0} 项当前业务动作</Typography.Title><Typography.Paragraph type="secondary">{reviewCount ? `${reviewCount} 项需要确认当前权限或代码实现。` : '当前动作、权限与实现状态由服务端实时投影。'}</Typography.Paragraph><Button type="link" onClick={() => onNavigate('/permissions')}>进入业务边界</Button></article>
        <article><Typography.Text className="workbench-secondary-label">变化与修复</Typography.Text><Typography.Title level={3}>当前暂不可用</Typography.Title><Typography.Paragraph type="secondary">当前尚不支持代码变化分析、修复与复验。</Typography.Paragraph><Button type="link" onClick={() => onNavigate('/changes')}>查看当前说明</Button></article>
        <article><Typography.Text className="workbench-secondary-label">检查与结果</Typography.Text><Typography.Title level={3}>当前不可检查</Typography.Title><Typography.Paragraph type="secondary">当前尚不支持准备测试材料或运行权限检查。</Typography.Paragraph><Button type="link" onClick={() => onNavigate('/tests')}>查看当前说明</Button></article>
      </div>
    </section>
    <section className="workbench-secondary-panel" aria-label="当前能力边界">
      <Alert type="info" showIcon message="业务边界可以持续维护" description="代码重新分析不会自动改写业务 revision 或权限；需要时由维护提案明确重绑或沿用权限。" />
    </section>
  </div>
}
