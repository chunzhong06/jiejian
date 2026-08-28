/* 权限与检查连续页：在同一状态链中完成权限确认、准备、预览、提交、进度与结果入口。 */

import { useEffect, useRef, useState } from 'react'
import { Alert, Descriptions, List, Segmented, Space, Tag, Typography } from 'antd'
import { checksApi, type CheckPreviewDto } from '../../api/checks'
import { ApiError } from '../../api/http'
import { permissionIntentsApi, type PermissionIntentMatrixDto, type PermissionIntentExpectation, type SecuritySetupCompileResultDto } from '../../api/permissionIntents'
import type { ProjectDto } from '../../api/projects'
import { runsApi, type RunDto } from '../../api/runs'
import { lifecycleLabel } from '../../app/presentation'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { TaskActionBar } from '../../components/TaskActionBar'
import { PermissionAdvancedPanel } from '../permissions/PermissionAdvancedPanel'
import { CheckProgress } from './CheckProgress'
import './checks.css'

type PermissionCheckPageProps = {
  project: ProjectDto
  runs: RunDto[]
  onRefresh: () => void | Promise<void>
  onError: (error: ApiError) => void
  onResolved?: () => void
  onNavigate: (path: string) => void
  onBack: () => void
  onNext: () => void
}

const terminalStates = new Set(['COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED'])

