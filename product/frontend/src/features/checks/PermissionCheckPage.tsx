/* 权限规则与验证运行共享同一事实读取；页面只按长期工作区拆分用户任务。 */

import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Descriptions, Input, List, Modal, Segmented, Space, Tag, Typography } from 'antd'
import { checksApi, type CheckPreviewDto } from '../../api/checks'
import { ApiError } from '../../api/http'
import { permissionIntentsApi, type PermissionDraftDto, type PermissionDraftSuggestionDto, type PermissionIntentCellDto, type PermissionIntentExpectation, type PermissionIntentMatrixDto, type PermissionIntentProposalDto } from '../../api/permissionIntents'
import type { ProjectDto } from '../../api/projects'
import { runsApi, type RunDto } from '../../api/runs'
import { lifecycleLabel } from '../../app/presentation'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { AssistantPanel } from '../../components/AssistantPanel'
import { TaskActionBar } from '../../components/TaskActionBar'
import { CheckProgress } from './CheckProgress'
import './checks.css'

type PermissionCheckPageProps = {
  mode: 'permissions' | 'validation'
  project: ProjectDto
  runs: RunDto[]
  onRefresh: () => void | Promise<void>
  onError: (error: ApiError) => void
  onResolved?: () => void
  onNavigate: (path: string) => void
  onBack: () => void
  onContinuePreparation?: () => Promise<void> | void
  onResult?: () => void
  changeId?: string
}

const terminalStates = new Set(['COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED'])

