// 工作台突出后端指定的主待办，并保留可自由进入的变化、权限和测试模块。

import { Alert, Button, Divider, Modal, Space, Tag, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { ApiError } from '../../api/http'
import type { OfficialExperienceDto, OfficialScenarioVersion } from '../../api/experience'
import { projectsApi, type DeliveryCheckDto, type ProductStatusDto, type ProjectDto, type ProjectReadinessDto } from '../../api/projects'
import type { RunDto } from '../../api/runs'
import type { SystemStatus } from '../../api/system'
import { formatTimestamp, verdictLabel } from '../../app/presentation'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { OfficialSampleSetupBar } from '../../components/OfficialSampleSetupBar'

function endpointLabel(readiness: ProjectReadinessDto) {
  if (readiness.endpoint_status === 'CONFIRMED') return '应用连接已确认'
  if (readiness.endpoint_status === 'UNAVAILABLE') return '应用当前不可达'
  return '应用连接待确认'
}

export function WorkbenchPage({
  selected,
  readiness,
  status,
  runs,
  systemStatus,
  experience,
  experienceBusy,
  onStartExperience,
  onPrepareExperience,
  onRunExperience,
  onSwitchExperience,
  onStopExperience,
  onEnterPresentation,
  onNavigate,
  onError,
}: {
  selected: ProjectDto | null
  readiness: ProjectReadinessDto | null
  status: ProductStatusDto | null
  runs: RunDto[]
  systemStatus: SystemStatus
  experience: OfficialExperienceDto | null
  experienceBusy: boolean
  onStartExperience: () => Promise<boolean>
  onPrepareExperience: () => void
  onRunExperience: () => void
  onSwitchExperience: (version: OfficialScenarioVersion, sourceRunId?: string) => void
  onStopExperience?: () => Promise<void>
  onEnterPresentation?: () => void
  onNavigate: (path: string) => void
  onError: (error: ApiError) => void
}) {
  const [startConfirmOpen, setStartConfirmOpen] = useState(false)
  const [deliveryBusy, setDeliveryBusy] = useState(false)
  const [delivery, setDelivery] = useState<DeliveryCheckDto | null>(null)
  useEffect(() => { setDelivery(null) }, [selected?.project_id])
  const latestResult = status?.latest_result ?? null
  const trustedRun = latestResult ? runs.find((item) => item.run_id === latestResult.run_id) : undefined
  const latestChange = status?.latest_change ?? null
  const systemIssue = systemStatus.api === 'unknown' || systemStatus.worker === 'stopped' || systemStatus.browser === 'unavailable'
  const sampleAvailable = experience?.available === true
  const activeSampleSelected = experience?.active === true && experience.project_id === selected?.project_id
  const trustedRunAt = trustedRun?.created_at_us ?? trustedRun?.created_at
  const presentationReady = Boolean(
    activeSampleSelected
    && trustedRun?.result_integrity === 'VERIFIED'
    && typeof experience?.scenario_changed_at_us === 'number'
    && typeof trustedRunAt === 'number'
    && trustedRunAt >= experience.scenario_changed_at_us,
  )
  const startSampleAction = <Button disabled={!sampleAvailable || experienceBusy} onClick={() => setStartConfirmOpen(true)}>启动官方示例</Button>
  const consent = <Modal
    open={startConfirmOpen}
    title="进入 Agent 写错的问题版？"
    okText="启动问题版"
    cancelText="取消"
    confirmLoading={experienceBusy}
    onCancel={() => setStartConfirmOpen(false)}
    onOk={async () => { if (await onStartExperience()) setStartConfirmOpen(false) }}
  >
    <Typography.Paragraph>协作空间原本要求：Bob 可以查看日常资料，但不能导出包含申报书、预算和评审材料的完整项目交付包。</Typography.Paragraph>
    <Typography.Paragraph>模拟的 Vibe Coding Agent 为缩短等待，把后台任务创建提前到了权限判断之前。启动时界鉴会保存安全源码基线并进入问题实现；一键应用公开合同后，再把真实代码差异登记为 MCP · Codex 提交的变化。</Typography.Paragraph>
    <Typography.Paragraph>启动后可一键应用公开样例配置，不需要逐项填写角色、流程和权限表。</Typography.Paragraph>
    <Typography.Paragraph strong>启动示例不会开始真实检查，也不会预先生成结论。</Typography.Paragraph>
  </Modal>
  const checkDelivery = async () => {
    if (!selected?.project_id) return
    setDeliveryBusy(true)
    try {
      setDelivery(await projectsApi.deliveryCheck(selected.project_id))
    } catch (error) {
      setDelivery(null)
      onError(error as ApiError)
    } finally {
      setDeliveryBusy(false)
    }
  }

  if (!selected) return <div className="workbench-page">
    <PageTaskHeader title="工作台" description="接入应用后，界鉴会持续跟踪权限、测试条件、代码变化与可信结果。" status="等待接入应用" />
    <section className="workbench-primary-panel workbench-empty" aria-labelledby="workbench-empty-title">
      <Typography.Title id="workbench-empty-title" level={3}>建立第一份权限安全基线</Typography.Title>
      <Typography.Paragraph type="secondary">先连接本地 Web 应用。应用继续开发时，界鉴会保留已确认规则，并提示新增或失效的部分。</Typography.Paragraph>
      <Button type="primary" onClick={() => onNavigate('/application')}>接入自己的应用</Button>
    </section>
    <Divider plain>或者先体验界鉴</Divider>
    <section className="workbench-sample-entry" aria-labelledby="workbench-sample-entry-title">
      <Typography.Text className="workbench-eyebrow">官方示例</Typography.Text>
      <Typography.Title id="workbench-sample-entry-title" level={3}>协作空间</Typography.Title>
      <Typography.Paragraph>Vibe Coding Agent 改动了导出流程，却可能在局部优化中遗忘既有权限边界。Bob 可以查看日常资料，但不能导出完整项目交付包；界鉴会核对页面响应、后台任务与 ZIP 结果是否一致。</Typography.Paragraph>
      <Typography.Paragraph type="secondary">体验包含问题版、证据受限版和修复版；每个结论都需要重新运行真实检查。</Typography.Paragraph>
      {!sampleAvailable && <Typography.Paragraph type="secondary">当前版本未包含官方示例</Typography.Paragraph>}
      {startSampleAction}
    </section>
    {consent}
  </div>

  const attentionItems = status?.attention_items ?? []
  const primaryItem = status?.primary_attention_key
    ? attentionItems.find((item) => item.key === status.primary_attention_key) ?? null
    : null
  const primaryReferenceMissing = Boolean(status && attentionItems.length > 0 && !primaryItem)
  const remainingAttentionCount = primaryItem
    ? attentionItems.filter((item) => item.key !== primaryItem.key).length
    : 0
  return <div className="workbench-page">
    <PageTaskHeader title="工作台" description="先看当前判断，再进入变化、权限或测试模块处理具体问题；Agent 每次修改后都从现有基线继续。" status={!status ? '正在读取当前状态' : primaryReferenceMissing ? '当前主任务不可用' : primaryItem ? '已定位当前主任务' : '当前没有待处理事项'} />

    <section className="workbench-primary-panel" aria-labelledby="workbench-current-app">
      <div className="workbench-project-heading">
        <div><Typography.Text className="workbench-eyebrow">当前应用</Typography.Text><Typography.Title id="workbench-current-app" level={2}>{selected.name?.trim() || '未命名应用'}</Typography.Title>{readiness && <Space wrap size={12}><Tag>{endpointLabel(readiness)}</Tag><Tag color={readiness.current_scope_runnable ? 'green' : 'default'}>{readiness.current_scope_runnable ? '当前范围可以检查' : '当前范围仍需准备'}</Tag></Space>}</div>
        {activeSampleSelected && <div className="workbench-sample-controls"><Tag color="blue">官方示例</Tag>{presentationReady && <Button type="primary" disabled={experienceBusy} onClick={onEnterPresentation}>进入完整展示</Button>}<Button disabled={experienceBusy} onClick={() => { void onStopExperience?.() }}>结束示例</Button></div>}
      </div>
      {activeSampleSelected && !presentationReady && <Alert className="workbench-presentation-readiness" type="info" showIcon message="完整展示尚未准备好" description="先形成一条可信正式检查结果；界鉴不会用演示占位数据补齐四幕。" />}
      {activeSampleSelected ? <OfficialSampleSetupBar
        status={status}
        experience={experience}
        busy={experienceBusy}
        latestRun={trustedRun}
        sourceBlockRunId={runs.find((item) => item.verdict === 'BLOCK' && item.result_integrity === 'VERIFIED')?.run_id}
        onPrepare={onPrepareExperience}
        onRun={onRunExperience}
        onSwitchVersion={onSwitchExperience}
        onOpenVerification={() => onNavigate('/verification')}
        onOpenChanges={() => onNavigate('/changes')}
        onOpenTests={() => onNavigate('/tests')}
      /> : <div className="workbench-focus-grid">
        <article className={`workbench-primary-focus${primaryItem ? ` is-${primaryItem.tone.toLowerCase()}` : ''}`} aria-label="当前判断与主任务">
          <Typography.Text className="workbench-eyebrow">当前判断</Typography.Text>
          <Typography.Title level={3}>{!status
            ? '正在读取当前应用的安全状态。'
            : primaryReferenceMissing
              ? '当前主任务无法与待办事实对应，请刷新后重试。'
              : primaryItem?.description ?? '当前版本没有待处理事项。'}</Typography.Title>
          {latestChange && <div className="workbench-current-event"><Typography.Text>最近变化</Typography.Text><Typography.Text strong>{latestChange.submitted_by} 提交：{latestChange.reason}</Typography.Text></div>}
          <div className="workbench-primary-action">
            <div className="workbench-primary-action-copy">
              <Typography.Text className="workbench-eyebrow">当前主任务</Typography.Text>
              <Typography.Text type="secondary">{primaryItem
                ? '这一项由当前产品状态明确指定；其他事项仍保留在对应区域。'
                : '新的 Agent 变化到来后，界鉴会继续沿用已经确认的权限规则。'}</Typography.Text>
            </div>
            {primaryItem && <Button type="primary" onClick={() => onNavigate(primaryItem.route)}>{primaryItem.label}</Button>}
          </div>
          {remainingAttentionCount > 0 && <Typography.Text className="workbench-remaining-attention" type="secondary">另有 {remainingAttentionCount} 项状态已归入下方对应区域。</Typography.Text>}
        </article>

        <aside className={`workbench-trusted-result${latestResult?.verdict ? ` is-${latestResult.verdict.toLowerCase()}` : ''}`} aria-label="最近可信结果">
          <Typography.Text className="workbench-eyebrow">最近可信结果</Typography.Text>
          {latestResult ? <>
            <Tag>{latestResult.verdict ? verdictLabel(latestResult.verdict) : '尚无安全结论'}</Tag>
            <Typography.Title level={3}>{latestResult.headline}</Typography.Title>
            <Typography.Paragraph type="secondary">{latestResult.scope_statement}</Typography.Paragraph>
            <Typography.Text type="secondary">{trustedRun ? `形成于 ${formatTimestamp(trustedRun.created_at_us ?? trustedRun.created_at)}` : '来自已发布的可信检查事实'}</Typography.Text>
          </> : <>
            <Typography.Title level={3}>还没有可信检查结果</Typography.Title>
            <Typography.Paragraph type="secondary">完成第一轮真实检查后，这里会显示结论、覆盖范围和对应版本。</Typography.Paragraph>
          </>}
        </aside>
      </div>}
      {systemIssue && <Button type="link" className="workbench-system-link" onClick={() => onNavigate('/settings/system')}>运行环境中有服务暂不可用，查看详情</Button>}
    </section>

    <section className="workbench-domain-panel" aria-labelledby="workbench-domain-title">
      <div className="workbench-secondary-heading"><Typography.Title id="workbench-domain-title" level={3}>专项工作</Typography.Title><Typography.Text type="secondary">按需要进入，不构成固定步骤。</Typography.Text></div>
      <div className="workbench-domain-grid">
        <article><Typography.Text className="workbench-secondary-label">变化</Typography.Text><Typography.Title level={3}>{latestChange ? `${latestChange.actual_changed_path_count} 个文件发生变化` : '尚无变化记录'}</Typography.Title><Typography.Paragraph type="secondary">{latestChange ? `${latestChange.submitted_by}：${latestChange.reason}` : 'Agent 提交变化后，界鉴会核对真实磁盘差异和修复状态。'}</Typography.Paragraph><Button type="link" onClick={() => onNavigate('/changes')}>进入变化</Button></article>
        <article><Typography.Text className="workbench-secondary-label">权限</Typography.Text><Typography.Title level={3}>{readiness?.confirmed_permission_requirement_count ?? 0} 条已确认规则</Typography.Title><Typography.Paragraph type="secondary">{readiness?.permission_representative_gap_count ? `${readiness.permission_representative_gap_count} 条规则缺少可代表的测试路径。` : '在这里维护权限规则、测试账号和业务流程。'}</Typography.Paragraph><Button type="link" onClick={() => onNavigate('/permissions')}>进入权限</Button></article>
        <article><Typography.Text className="workbench-secondary-label">测试</Typography.Text><Typography.Title level={3}>{latestResult?.verdict ? verdictLabel(latestResult.verdict) : '尚无可信结果'}</Typography.Title><Typography.Paragraph type="secondary">{latestResult ? latestResult.headline : '准备条件、运行检查和结果历史集中在同一模块。'}</Typography.Paragraph><Button type="link" onClick={() => onNavigate('/tests')}>进入测试</Button></article>
      </div>
    </section>

    <section className="workbench-secondary-panel" aria-label="交付与最近事实">
      <div className="workbench-delivery-row">
        <div><Typography.Text className="workbench-eyebrow">交付前检查</Typography.Text><Typography.Paragraph type="secondary">需要交付时，再核对当前源码、权限规则与最近可信检查是否属于同一版本。</Typography.Paragraph></div>
        <Button loading={deliveryBusy} onClick={() => void checkDelivery()}>交付前检查</Button>
        {delivery && <Alert
          className="workbench-delivery-result"
          type={delivery.decision === 'READY' ? 'success' : delivery.decision === 'BLOCKED' ? 'warning' : 'error'}
          showIcon
          message={delivery.decision === 'READY' ? '可以交付' : delivery.decision === 'BLOCKED' ? '暂不能交付' : '当前无法可靠完成交付检查'}
          description={delivery.decision === 'READY' ? '当前磁盘源码、权限规则和最新可信完整检查属于同一版本。' : delivery.summary}
          action={delivery.decision === 'BLOCKED' && delivery.next_path ? <Button onClick={() => onNavigate(delivery.next_path!)}>{delivery.next_label ?? '继续处理'}</Button> : undefined}
        />}
      </div>
      <Divider />
      <div className="workbench-activity-section" aria-labelledby="workbench-activity-title">
        <div className="workbench-secondary-heading"><Typography.Title id="workbench-activity-title" level={3}>最近事实</Typography.Title><Typography.Text type="secondary">只列出已经形成的变化和检查。</Typography.Text></div>
        <div className="workbench-activity-list">
          {latestChange && <article><span>Agent / 变化</span><div><strong>{latestChange.reason}</strong><small>{latestChange.submitted_by} · {formatTimestamp(latestChange.created_at_us)}</small></div><Button type="link" onClick={() => onNavigate('/changes')}>查看</Button></article>}
          {latestResult && <article><span>界鉴 / 检查</span><div><strong>{latestResult.headline}</strong><small>{trustedRun ? formatTimestamp(trustedRun.created_at_us ?? trustedRun.created_at) : latestResult.scope_statement}</small></div><Button type="link" onClick={() => onNavigate('/results')}>查看</Button></article>}
          {!latestChange && !latestResult && <Typography.Paragraph type="secondary">当前还没有变化或检查事实。</Typography.Paragraph>}
        </div>
      </div>
    </section>
    {consent}
  </div>
}