export function PermissionCheckPage({ project, runs, onRefresh, onError, onResolved, onNavigate, onBack, onNext }: PermissionCheckPageProps) {
  const [matrix, setMatrix] = useState<PermissionIntentMatrixDto | null>(null)
  const [preview, setPreview] = useState<CheckPreviewDto | null>(null)
  const [previewFresh, setPreviewFresh] = useState(false)
  const [requiresCompile, setRequiresCompile] = useState(false)
  const [needsNewRun, setNeedsNewRun] = useState(false)
  const [compileResult, setCompileResult] = useState<SecuritySetupCompileResultDto | null>(null)
  const [currentRun, setCurrentRun] = useState<RunDto | undefined>(runs[0])
  const [savingCell, setSavingCell] = useState<string>()
  const [refreshing, setRefreshing] = useState(false)
  const [compiling, setCompiling] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const reconciledTerminalRun = useRef<string | null>(null)

  const latest = currentRun ?? runs[0]
  const activeRun = Boolean(latest?.run_id && !terminalStates.has(String(latest.lifecycle)))
  const canViewResult = Boolean(latest && ['COMPLETED', 'SAFETY_STOPPED'].includes(String(latest.lifecycle)) && ['VERIFIED', 'INVALID'].includes(String(latest.result_integrity)))
  const canSubmit = Boolean(previewFresh && !requiresCompile && !savingCell && preview?.ready && !activeRun)
  const executableActionCount = preview?.actions.filter((action) => action.ready).length ?? 0
  const uncoveredActionCount = preview?.actions.filter((action) => !action.ready).length ?? 0
  const allowCount = preview?.actions.flatMap((action) => action.checks).filter((item) => item.expectation === 'ALLOW').length ?? 0
  const denyCount = preview?.actions.flatMap((action) => action.checks).filter((item) => item.expectation === 'DENY').length ?? 0

  useEffect(() => { setCurrentRun(runs[0]) }, [runs])
  useEffect(() => {
    let active = true
    setMatrix(null)
    setPreview(null)
    setPreviewFresh(false)
    setRequiresCompile(false)
    setNeedsNewRun(false)
    setCompileResult(null)
    setRefreshing(true)
    void Promise.all([
      permissionIntentsApi.matrix(project.project_id),
      checksApi.preview(project.project_id),
    ]).then(([nextMatrix, nextPreview]) => {
      if (!active) return
      setMatrix(nextMatrix)
      setPreview(nextPreview)
      setPreviewFresh(true)
      onResolved?.()
    }).catch((error) => { if (active) onError(error as ApiError) }).finally(() => { if (active) setRefreshing(false) })
    return () => { active = false }
  }, [project.project_id])

  useEffect(() => {
    const summary = runs[0]
    if (!summary?.run_id) return
    let active = true
    void runsApi.run(String(summary.run_id)).then((run) => { if (active) setCurrentRun(run) }).catch((error) => { if (active) onError(error as ApiError) })
    return () => { active = false }
  }, [runs[0]?.run_id, runs[0]?.lifecycle, runs[0]?.updated_at_us, runs[0]?.job?.state])

  useEffect(() => {
    if (!latest?.run_id || !terminalStates.has(String(latest.lifecycle))) return
    const terminalKey = `${latest.run_id}:${latest.lifecycle}:${latest.job?.state ?? ''}`
    if (reconciledTerminalRun.current === terminalKey) return
    reconciledTerminalRun.current = terminalKey
    // Run 与 Readiness 分接口读取；终态出现后补读一次，避免页面组合旧活动任务与新结果。
    void onRefresh()
  }, [latest?.run_id, latest?.lifecycle, latest?.job?.state, onRefresh])

  const invalidatePreview = () => {
    setPreview(null)
    setPreviewFresh(false)
    setRequiresCompile(true)
    setNeedsNewRun(true)
    setCompileResult(null)
  }

  const confirm = async (actionId: string, subjectRoleId: string, ownerRoleId: string, relation: 'OWNS' | 'SAME_ROLE_OTHER_ACCOUNT' | 'OTHER_ROLE', value: string | number) => {
    const key = `${actionId}:${subjectRoleId}:${ownerRoleId}:${relation}`
    invalidatePreview()
    setSavingCell(key)
    try {
      const expectation = value === 'ALLOW' || value === 'DENY' ? value as PermissionIntentExpectation : null
      setMatrix(await permissionIntentsApi.confirm(project.project_id, actionId, subjectRoleId, ownerRoleId, relation, expectation, 'local-user'))
      await onRefresh()
    } catch (error) { onError(error as ApiError) }
    finally { setSavingCell(undefined) }
  }

  const authorityChanged = () => {
    invalidatePreview()
    void permissionIntentsApi.matrix(project.project_id).then(setMatrix).catch((error) => onError(error as ApiError))
    void onRefresh()
  }

  const compile = async () => {
    if (savingCell) return
    setCompiling(true)
    setPreview(null)
    setPreviewFresh(false)
    setRequiresCompile(true)
    try {
      const result = await permissionIntentsApi.compile(project.project_id, 'local-user')
      setCompileResult(result)
      const [nextMatrix, nextPreview] = await Promise.all([
        permissionIntentsApi.matrix(project.project_id),
        checksApi.preview(project.project_id),
      ])
      setMatrix(nextMatrix)
      setPreview(nextPreview)
      setPreviewFresh(true)
      setRequiresCompile(false)
      await onRefresh()
      onResolved?.()
    } catch (error) { onError(error as ApiError) }
    finally { setCompiling(false) }
  }

  const refreshFacts = async () => {
    setRefreshing(true)
    try {
      const [nextMatrix, nextPreview] = await Promise.all([
        permissionIntentsApi.matrix(project.project_id),
        checksApi.preview(project.project_id),
      ])
      setMatrix(nextMatrix)
      setPreview(nextPreview)
      setPreviewFresh(true)
      if (latest?.run_id) setCurrentRun(await runsApi.run(String(latest.run_id)))
      await onRefresh()
      onResolved?.()
    } catch (error) { onError(error as ApiError) }
    finally { setRefreshing(false) }
  }

  const refreshRun = () => {
    void onRefresh()
    if (latest?.run_id) void runsApi.run(String(latest.run_id)).then(setCurrentRun).catch((error) => onError(error as ApiError))
  }

  const submit = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    try {
      const result = await checksApi.submit(project.project_id)
      setCurrentRun(result.run)
      setNeedsNewRun(false)
      await onRefresh()
      onResolved?.()
    } catch (error) { onError(error as ApiError) }
    finally { setSubmitting(false) }
  }

  const cancel = async () => {
    const jobId = latest?.job?.job_id
    if (!jobId) return
    setCancelling(true)
    try {
      await runsApi.cancel(String(jobId))
      refreshRun()
    } catch (error) { onError(error as ApiError) }
    finally { setCancelling(false) }
  }

  const currentStage = activeRun
    ? 5
    : canViewResult && !needsNewRun
      ? 6
      : canSubmit
        ? 4
        : previewFresh && preview
          ? 3
          : matrix?.compilable_action_count
            ? 2
            : 1
  const sequence = ['确认权限要求', '准备检查条件', '核对本次范围', '开始检查', '查看当前进度', '完成并查看结果']
  const titleStatus = activeRun ? lifecycleLabel(latest?.lifecycle) : canViewResult && !needsNewRun ? '检查已完成' : canSubmit ? '可以开始检查' : requiresCompile ? '权限要求已更新' : '正在准备检查'

  const primary = activeRun
    ? undefined
    : canViewResult && !needsNewRun
      ? { label: '查看检查结果', onClick: onNext }
      : canSubmit
        ? { label: latest && terminalStates.has(String(latest.lifecycle)) ? '重新开始检查' : '开始检查', onClick: () => void submit(), loading: submitting }
        : savingCell
          ? { label: '正在保存权限要求', disabled: true, loading: true }
        : previewFresh && !requiresCompile && preview?.next_path && preview.next_path !== '/check'
          ? { label: preview.next_label ?? '去完成测试条件', onClick: () => onNavigate(preview.next_path!) }
          : matrix?.compilable_action_count
            ? { label: '准备本次检查', onClick: () => void compile(), loading: compiling }
            : { label: refreshing ? '正在读取权限要求' : '确认允许和拒绝后继续', disabled: true }

  const restart = activeRun && latest?.job?.job_id
    ? {
      label: '取消当前检查', onClick: () => void cancel(), loading: cancelling, danger: true,
      confirm: { title: '取消当前检查？', description: '界鉴会请求后台停止尚未完成的检查，并保留已经形成的运行记录；取消不会产生安全结论。', okText: '确认取消', cancelText: '继续检查' },
    }
    : canViewResult && !needsNewRun && canSubmit
      ? {
        label: '重新检查当前范围', onClick: () => void submit(), loading: submitting,
        confirm: { title: '重新检查当前范围？', description: '界鉴会创建一次新的受控检查；已经发布的结果和历史记录不会被覆盖。', okText: '开始新检查', cancelText: '取消' },
      }
      : undefined

  return <div className="permission-check-page">
    <PageTaskHeader title="权限与检查" description="先确认谁应该允许或拒绝，再核对测试账号和对照范围，最后由界鉴在受控环境中检查真实结果。" status={titleStatus} />
    <ol className="task-sequence permission-check-sequence" aria-label="权限与检查进度">
      {sequence.map((label, index) => {
        const step = index + 1
        const state = step < currentStage ? 'complete' : step === currentStage ? 'current' : 'upcoming'
        return <li key={label} className={`task-sequence-step is-${state}`}><span>{step < currentStage ? '✓' : step}</span><div><strong>{label}</strong><small>{state === 'complete' ? '已完成' : state === 'current' ? '当前任务' : '随后进行'}</small></div></li>
      })}
    </ol>

    <section className="permission-check-section" aria-labelledby="permission-requirements-title">
      <div className="permission-check-heading"><div><Typography.Title level={3} id="permission-requirements-title">确认权限要求</Typography.Title><Typography.Paragraph type="secondary">为每个权限组和资源关系选择“允许”或“拒绝”。这里表达的是你的安全要求，不是界鉴自动作出的漏洞结论。</Typography.Paragraph></div><Tag>{matrix ? `已确认 ${matrix.confirmed_count} 项` : '正在读取'}</Tag></div>
      {matrix?.actions.length === 0 && <Alert type="info" showIcon message="还没有可确认的业务动作" description="请先完成业务流程录制，并确认测试资源、真实结果观察和恢复方式。" />}
      <div className="permission-requirement-list">
        {matrix?.actions.map((action) => <article className="permission-requirement-action" key={action.action_candidate_id}>
          <div className="permission-requirement-title"><div><Typography.Title level={4}>{action.action_display_name}</Typography.Title><Typography.Text type="secondary">测试资源：{action.resource_logical_name ?? '尚未准备'}</Typography.Text></div><Tag color={action.compilable ? 'success' : 'warning'}>{action.compilable ? '允许与拒绝已齐全' : '仍需确认'}</Tag></div>
          {action.cells.map((cell) => {
            const key = `${action.action_candidate_id}:${cell.subject_role_candidate_id}:${cell.resource_owner_role_candidate_id}:${cell.relation}`
            const blocking = cell.review_reasons.some((reason) => !['PERMISSION_INTENT_UNCONFIRMED', 'PERMISSION_INTENT_STALE'].includes(reason))
            return <div className="permission-requirement-row" key={key}>
              <div><Typography.Text strong>{cell.subject_role_display_name} · {relationLabels[cell.relation]}</Typography.Text><Typography.Text type="secondary">资源属于 {cell.resource_owner_role_display_name} 权限组</Typography.Text></div>
              <Segmented aria-label={`${cell.subject_role_display_name}权限组以${relationLabels[cell.relation]}关系对${action.action_display_name}的权限`} value={cell.expectation ?? 'UNCONFIRMED'} disabled={blocking || savingCell === key || activeRun} options={[{ label: '未确认', value: 'UNCONFIRMED' }, { label: '允许', value: 'ALLOW' }, { label: '拒绝', value: 'DENY' }]} onChange={(value) => void confirm(action.action_candidate_id, cell.subject_role_candidate_id, cell.resource_owner_role_candidate_id, cell.relation, value)} />
              <div className="permission-requirement-note">{cell.status === 'NEEDS_REVIEW' && <Typography.Text type="warning">依赖事实已变化，请重新确认</Typography.Text>}{blocking && <Typography.Text type="danger">{cell.review_reasons.map((reason) => gapLabels[reason] ?? reason).join('、')}</Typography.Text>}{cell.execution_gap && <Typography.Text type="secondary">{executionGapLabel(cell.execution_gap, cell)}</Typography.Text>}</div>
            </div>
          })}
          {action.gaps.length > 0 && <Typography.Paragraph type="secondary" className="permission-requirement-gaps">尚缺：{action.gaps.map((gap) => gapLabels[gap] ?? gap).join('、')}</Typography.Paragraph>}
        </article>)}
      </div>
    </section>

    <section className="permission-check-section" aria-labelledby="check-preparation-title">
      <div className="permission-check-heading"><div><Typography.Title level={3} id="check-preparation-title">准备检查条件</Typography.Title><Typography.Paragraph type="secondary">界鉴会把已确认权限要求与业务流程、测试账号、观察和恢复方式编译成一次受控检查。</Typography.Paragraph></div></div>
      {requiresCompile && <Alert type="warning" showIcon message="权限要求已经更新，旧检查预览已失效" description="请重新准备检查。只有重新生成配置并读取新的检查预览后，才能开始检查。" />}
      {!requiresCompile && compileResult && <Alert type="success" showIcon message={compileResult.reused ? '当前检查条件已经重新确认' : '检查条件已经准备好'} description={`已准备 ${compileResult.covered_action_ids.length} 个业务动作；${matrix?.representative_gap_count ?? 0} 项权限要求暂缺测试条件。`} />}
      {!requiresCompile && !compileResult && previewFresh && preview?.ready && <Alert type="success" showIcon message="当前检查条件已经准备好" description="下面的预览来自后端当前权威事实，可以继续核对本次检查范围。" />}
      {!requiresCompile && !compileResult && (!previewFresh || !preview?.ready) && <Alert type="info" showIcon message={matrix?.compilable_action_count ? '权限要求可以生成检查条件' : '还需要确认允许和拒绝'} description={matrix?.compilable_action_count ? '点击页面底部“准备本次检查”后，界鉴会重新生成配置并读取最新预览。' : '至少完成一个业务动作的允许/拒绝对照后才能准备检查。'} />}
    </section>

    <section className="permission-check-section" aria-labelledby="check-preview-title">
      <div className="permission-check-heading"><div><Typography.Title level={3} id="check-preview-title">核对本次检查</Typography.Title><Typography.Paragraph type="secondary">确认本次会使用哪些测试账号、验证哪些允许/拒绝对照，以及哪些权限要求尚未覆盖。</Typography.Paragraph></div>{previewFresh && preview && <Tag color={preview.ready ? 'success' : 'warning'}>{preview.ready ? '可以检查' : '仍有缺项'}</Tag>}</div>
      {!previewFresh && <Typography.Text type="secondary">{requiresCompile ? '等待重新准备检查条件。' : '正在读取当前检查范围……'}</Typography.Text>}
      {previewFresh && preview && <>
        <Descriptions className="check-preview-summary" column={{ xs: 1, sm: 2, md: 4 }}>
          <Descriptions.Item label="可检查业务动作">{executableActionCount}</Descriptions.Item>
          <Descriptions.Item label="测试账号用例">{preview.case_count}</Descriptions.Item>
          <Descriptions.Item label="应该允许 / 应该拒绝">{allowCount} / {denyCount}</Descriptions.Item>
          <Descriptions.Item label="暂未覆盖业务动作">{uncoveredActionCount}</Descriptions.Item>
        </Descriptions>
        <div className="check-preview-actions">
          {preview.actions.map((action) => <article className="check-preview-action" key={action.action_candidate_id}>
            <div className="check-preview-action-title"><div><Typography.Title level={4}>{action.action_display_name}</Typography.Title>{action.resource_logical_name && <Typography.Text type="secondary">测试资源：{action.resource_logical_name}</Typography.Text>}</div><Tag color={action.ready ? 'success' : 'warning'}>{action.ready ? '纳入本次检查' : '暂未覆盖'}</Tag></div>
            {action.gaps.length > 0 && <Alert type="warning" showIcon message="这个动作暂未覆盖" description={action.gaps.map((gap) => gap.message).join('；')} />}
            <List className="check-preview-list" dataSource={action.checks} locale={{ emptyText: '尚无账号检查项' }} renderItem={(item) => <List.Item extra={<Tag color={item.expectation === 'ALLOW' ? 'green' : item.expectation === 'DENY' ? 'red' : 'default'}>{item.expectation === 'ALLOW' ? '应该允许' : item.expectation === 'DENY' ? '应该拒绝' : '尚未确认'}</Tag>}><List.Item.Meta title={item.subject_label} description={`${item.subject_role_display_name} · ${relationLabels[item.relation] ?? '当前资源关系'}${item.gaps.length ? ` · ${item.gaps.map((gap) => gap.message).join('、')}` : ''}`} /></List.Item>} />
          </article>)}
        </div>
        {preview.ready && <Alert type="success" showIcon message={`将执行 ${preview.case_count} 个检查用例，形成 ${preview.differential_pair_count} 组允许/拒绝对照${uncoveredActionCount > 0 ? `；另有 ${uncoveredActionCount} 个动作暂未覆盖` : ''}。`} />}
        {!preview.ready && preview.gaps.length > 0 && <Alert type="warning" showIcon message="当前还不能开始检查" description={preview.gaps.map((gap) => gap.message).join('；')} />}
      </>}
    </section>

    <section className="permission-check-section" aria-labelledby="current-check-title">
      <div className="permission-check-heading"><div><Typography.Title level={3} id="current-check-title">开始检查并查看进度</Typography.Title><Typography.Paragraph type="secondary">开始后，界鉴会先验证正常允许的操作，再尝试不应允许的操作，并通过可信观察确认真实资源结果和恢复测试数据。</Typography.Paragraph></div>{latest?.run_id && <Tag>{lifecycleLabel(latest.lifecycle)}</Tag>}</div>
      {!latest && <Typography.Text type="secondary">准备和预览完成后，可从页面底部开始本次检查。</Typography.Text>}
      {latest && <CheckProgress run={latest} actions={preview?.actions} onRefresh={refreshRun} onError={onError} onNavigate={onNavigate} />}
      {canViewResult && !needsNewRun && <Alert type="success" showIcon message="本次检查已经完成" description="可信结果已经发布，可以继续查看检查结果和证据。" />}
    </section>

    <PermissionAdvancedPanel project={project} onError={onError} onAuthorityChanged={authorityChanged} />
    <TaskActionBar back={{ label: '返回业务流程', onClick: onBack }} refresh={{ label: '刷新当前状态', onClick: () => void refreshFacts(), loading: refreshing }} restart={restart} primary={primary} />
  </div>
}