export function PermissionCheckPage({ mode, project, runs, onRefresh, onError, onResolved, onNavigate, onBack, onContinuePreparation, onResult, changeId }: PermissionCheckPageProps) {
  const [matrix, setMatrix] = useState<PermissionIntentMatrixDto | null>(null)
  const [proposals, setProposals] = useState<PermissionIntentProposalDto[]>([])
  const [preview, setPreview] = useState<CheckPreviewDto | null>(null)
  const [previewFresh, setPreviewFresh] = useState(false)
  const [requiresCompile, setRequiresCompile] = useState(false)
  const [needsNewRun, setNeedsNewRun] = useState(false)
  const [preparedNow, setPreparedNow] = useState(false)
  const [currentRun, setCurrentRun] = useState<RunDto | undefined>(runs[0])
  const [savingCell, setSavingCell] = useState<string>()
  const [refreshing, setRefreshing] = useState(false)
  const [compiling, setCompiling] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [pendingChange, setPendingChange] = useState<PendingPermissionChange | null>(null)
  const [draftInput, setDraftInput] = useState('')
  const [draftSourceText, setDraftSourceText] = useState('')
  const [draft, setDraft] = useState<PermissionDraftDto | null>(null)
  const [drafting, setDrafting] = useState(false)
  const [pendingDraftOptionId, setPendingDraftOptionId] = useState<string>()
  const [savingProposalId, setSavingProposalId] = useState<string>()
  const reconciledTerminalRun = useRef<string | null>(null)
  const readPreview = () => changeId
    ? checksApi.preview(project.project_id, changeId)
    : checksApi.preview(project.project_id)

  const latest = currentRun ?? runs[0]
  const activeRun = Boolean(latest?.run_id && !terminalStates.has(String(latest.lifecycle)))
  const canViewResult = Boolean(latest && ['COMPLETED', 'SAFETY_STOPPED'].includes(String(latest.lifecycle)) && ['VERIFIED', 'INVALID'].includes(String(latest.result_integrity)))
  const canSubmit = Boolean(previewFresh && !requiresCompile && !savingCell && preview?.ready && !activeRun)
  const executableActionCount = preview?.actions.filter((action) => action.ready).length ?? 0
  const uncoveredActionCount = preview?.actions.filter((action) => !action.ready).length ?? 0
  const allowCount = preview?.actions.flatMap((action) => action.checks).filter((item) => item.expectation === 'ALLOW').length ?? 0
  const denyCount = preview?.actions.flatMap((action) => action.checks).filter((item) => item.expectation === 'DENY').length ?? 0
  const allowChecks = preview?.actions.flatMap((action) => action.checks.filter((item) => item.expectation === 'ALLOW').map((item) => ({ ...item, action: action.action_display_name }))) ?? []
  const denyChecks = preview?.actions.flatMap((action) => action.checks.filter((item) => item.expectation === 'DENY').map((item) => ({ ...item, action: action.action_display_name }))) ?? []
  const protectedEffects = Array.from(new Set(matrix?.actions.flatMap((action) => action.cells.flatMap((cell) => cell.protected_effects.map((effect) => effect.business_label || effect.resource_type))) ?? []))

  useEffect(() => { setCurrentRun(runs[0]) }, [runs])
  useEffect(() => {
    let active = true
    setMatrix(null)
    setProposals([])
    setPreview(null)
    setPreviewFresh(false)
    setRequiresCompile(false)
    setNeedsNewRun(false)
    setPreparedNow(false)
    setDraftInput('')
    setDraftSourceText('')
    setDraft(null)
    setPendingDraftOptionId(undefined)
    setRefreshing(true)
    void Promise.all([
      permissionIntentsApi.matrix(project.project_id),
      permissionIntentsApi.proposals(project.project_id),
      readPreview(),
    ]).then(([nextMatrix, proposalView, nextPreview]) => {
      if (!active) return
      setMatrix(nextMatrix)
      setProposals(proposalView.proposals)
      setPreview(nextPreview)
      setPreviewFresh(true)
      onResolved?.()
    }).catch((error) => { if (active) onError(error as ApiError) }).finally(() => { if (active) setRefreshing(false) })
    return () => { active = false }
  }, [project.project_id, changeId])

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
    setPreparedNow(false)
  }

  const refreshPermissionFacts = async () => {
    const [nextMatrix, proposalView] = await Promise.all([
      permissionIntentsApi.matrix(project.project_id),
      permissionIntentsApi.proposals(project.project_id),
    ])
    setMatrix(nextMatrix)
    setProposals(proposalView.proposals)
  }

  const approveChange = async () => {
    if (!pendingChange) return
    const { actionId, cell, expectation } = pendingChange
    const key = permissionCellKey(actionId, cell)
    invalidatePreview()
    setSavingCell(key)
    try {
      await permissionIntentsApi.approve(project.project_id, {
        action_candidate_id: actionId,
        subject_role_candidate_id: cell.subject_role_candidate_id,
        resource_owner_role_candidate_id: cell.resource_owner_role_candidate_id,
        relation: cell.relation,
      }, expectation)
      await refreshPermissionFacts()
      await onRefresh()
      if (pendingDraftOptionId) {
        setDraft((current) => current ? {
          ...current,
          suggestions: current.suggestions.filter((item) => item.option_id !== pendingDraftOptionId),
        } : current)
      }
      setPendingChange(null)
      setPendingDraftOptionId(undefined)
    } catch (error) { onError(error as ApiError) }
    finally { setSavingCell(undefined) }
  }

  const createDraft = async () => {
    const text = draftInput.trim()
    if (!text) return
    setDrafting(true)
    try {
      const nextDraft = await permissionIntentsApi.draft(project.project_id, text)
      setDraftSourceText(text)
      setDraft(nextDraft)
    } catch (error) { onError(error as ApiError) }
    finally { setDrafting(false) }
  }

  const confirmDraftSuggestion = (suggestion: PermissionDraftSuggestionDto) => {
    const cell = findDraftCell(suggestion, matrix)
    if (!cell) return
    setPendingDraftOptionId(suggestion.option_id)
    setPendingChange({
      actionId: suggestion.action_candidate_id,
      cell,
      expectation: suggestion.suggested_expectation,
    })
  }

  const ignoreDraftSuggestion = (optionId: string) => {
    setDraft((current) => current ? {
      ...current,
      suggestions: current.suggestions.filter((item) => item.option_id !== optionId),
    } : current)
  }

  const decideProposal = async (proposal: PermissionIntentProposalDto, decision: 'approve' | 'reject') => {
    setSavingProposalId(proposal.proposal_id)
    try {
      if (decision === 'approve') {
        invalidatePreview()
        await permissionIntentsApi.approveProposal(project.project_id, proposal.proposal_id)
      } else {
        await permissionIntentsApi.rejectProposal(project.project_id, proposal.proposal_id)
      }
      await refreshPermissionFacts()
      await onRefresh()
    } catch (error) { onError(error as ApiError) }
    finally { setSavingProposalId(undefined) }
  }

  const compile = async () => {
    if (savingCell) return
    setCompiling(true)
    setPreview(null)
    setPreviewFresh(false)
    setRequiresCompile(true)
    try {
      const [nextMatrix, proposalView, nextPreview] = await Promise.all([
        permissionIntentsApi.matrix(project.project_id),
        permissionIntentsApi.proposals(project.project_id),
        checksApi.prepare(project.project_id, changeId),
      ])
      setPreparedNow(true)
      setMatrix(nextMatrix)
      setProposals(proposalView.proposals)
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
      const [nextMatrix, proposalView, nextPreview] = await Promise.all([
        permissionIntentsApi.matrix(project.project_id),
        permissionIntentsApi.proposals(project.project_id),
        readPreview(),
      ])
      setMatrix(nextMatrix)
      setProposals(proposalView.proposals)
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
      const result = await (changeId
        ? checksApi.submit(project.project_id, changeId)
        : checksApi.submit(project.project_id))
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

  const titleStatus = activeRun ? lifecycleLabel(latest?.lifecycle) : canViewResult && !needsNewRun ? '检查已完成' : canSubmit ? '可以开始检查' : requiresCompile ? '权限要求已更新' : '正在准备检查'
  const profilePreparationNeeded = requiresCompile || !previewFresh || Boolean(
    preview?.gaps.some((gap) => gap.code === 'GENERATED_PROFILE_MISSING' || gap.code === 'GENERATED_PROFILE_STALE'),
  )

  const assistantPanel = hasObservationGap(matrix, preview)
    ? { surface: 'observation-recovery' as const, title: '观察与恢复说明', actionLabel: 'AI 解释为什么还不能可靠检查' }
    : { surface: 'check-preview-explanation' as const, title: '本次检查范围', actionLabel: 'AI 解读本次检查' }

  const primary = activeRun
    ? undefined
    : canViewResult && !needsNewRun
      ? { label: '查看检查结果', onClick: onResult }
      : canSubmit
        ? { label: latest && terminalStates.has(String(latest.lifecycle)) ? '重新开始真实检查' : '开始真实检查', onClick: () => void submit(), loading: submitting }
        : savingCell
          ? { label: '正在保存权限要求', disabled: true, loading: true }
        : matrix?.compilable_action_count && profilePreparationNeeded
          ? { label: '准备本次检查', onClick: () => void compile(), loading: compiling }
        : previewFresh && !requiresCompile && preview?.next_path && preview.next_path !== '/validation'
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
    <PageTaskHeader
      title={mode === 'permissions' ? '权限规则' : '验证运行'}
      description={mode === 'permissions'
        ? '确认谁可以执行哪些业务动作。Agent 可以提出建议，但只有人能批准权限规则和实现对应关系。'
        : '按当前完整权限范围核对测试条件，并在受控环境中检查页面响应、后台任务和真实业务后果。'}
      status={mode === 'permissions' ? `${matrix?.confirmed_count ?? 0} 项已确认` : titleStatus}
    />
    {mode === 'permissions' && <><section className="permission-check-section permission-draft-section" aria-labelledby="permission-draft-title">
      <div className="permission-check-heading"><div><Typography.Title level={3} id="permission-draft-title">用一句话描述权限要求</Typography.Title><Typography.Paragraph type="secondary">界鉴只会把你的原话整理成待确认建议，不会自动修改权限规则。</Typography.Paragraph></div><Tag>可选</Tag></div>
      <Input.TextArea aria-label="权限要求原话" value={draftInput} maxLength={2000} showCount rows={4} placeholder="例如：普通成员可以查看自己的资料，但不能导出完整项目包。" onChange={(event) => setDraftInput(event.target.value)} />
      <div><Button type="primary" loading={drafting} disabled={!draftInput.trim()} onClick={() => void createDraft()}>整理成待确认规则</Button></div>
      {draft?.status === 'UNAVAILABLE' && <Alert type="warning" showIcon message="自然语言整理暂不可用" description="正式权限矩阵仍然完整可用，你可以直接在下方确认允许和拒绝。" />}
      {draft?.status === 'PARTIAL' && <Alert type="info" showIcon message="还有部分内容无法可靠对应" description="已验证的建议仍可逐条确认；其余内容请人工查看下方权限矩阵。" />}
      {draft && draft.status !== 'UNAVAILABLE' && <div className="permission-draft-results">
        <div className="permission-draft-source"><Typography.Text strong>用户原话</Typography.Text><Typography.Paragraph>{draftSourceText}</Typography.Paragraph></div>
        {draft.suggestions.map((suggestion) => {
          const available = findDraftCell(suggestion, matrix)?.can_confirm === true
          return <article className="permission-draft-card" key={suggestion.option_id}>
            <div className="permission-draft-card-heading"><Typography.Text strong>{suggestion.subject_display_name} · {suggestion.action_display_name}</Typography.Text><Tag color="blue">待你确认</Tag></div>
            <Descriptions size="small" column={1}>
              <Descriptions.Item label="当前业务单元">{suggestion.subject_display_name}以{relationLabels[suggestion.relation]}关系，对{suggestion.resource_owner_display_name}的资源执行“{suggestion.action_display_name}”</Descriptions.Item>
              <Descriptions.Item label="当前规则">{expectationLabel(suggestion.current_expectation)}</Descriptions.Item>
              <Descriptions.Item label="AI 建议规则">{expectationLabel(suggestion.suggested_expectation)}</Descriptions.Item>
              <Descriptions.Item label="原文依据">“{suggestion.source_quote}”</Descriptions.Item>
            </Descriptions>
            <Space><Button type="primary" disabled={!available || activeRun || Boolean(savingCell)} onClick={() => confirmDraftSuggestion(suggestion)}>确认这条</Button><Button disabled={Boolean(savingCell)} onClick={() => ignoreDraftSuggestion(suggestion.option_id)}>忽略</Button></Space>
            {!available && <Typography.Text type="warning">当前权限矩阵已经变化，请重新整理后再确认。</Typography.Text>}
          </article>
        })}
        {draft.issues.map((issue, index) => <Alert key={`${issue.code}-${index}`} type="info" showIcon message={issue.message} description={issue.source_quote ? `未可靠对应：“${issue.source_quote}”` : undefined} />)}
        {draft.suggestions.length === 0 && <Typography.Text type="secondary">当前草稿没有待确认建议，请继续人工核对权限矩阵。</Typography.Text>}
      </div>}
    </section>

    <section className="permission-check-section" aria-labelledby="permission-requirements-title">
      <div className="permission-check-heading"><div><Typography.Title level={3} id="permission-requirements-title">确认权限要求</Typography.Title><Typography.Paragraph type="secondary">为每个权限组和资源关系选择“允许”或“拒绝”。这里表达的是你的安全要求，不是界鉴自动作出的漏洞结论。</Typography.Paragraph></div><Tag>{matrix ? `已确认 ${matrix.confirmed_count} 项` : '正在读取'}</Tag></div>
      {matrix?.actions.length === 0 && <Alert type="info" showIcon message="还没有可确认的业务动作" description="请先完成业务流程录制，并确认测试资源、真实结果观察和恢复方式。" />}
      {matrix && matrix.actions.length > 0 && matrix.required_confirmation_count === 0 && matrix.actions.some((action) => !action.compilable) && <Alert type="info" showIcon message="当前还没有真正可确认的权限规则" description="当前还缺业务流程、测试资源或其他前置事实。先完成测试准备后，界鉴才会让你确认真正可执行的权限规则。" />}
      <div className="permission-requirement-list">
        {matrix?.actions.map((action) => <article className="permission-requirement-action" key={action.action_candidate_id}>
          <div className="permission-requirement-title"><div><Typography.Title level={4}>{action.action_display_name}</Typography.Title><Typography.Text type="secondary">测试资源：{action.resource_logical_name ?? '尚未准备'}</Typography.Text></div><Tag color={action.compilable ? 'success' : action.cells.some((cell) => cell.requires_human_confirmation) ? 'warning' : 'default'}>{action.compilable ? '允许与拒绝已齐全' : action.cells.some((cell) => cell.requires_human_confirmation) ? '仍需确认' : '等待准备事实'}</Tag></div>
          {action.cells.map((cell) => {
            const key = permissionCellKey(action.action_candidate_id, cell)
            return <div className="permission-requirement-row" key={key}>
              <div className="permission-sentence">
                <Typography.Text className="permission-sentence-role">{cell.subject_role_display_name}</Typography.Text>
                <Typography.Text className={`permission-sentence-expectation is-${String(cell.expectation ?? 'UNCONFIRMED').toLowerCase()}`}>{cell.expectation === 'ALLOW' ? '允许' : cell.expectation === 'DENY' ? '不允许' : '尚未确认是否允许'}</Typography.Text>
                <Typography.Text>对{resourceRelationLabel(cell)}的“{action.resource_logical_name ?? '受保护业务对象'}”</Typography.Text>
                <Typography.Text>执行“{action.action_display_name}”</Typography.Text>
                <div className={`permission-effect-summary is-${String(cell.expectation ?? 'UNCONFIRMED').toLowerCase()}`}><Typography.Text strong>{cell.expectation === 'ALLOW' ? '合法功能必须保持：' : cell.expectation === 'DENY' ? '禁止发生：' : '需要确认的真实业务后果：'}</Typography.Text>{cell.protected_effects.length > 0 ? <ul>{cell.protected_effects.map((effect, index) => <li key={`${effect.business_label}-${index}`}>{effect.business_label || effect.resource_type}</li>)}</ul> : <Typography.Text type="secondary">尚未确认受保护业务后果</Typography.Text>}</div>
              </div>
              <div className="permission-requirement-control"><Segmented aria-label={`${cell.subject_role_display_name}权限组以${relationLabels[cell.relation]}关系对${action.action_display_name}的权限`} value={cell.expectation ?? 'UNCONFIRMED'} disabled={!cell.can_confirm || savingCell === key || activeRun} options={[{ label: '未确认', value: 'UNCONFIRMED' }, { label: '允许', value: 'ALLOW' }, { label: '拒绝', value: 'DENY' }]} onChange={(value) => setPendingChange({ actionId: action.action_candidate_id, cell, expectation: value === 'ALLOW' || value === 'DENY' ? value : null })} />{cell.status === 'NEEDS_REVIEW' && cell.expectation !== null && cell.can_confirm && <Button type="link" size="small" disabled={savingCell === key || activeRun} onClick={() => setPendingChange({ actionId: action.action_candidate_id, cell, expectation: cell.expectation })}>重新确认当前要求</Button>}{cell.requires_human_confirmation && <Typography.Text type="warning">依赖事实已变化，请重新确认</Typography.Text>}{!cell.can_confirm && cell.confirmation_blockers.length > 0 && <Typography.Text type="secondary">{cell.confirmation_blockers.map((reason) => gapLabels[reason] ?? reason).join('、')}</Typography.Text>}{cell.execution_gap && <Typography.Text type="secondary">{executionGapLabel(cell.execution_gap, cell)}</Typography.Text>}<details className="permission-technical-details"><summary>查看版本与实现状态</summary><Typography.Text type="secondary">{cell.expectation === null ? '尚未确认' : `权限版本 ${cell.policy_epoch ?? matrix.policy_epoch}`}{cell.intent_revision !== null && ` · 修订 ${cell.intent_revision}`} · {bindingLabel(cell.status)}</Typography.Text></details></div>
            </div>
          })}
          {action.gaps.length > 0 && <Typography.Paragraph type="secondary" className="permission-requirement-gaps">尚缺：{action.gaps.map((gap) => gapLabels[gap] ?? gap).join('、')}</Typography.Paragraph>}
        </article>)}
      </div>
    </section>

    {proposals.length > 0 && <section className="permission-check-section" aria-labelledby="permission-proposals-title">
      <div className="permission-check-heading"><div><Typography.Title level={3} id="permission-proposals-title">Agent 建议等待确认</Typography.Title><Typography.Paragraph type="secondary">Agent 只能提出建议；权限语义和实现映射仍由你确认。</Typography.Paragraph></div></div>
      <div className="permission-proposal-list">{proposals.map((proposal) => <article className="permission-proposal-card" key={proposal.proposal_id}>
        <Typography.Text strong>{proposal.kind === 'SEMANTIC_CHANGE' ? '权限语义建议' : '实现映射建议'}</Typography.Text>
        <Descriptions size="small" column={1}>
          <Descriptions.Item label="当前值">{proposalCurrentValue(proposal, matrix)}</Descriptions.Item>
          <Descriptions.Item label="Agent 建议">{proposalSuggestedValue(proposal)}</Descriptions.Item>
          <Descriptions.Item label="原因">{proposal.reason}</Descriptions.Item>
        </Descriptions>
        <Space><Button disabled={proposal.status !== 'PENDING' || Boolean(savingProposalId)} loading={savingProposalId === proposal.proposal_id && proposal.status === 'PENDING'} onClick={() => void decideProposal(proposal, 'approve')}>批准</Button><Button danger disabled={proposal.status !== 'PENDING' || Boolean(savingProposalId)} loading={savingProposalId === proposal.proposal_id && proposal.status === 'PENDING'} onClick={() => void decideProposal(proposal, 'reject')}>拒绝</Button></Space>
      </article>)}</div>
    </section>}</>}

    {mode === 'validation' && <><section className="permission-check-section" aria-labelledby="check-preparation-title">
      <div className="permission-check-heading"><div><Typography.Title level={3} id="check-preparation-title">准备检查条件</Typography.Title><Typography.Paragraph type="secondary">界鉴会把已确认权限要求与业务流程、测试账号、观察和恢复方式整理成一次受控检查。</Typography.Paragraph></div></div>
      {requiresCompile && <Alert type="warning" showIcon message="权限要求已经更新，旧检查预览已失效" description="请重新准备检查。只有重新生成配置并读取新的检查预览后，才能开始检查。" />}
      {!requiresCompile && preparedNow && <Alert type="success" showIcon message="检查条件已经重新确认" description={`当前有 ${preview?.actions.filter((action) => action.ready).length ?? 0} 个业务动作可以检查；${matrix?.representative_gap_count ?? 0} 项权限规则暂缺测试条件。`} />}
      {!requiresCompile && !preparedNow && previewFresh && preview?.ready && <Alert type="success" showIcon message="当前检查条件已经准备好" description="下面的预览来自后端当前权威事实，可以继续核对本次检查范围。" />}
      {!requiresCompile && !preparedNow && (!previewFresh || !preview?.ready) && <Alert type="info" showIcon message={matrix?.compilable_action_count ? '权限规则可以生成检查条件' : '还需要确认允许和拒绝'} description={matrix?.compilable_action_count ? '点击页面底部“准备本次检查”后，界鉴会重新生成配置并读取最新预览。' : '至少完成一个业务动作的允许/拒绝对照后才能准备检查。'} />}
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
        <div className="check-scenario-grid" aria-label="真实检查范围">
          <article className="check-scenario-card is-allow"><Typography.Text className="check-scenario-kicker">合法对照</Typography.Text><Typography.Title level={4}>确认应当成功的正常路径</Typography.Title>{allowChecks.length > 0 ? <ul>{allowChecks.map((item, index) => <li key={`allow-${item.action}-${item.subject_label}-${index}`}><strong>{item.subject_label}</strong> 应能完成“{item.action}”</li>)}</ul> : <Typography.Text type="secondary">尚未形成可执行的允许对照。</Typography.Text>}</article>
          <article className="check-scenario-card is-deny"><Typography.Text className="check-scenario-kicker">禁止实验</Typography.Text><Typography.Title level={4}>尝试不应被允许的真实操作</Typography.Title>{denyChecks.length > 0 ? <ul>{denyChecks.map((item, index) => <li key={`deny-${item.action}-${item.subject_label}-${index}`}><strong>{item.subject_label}</strong> 不应完成“{item.action}”</li>)}</ul> : <Typography.Text type="secondary">尚未形成可执行的拒绝实验。</Typography.Text>}</article>
          <article className="check-scenario-card is-effect"><Typography.Text className="check-scenario-kicker">真实业务后果</Typography.Text><Typography.Title level={4}>最终观察资源是否真的改变</Typography.Title>{protectedEffects.length > 0 ? <ul>{protectedEffects.map((effect) => <li key={effect}>{effect}</li>)}</ul> : <Typography.Text type="secondary">尚未确认要独立观察的受保护业务后果。</Typography.Text>}</article>
        </div>
        <div className="check-preview-actions">
          {preview.actions.map((action) => <article className="check-preview-action" key={action.action_candidate_id}>
            <div className="check-preview-action-title"><div><Typography.Title level={4}>{action.action_display_name}</Typography.Title>{action.resource_logical_name && <Typography.Text type="secondary">测试资源：{action.resource_logical_name}</Typography.Text>}</div><Tag color={action.ready ? 'success' : 'warning'}>{action.ready ? '纳入本次检查' : '暂未覆盖'}</Tag></div>
            {action.gaps.length > 0 && <Alert type="warning" showIcon message="这个动作暂未覆盖" description={action.gaps.map((gap) => gap.message).join('；')} />}
            <List className="check-preview-list" dataSource={action.checks} locale={{ emptyText: '尚无账号检查项' }} renderItem={(item) => <List.Item extra={<Tag color={item.expectation === 'ALLOW' ? 'green' : item.expectation === 'DENY' ? 'red' : 'default'}>{item.expectation === 'ALLOW' ? '应该允许' : item.expectation === 'DENY' ? '应该拒绝' : '尚未确认'}</Tag>}><List.Item.Meta title={item.subject_label} description={`${item.subject_role_display_name} · ${relationLabels[item.relation] ?? '当前资源关系'}${item.gaps.length ? ` · ${item.gaps.map((gap) => gap.message).join('、')}` : ''}`} /></List.Item>} />
          </article>)}
        </div>
        {preview.ready && <Alert type="success" showIcon message={`将执行 ${preview.case_count} 个检查用例，形成 ${preview.differential_pair_count} 组允许/拒绝对照${uncoveredActionCount > 0 ? `；另有 ${uncoveredActionCount} 个动作暂未覆盖` : ''}。`} description="开始后只根据正式运行事实形成结论；页面不会把 HTTP 拒绝或事件流状态当作安全结果。" />}
        {!preview.ready && preview.gaps.length > 0 && <Alert type="warning" showIcon message="当前还不能开始检查" description={preview.gaps.map((gap) => gap.message).join('；')} />}
      </>}
    </section>

    <AssistantPanel projectId={project.project_id} surface={assistantPanel.surface} title={assistantPanel.title} actionLabel={assistantPanel.actionLabel} />

    <section className="permission-check-section" aria-labelledby="current-check-title">
      <div className="permission-check-heading"><div><Typography.Title level={3} id="current-check-title">开始检查并查看进度</Typography.Title><Typography.Paragraph type="secondary">开始后，界鉴会先验证正常允许的操作，再尝试不应允许的操作，并通过可信观察确认真实资源结果和恢复测试数据。</Typography.Paragraph></div>{latest?.run_id && <Tag>{lifecycleLabel(latest.lifecycle)}</Tag>}</div>
      {!latest && <Typography.Text type="secondary">准备和预览完成后，可从页面底部开始本次检查。</Typography.Text>}
      {latest && <CheckProgress run={latest} actions={preview?.actions} onRefresh={refreshRun} onError={onError} onNavigate={onNavigate} />}
      {canViewResult && !needsNewRun && <Alert type="success" showIcon message="本次检查已经完成" description="可信结果已经发布，可以继续查看检查结果和证据。" />}
    </section></>}

    <TaskActionBar
      back={{ label: mode === 'permissions' ? '返回变化与待办' : '返回测试准备', onClick: onBack }}
      refresh={{ label: '刷新当前状态', onClick: () => void refreshFacts(), loading: refreshing }}
      restart={mode === 'validation' ? restart : undefined}
      primary={mode === 'permissions'
        ? savingCell
          ? { label: '正在保存权限要求', ariaLabel: '正在保存权限要求', disabled: true, loading: true }
          : matrix && matrix.required_confirmation_count > 0
            ? { label: `还有 ${matrix.required_confirmation_count} 项权限规则需要确认`, disabled: true }
            : { label: '继续准备', onClick: onContinuePreparation }
        : primary}
    />
    <Modal open={Boolean(pendingChange)} title="确认权限变更" okText="确认权限变更" cancelText="暂不变更" confirmLoading={Boolean(savingCell)} onOk={() => void approveChange()} onCancel={() => { if (!savingCell) { setPendingChange(null); setPendingDraftOptionId(undefined) } }}>
      {pendingChange && <Space direction="vertical" size="small">
        <Typography.Text>当前要求：{expectationLabel(pendingChange.cell.expectation)}</Typography.Text>
        <Typography.Text>准备变成：{expectationLabel(pendingChange.expectation)}</Typography.Text>
        <div><Typography.Text strong>受保护业务后果：</Typography.Text><ul>{(pendingChange.cell.protected_effects ?? []).map((effect, index) => <li key={`${effect.business_label}-${index}`}>{effect.business_label || effect.resource_type}</li>)}</ul></div>
        {pendingChange.cell.expectation !== pendingChange.expectation && <Typography.Text>确认后将从版本 {matrix?.policy_epoch ?? 0} 推进到 { (matrix?.policy_epoch ?? 0) + 1 }</Typography.Text>}
        {pendingChange.cell.status === 'NEEDS_REVIEW' && pendingChange.cell.expectation === pendingChange.expectation && <Typography.Text>权限语义不变，不推进版本；仅重新确认当前实现映射</Typography.Text>}
      </Space>}
    </Modal>
  </div>
}

