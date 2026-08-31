/* =============================================================================
 * 测试账号页面
 *
 * 定位
 *   已确认应用权限组与业务流程录制之间的普通用户登录状态准备步骤
 *
 * 职责
 *   推荐每个权限组的账号｜解释秘密边界｜显式确认保存｜处理复核、重置和删除
 *
 * 边界
 *   页面不收集密码；登录只发生在独立浏览器，API 只返回非秘密状态
 * ============================================================================= */

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Empty, Input, Modal, Select, Space, Spin, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import type { WorkspaceSnapshot } from '../../app/useProjectWorkspace'
import { projectsApi, type ProjectDto, type RoleCandidateDto } from '../../api/projects'
import {
  testIdentitiesApi,
  type IdentityPreparationDto,
  type TestIdentityDto,
} from '../../api/testIdentities'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { AssistantPanel } from '../../components/AssistantPanel'
import { TaskActionBar } from '../../components/TaskActionBar'
import './identities.css'

function statusTag(identity: TestIdentityDto) {
  if (identity.status === 'PREPARED') return <Tag color="green">登录状态已准备</Tag>
  if (identity.status === 'NEEDS_REVIEW') return <Tag color="orange">需要重新确认</Tag>
  return <Tag>尚未准备登录状态</Tag>
}

function preparationStatus(preparation: IdentityPreparationDto | null) {
  if (!preparation) return '等待选择权限组'
  if (preparation.status === 'WAITING_FOR_LOGIN') return '等待你完成登录'
  if (preparation.status === 'SAVING') return '正在保存登录状态'
  if (preparation.status === 'PREPARED') return '登录状态已准备'
  return preparation.status === 'FAILED' ? '登录准备失败' : preparation.message
}