const relationLabels: Record<string, string> = {
  OWNS: '自己的资源', SAME_ROLE_OTHER_ACCOUNT: '同权限组其他用户的资源', OTHER_ROLE: '其他权限组的资源',
}
function executionGapLabel(gap: string, cell: PermissionIntentMatrixDto['actions'][number]['cells'][number]) {
  if (gap === 'TEST_IDENTITY_MISSING' && cell.relation === 'SAME_ROLE_OTHER_ACCOUNT') return `还需要第二个${cell.subject_role_display_name}测试账号才能检查这一项`
  if (gap === 'TEST_IDENTITY_MISSING') return `还需要${cell.subject_role_display_name}测试账号才能检查这一项`
  if (gap === 'TEST_IDENTITY_NOT_PREPARED') return `还需要${cell.subject_role_display_name}测试账号完成登录准备`
  return gapLabels[gap] ?? gap
}
const gapLabels: Record<string, string> = {
  ACTION_FLOW_OR_RESOURCE_MISSING: '尚未录制并确认业务动作', ACTION_SAFETY_SETUP_STALE: '业务动作准备信息已经变化',
  RESOURCE_OWNER_ROLE_UNCONFIRMED: '资源所有者权限组尚未确认', TEST_RESOURCE_UNCONFIRMED: '测试资源未确认',
  OBSERVATION_UNCONFIRMED: '可信观察方式未确认', RECOVERY_UNCONFIRMED: '安全恢复方式未确认',
  SECURITY_EFFECT_UNCONFIRMED: '真实影响未确认', TEST_IDENTITY_MISSING: '缺少测试账号',
  TEST_IDENTITY_NOT_PREPARED: '测试账号尚未准备', ALLOW_INTENT_MISSING: '缺少一个可执行的允许权限组',
  DENY_INTENT_MISSING: '缺少一个可执行的拒绝权限组', PERMISSION_INTENT_NEEDS_REVIEW: '已有权限要求需要重新确认',
}