type PendingPermissionChange = { actionId: string; cell: PermissionIntentCellDto; expectation: PermissionIntentExpectation | null }

function permissionCellKey(actionId: string, cell: PermissionIntentCellDto) {
  return `${actionId}:${cell.subject_role_candidate_id}:${cell.resource_owner_role_candidate_id}:${cell.relation}`
}

function findDraftCell(suggestion: PermissionDraftSuggestionDto, matrix: PermissionIntentMatrixDto | null) {
  return matrix?.actions
    .find((action) => action.action_candidate_id === suggestion.action_candidate_id)
    ?.cells.find((cell) => (
      cell.subject_role_candidate_id === suggestion.subject_role_candidate_id
      && cell.resource_owner_role_candidate_id === suggestion.resource_owner_role_candidate_id
      && cell.relation === suggestion.relation
    ))
}

function expectationLabel(value: PermissionIntentExpectation | null) {
  return value === 'ALLOW' ? '允许' : value === 'DENY' ? '拒绝' : '未确认'
}

function bindingLabel(status: PermissionIntentCellDto['status']) {
  return ({ CURRENT: '实现映射可用', NEEDS_REVIEW: '实现映射待复核', UNRESOLVED: '实现映射未解决', UNCONFIRMED: '尚未确认' } as const)[status]
}