export function TestIdentityPage({ project, onError, onBack, onStateChanged, onContinuePreparation }: {
  project: ProjectDto
  onError: (error: ApiError) => void
  onBack: () => void
  onStateChanged: () => Promise<WorkspaceSnapshot | undefined>
  onContinuePreparation: () => Promise<void> | void
}) {
  const [roles, setRoles] = useState<RoleCandidateDto[]>([])
  const [identities, setIdentities] = useState<TestIdentityDto[]>([])
  const [selectedRole, setSelectedRole] = useState('')
  const [label, setLabel] = useState('')
  const [preparation, setPreparation] = useState<IdentityPreparationDto | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [syncError, setSyncError] = useState<string>()

  const syncWorkspace = async (savedMessage: string) => {
    const snapshot = await onStateChanged()
    if (snapshot) {
      setSyncError(undefined)
      return true
    }
    setSyncError(`${savedMessage}，但工作区状态刷新失败，请重试“刷新账号状态”。`)
    return false
  }

  const load = async () => {
    const [understanding, accounts] = await Promise.all([
      projectsApi.understanding(project.project_id),
      testIdentitiesApi.list(project.project_id),
    ])
    const confirmed = understanding.role_candidates.filter((item) => item.decision === 'CONFIRMED' && !item.stale)
    setRoles(confirmed)
    setIdentities(accounts)
    setSelectedRole((current) => current || confirmed[0]?.candidate_id || '')
  }

  useEffect(() => {
    let active = true
    setLoading(true)
    void load().catch((error) => { if (active) onError(error as ApiError) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [project.project_id])

  useEffect(() => {
    if (!preparation || ['PREPARED', 'UNSUPPORTED', 'CANCELLED', 'FAILED'].includes(preparation.status)) return
    const timer = window.setTimeout(() => {
      void testIdentitiesApi.preparation(preparation.preparation_id).then(async (next) => {
        setPreparation(next)
        if (next.status === 'PREPARED') {
          await load()
          await syncWorkspace('账号登录状态已保存')
        }
      }).catch((error) => onError(error as ApiError))
    }, 500)
    return () => window.clearTimeout(timer)
  }, [preparation, project.project_id])

  const preparationIdentity = preparation ? identities.find((identity) => identity.identity_id === preparation.identity_id) : undefined
  const preparedCount = identities.filter((identity) => identity.status === 'PREPARED').length
  const canContinue = preparedCount > 0 || preparation?.status === 'PREPARED'

  const refresh = async () => {
    setBusy(true)
    try {
      await load()
      await syncWorkspace('账号状态已刷新')
    }
    catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }

  const createIdentity = async () => {
    if (!selectedRole || !label.trim()) return
    setBusy(true)
    try {
      await testIdentitiesApi.create(project.project_id, selectedRole, label.trim())
      setLabel('')
      await load()
      await syncWorkspace('测试账号已添加')
    } catch (error) { onError(error as ApiError) } finally { setBusy(false) }
  }

  const start = async (identityId: string) => {
    setBusy(true)
    try { setPreparation(await testIdentitiesApi.startPreparation(identityId)) }
    catch (error) { onError(error as ApiError) } finally { setBusy(false) }
  }

  const confirm = async () => {
    if (!preparation) return
    setBusy(true)
    try {
      const next = await testIdentitiesApi.confirmPreparation(preparation.preparation_id)
      setPreparation(next)
      await load()
      await syncWorkspace('账号登录状态已保存')
    }
    catch (error) { onError(error as ApiError) } finally { setBusy(false) }
  }

  const cancel = async () => {
    if (!preparation) return
    setBusy(true)
    try { setPreparation(await testIdentitiesApi.cancelPreparation(preparation.preparation_id)) }
    catch (error) { onError(error as ApiError) } finally { setBusy(false) }
  }

  const reset = (identity: TestIdentityDto) => Modal.confirm({
    title: `清除“${identity.label}”的登录状态？`,
    content: '界鉴会精确删除该测试账号保存的登录状态；账号名称与权限组绑定会保留。',
    okText: '清除登录状态', cancelText: '取消', okButtonProps: { danger: true },
    onOk: async () => {
      try { await testIdentitiesApi.reset(identity.identity_id); await load(); await syncWorkspace('账号登录状态已清除') }
      catch (error) { onError(error as ApiError); throw error }
    },
  })

  const remove = (identity: TestIdentityDto) => Modal.confirm({
    title: `删除测试账号“${identity.label}”？`,
    content: '界鉴会先删除该账号的全部安全登录状态；如果安全存储清理失败，账号信息会保留以便重试。',
    okText: '删除测试账号', cancelText: '取消', okButtonProps: { danger: true },
    onOk: async () => {
      try { await testIdentitiesApi.delete(identity.identity_id); await load(); await syncWorkspace('测试账号已删除') }
      catch (error) { onError(error as ApiError); throw error }
    },
  })

  if (loading) return <Card><Spin /> 正在读取测试账号…</Card>

  return <div className="identity-page">
    <PageTaskHeader title="测试账号" description="为已确认的权限组准备真实测试账号；登录在独立窗口中完成，界鉴不会保存密码。" status={preparation ? preparationStatus(preparation) : `${preparedCount} 个账号已准备`} />
    <Card className="identity-overview" title="准备测试账号">
      <Typography.Paragraph>点击“打开登录浏览器”后，请在独立窗口中自行完成密码、单点登录或多因素认证。只有你明确确认后，界鉴才保存当前应用需要的有限登录状态。</Typography.Paragraph>
      <Alert type="info" showIcon message="建议每个权限组至少准备一个账号" description="缺少账号的权限组不会被自动检查，也不会被当作检查通过；检查同一权限组内不同用户的资源时，可能还需要第二个账号。" />
      {roles.length > 0 && <div className="identity-create">
        <Select aria-label="选择已确认权限组" value={selectedRole} onChange={setSelectedRole} options={roles.map((role) => ({ value: role.candidate_id, label: role.display_name }))} />
        <Input aria-label="测试账号名称" value={label} maxLength={128} onChange={(event) => setLabel(event.target.value)} placeholder="例如：普通用户A / 管理员测试账号" />
        <Button loading={busy} disabled={!selectedRole || !label.trim()} onClick={() => void createIdentity()}>添加测试账号</Button>
      </div>}
    </Card>

    <section className="identity-role-section" aria-labelledby="identity-role-section-title">
      <div className="identity-role-heading"><div><Typography.Title id="identity-role-section-title" level={3}>按权限组准备</Typography.Title><Typography.Paragraph type="secondary">每张角色卡说明它要验证什么、当前使用哪个账号，以及下一步需要你做什么。</Typography.Paragraph></div><Space wrap><Tag>{preparedCount} 个账号已准备</Tag><Button loading={busy} onClick={() => void refresh()}>刷新账号状态</Button></Space></div>
      {roles.length === 0 && <Empty description="请先在应用接入中确认至少一个权限组" />}
      <div className="identity-role-grid">{roles.map((role) => {
        const roleIdentities = identities.filter((identity) => identity.role_candidate_id === role.candidate_id)
        const rolePrepared = roleIdentities.filter((identity) => identity.status === 'PREPARED').length
        return <article className="identity-role-card" key={role.candidate_id}>
          <div className="identity-role-card-header"><div><Typography.Text className="identity-role-kicker">权限组角色</Typography.Text><Typography.Title level={4}>{role.display_name}</Typography.Title></div><Tag color={rolePrepared ? 'green' : 'orange'}>{rolePrepared ? `${rolePrepared} 个已准备` : '需要账号'}</Tag></div>
          <Typography.Paragraph>用于验证“{role.display_name}”在合法路径和禁止路径中的真实权限边界。</Typography.Paragraph>
          <div className="identity-role-accounts">{roleIdentities.length === 0
            ? <Typography.Text type="secondary">当前测试账号：尚未添加。请在上方为这个权限组添加账号。</Typography.Text>
            : roleIdentities.map((identity) => <div className="identity-account-row" key={identity.identity_id}><div><Space wrap><Typography.Text strong>{identity.label}</Typography.Text>{statusTag(identity)}</Space><Typography.Text type="secondary">{identity.status === 'PREPARED' ? '可以用于受控检查' : identity.status === 'NEEDS_REVIEW' ? '需要清除旧状态后重新登录' : '需要在独立浏览器完成登录'}</Typography.Text></div><Space wrap>{identity.status === 'NOT_PREPARED' && <Button loading={busy} onClick={() => void start(identity.identity_id)}>打开登录浏览器</Button>}{identity.status === 'PREPARED' && <Button onClick={() => reset(identity)}>清除登录状态</Button>}{identity.status === 'NEEDS_REVIEW' && <Button onClick={() => reset(identity)}>清除旧状态</Button>}<Button danger onClick={() => remove(identity)}>删除</Button></Space></div>)}</div>
        </article>
      })}</div>
    </section>

    {preparation?.status === 'WAITING_FOR_LOGIN' && <Card className="identity-login-steps" title={`准备“${preparationIdentity?.label ?? '普通用户测试账号'}”`}>
      <ol className="identity-login-step-list">
        <li><Tag color="green">✓</Tag><div><Typography.Text strong>登录窗口已经打开</Typography.Text><Typography.Text type="secondary">界鉴正在等待你完成这个测试账号的登录。</Typography.Text></div></li>
        <li><Tag color="blue">当前</Tag><div><Typography.Text strong>在新窗口完成登录</Typography.Text><Typography.Text type="secondary">正常输入密码，完成 SSO 或 MFA。登录成功后不要关闭这个窗口。</Typography.Text></div></li>
        <li><Tag>3</Tag><div><Typography.Text strong>回到界鉴确认</Typography.Text><Button type="primary" loading={busy} onClick={() => void confirm()}>我已完成登录</Button></div></li>
      </ol>
      <Alert type="warning" showIcon message="不要关闭这个窗口" description="点击确认后，界鉴会安全保存当前应用所需的有限登录状态；不会保存你的密码。" />
      <Button loading={busy} onClick={() => void cancel()}>取消准备</Button>
    </Card>}
    {preparation && preparation.status !== 'WAITING_FOR_LOGIN' && <Alert
      type={preparation.status === 'FAILED' ? 'error' : preparation.status === 'UNSUPPORTED' ? 'warning' : preparation.status === 'PREPARED' ? 'success' : 'info'}
      showIcon
      message={preparation.status === 'SAVING' ? '正在安全保存这个应用所需的登录状态…' : preparation.status === 'PREPARED' ? '登录状态已准备；界鉴没有保存你的密码' : preparation.message}
      action={<Space>
        {preparation.status === 'STARTING' && <Button loading={busy} onClick={() => void cancel()}>取消准备</Button>}
        {['PREPARED', 'UNSUPPORTED', 'CANCELLED', 'FAILED'].includes(preparation.status) && <Button onClick={() => setPreparation(null)}>关闭提示</Button>}
      </Space>}
    />}
    {syncError && <Alert type="warning" showIcon message={syncError} />}

    <AssistantPanel projectId={project.project_id} surface="identity-preparation" title="测试账号准备顺序" actionLabel="AI 帮我安排准备顺序" />
    <TaskActionBar
      back={{ label: '返回应用接入', onClick: onBack }}
      primary={{ label: canContinue ? '继续准备' : '准备至少一个账号后继续', onClick: onContinuePreparation, disabled: !canContinue }}
    />
  </div>
}