function hasObservationGap(matrix: PermissionIntentMatrixDto | null, preview: CheckPreviewDto | null) {
  const gapCodes = [
    ...(matrix?.actions.flatMap((action) => action.gaps) ?? []),
    ...(preview?.gaps.map((gap) => gap.code) ?? []),
    ...(preview?.actions.flatMap((action) => action.gaps.map((gap) => gap.code)) ?? []),
  ]
  return gapCodes.some((gap) => ['OBSERVATION_UNCONFIRMED', 'RECOVERY_UNCONFIRMED', 'ACTION_SAFETY_SETUP_STALE', 'SECURITY_EFFECT_UNCONFIRMED'].includes(gap))
}

function findProposalCell(proposal: PermissionIntentProposalDto, matrix: PermissionIntentMatrixDto | null) {
  if (!matrix || !proposal.intent_id) return undefined
  return matrix.actions.flatMap((action) => action.cells).find((cell) => cell.intent_id === proposal.intent_id)
}

function proposalCurrentValue(proposal: PermissionIntentProposalDto, matrix: PermissionIntentMatrixDto | null) {
  const cell = findProposalCell(proposal, matrix)
  if (proposal.kind === 'IMPLEMENTATION_REBIND') return cell ? bindingLabel(cell.status) : '尚未确认'
  return expectationLabel(cell?.expectation ?? null)
}

function proposalSuggestedValue(proposal: PermissionIntentProposalDto) {
  if (proposal.kind === 'IMPLEMENTATION_REBIND') return '重新确认当前实现映射'
  if (proposal.semantic_change?.effective_state === 'RETIRED') return '退役为未确认'
  return expectationLabel(proposal.semantic_change?.expectation ?? null)
}

const relationLabels: Record<string, string> = {
  OWNS: '自己的资源', SAME_ROLE_OTHER_ACCOUNT: '同权限组其他用户的资源', OTHER_ROLE: '其他权限组的资源',
}
function resourceRelationLabel(cell: PermissionIntentCellDto) {
  if (cell.relation === 'OWNS') return '自己管理'
  if (cell.relation === 'SAME_ROLE_OTHER_ACCOUNT') return `另一位${cell.resource_owner_role_display_name}管理`
  return `${cell.resource_owner_role_display_name}管理`
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
