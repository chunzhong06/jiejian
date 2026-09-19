/* =============================================================================
 * 测试账号页面
 *
 * 定位
 *   已确认应用业务主体与业务流程录制之间的普通用户登录状态准备步骤
 *
 * 职责
 *   推荐每个业务主体的账号｜解释秘密边界｜显式确认保存｜处理复核、重置和删除
 *
 * 边界
 *   页面不收集密码；登录只发生在独立浏览器，API 只返回非秘密状态
 * ============================================================================= */

import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Empty, Input, Modal, Select, Space, Spin, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import type { WorkspaceViewDto } from '../../api/workspace'
import type { ProjectDto } from '../../api/projects'
import { businessBoundariesApi, type BusinessActorRevisionDto } from '../../api/businessBoundaries'
import {
  testIdentitiesApi,
  type IdentityPreparationDto,
  type TestIdentityDto,
} from '../../api/testIdentities'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { TaskActionBar } from '../../components/TaskActionBar'
import './identities.css'

function statusTag(identity: TestIdentityDto) {
  if (identity.status === 'PREPARED') return <Tag color="green">登录状态已准备</Tag>
  if (identity.status === 'NEEDS_REVIEW') return <Tag color="orange">需要重新确认</Tag>
  return <Tag>尚未准备登录状态</Tag>
}

function preparationStatus(preparation: IdentityPreparationDto | null) {
  if (!preparation) return '等待选择业务主体'
  if (preparation.status === 'WAITING_FOR_LOGIN') return '等待你完成登录'
  if (preparation.status === 'SAVING') return '正在保存登录状态'
  if (preparation.status === 'PREPARED') return '登录状态已准备'
  return preparation.status === 'FAILED' ? '登录准备失败' : preparation.message
}

export function TestIdentityPage({ project, initialPreparation, onError, onBack, onStateChanged, onContinuePreparation, onPrepared }: {
  project: ProjectDto
  initialPreparation?: IdentityPreparationDto
  onError: (error: ApiError) => void
  onBack: () => void
  onStateChanged: () => Promise<WorkspaceViewDto | undefined>
  onContinuePreparation: () => Promise<void> | void
  onPrepared?: () => void
}) {
  const [roles, setRoles] = useState<BusinessActorRevisionDto[]>([])
  const [identities, setIdentities] = useState<TestIdentityDto[]>([])
  const [selectedRole, setSelectedRole] = useState('')
  const [label, setLabel] = useState('')
  const [preparation, setPreparation] = useState<IdentityPreparationDto | null>(initialPreparation ?? null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [syncError, setSyncError] = useState<string>()

  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const activeLogin = Boolean(preparation && !['PREPARED', 'UNSUPPORTED', 'CANCELLED', 'FAILED'].includes(preparation.status))

  const syncWorkspace = async (savedMessage: string) => {
    if (!alive.current) return false
    const snapshot = await onStateChanged()
    if (!alive.current) return false
    if (snapshot) {
      setSyncError(undefined)
      return true
    }
    setSyncError(`${savedMessage}，但工作区状态刷新失败，请重试“刷新账号状态”。`)
    return false
  }

  const load = async () => {
    const [boundary, accounts] = await Promise.all([
      businessBoundariesApi.current(project.project_id),
      testIdentitiesApi.list(project.project_id),
    ])
    if (!alive.current) return
    const confirmed = boundary.actors.filter((item) => item.effective_state === 'ACTIVE')
    setRoles(confirmed)
    setIdentities(accounts)
    setSelectedRole((current) => confirmed.some((item) => item.actor_id === current) ? current : confirmed[0]?.actor_id || '')
  }

  useEffect(() => {
    let active = true
    setLoading(true)
    void load().catch((error) => { if (active) if (alive.current) onError(error as ApiError) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [project.project_id])

  useEffect(() => {
    if (!preparation || ['PREPARED', 'UNSUPPORTED', 'CANCELLED', 'FAILED'].includes(preparation.status)) return
    let active = true
    const timer = window.setTimeout(() => {
      void testIdentitiesApi.preparation(preparation.preparation_id).then(async (next) => {
        if (!active) return
        setPreparation(next)
        if (next.status === 'PREPARED') {
          onPrepared?.()
          await load()
          await syncWorkspace(next.status === 'PREPARED' ? '账号登录状态已保存' : '登录保存请求已提交')
        }
      }).catch((error) => onError(error as ApiError))
    }, 500)
    return () => { active = false; window.clearTimeout(timer) }
  }, [preparation, project.project_id])

  const preparationIdentity = preparation ? identities.find((identity) => identity.identity_id === preparation.identity_id) : undefined
  const preparedCount = identities.filter((identity) => identity.status === 'PREPARED').length

  const refresh = async () => {
    setBusy(true)
    try {
      await load()
      await syncWorkspace('账号状态已刷新')
    }
    catch (error) { if (alive.current) onError(error as ApiError) }
    finally { if (alive.current) setBusy(false) }
  }

  const createIdentity = async () => {
    if (!selectedRole || !label.trim()) return
    setBusy(true)
    try {
      const actor = roles.find((item) => item.actor_id === selectedRole)
      if (!actor) return
      await testIdentitiesApi.create(project.project_id, actor.actor_id, actor.revision, label.trim())
      setLabel('')
      await load()
      await syncWorkspace('测试账号已添加')
    } catch (error) { if (alive.current) onError(error as ApiError) } finally { if (alive.current) setBusy(false) }
  }

  const start = async (identityId: string) => {
    setBusy(true)
    try { const next = await testIdentitiesApi.startPreparation(identityId); if (!alive.current) return; setPreparation(next); await load(); await syncWorkspace('登录准备已开始') }
    catch (error) { if (alive.current) onError(error as ApiError) } finally { if (alive.current) setBusy(false) }
  }

  const confirm = async () => {
    if (!preparation) return
    setBusy(true)
    try {
      const next = await testIdentitiesApi.confirmPreparation(preparation.preparation_id)
      if (!alive.current) return
      setPreparation(next)
      if (next.status === 'PREPARED') onPrepared?.()
      await load()
      await syncWorkspace(next.status === 'PREPARED' ? '账号登录状态已保存' : '登录保存请求已提交')
    }
    catch (error) { if (alive.current) onError(error as ApiError) } finally { if (alive.current) setBusy(false) }
  }

  const cancel = async () => {
    if (!preparation) return
    setBusy(true)
    try { const next = await testIdentitiesApi.cancelPreparation(preparation.preparation_id); if (!alive.current) return; setPreparation(next); await load(); await syncWorkspace('登录准备已取消') }
    catch (error) { if (alive.current) onError(error as ApiError) } finally { if (alive.current) setBusy(false) }
  }

  const reset = (identity: TestIdentityDto) => Modal.confirm({
    title: `清除“${identity.label}”的登录状态？`,
    content: '界鉴会精确删除该测试账号保存的登录状态；账号名称与业务主体绑定会保留。',
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

  if (loading) return <EditorialPage><Spin /> 正在读取测试账号…</EditorialPage>

  return <EditorialPage label="测试账号登录准备">
    <EditorialHeader eyebrow="验证 · 真实账号" title={initialPreparation ? `准备“${preparationIdentity?.label ?? '当前测试账号'}”的登录状态` : '管理当前测试账号'}><p className="editorial-muted">{preparation ? preparationStatus(preparation) : '只处理当前账号，其他有效准备仍然保留'}</p></EditorialHeader>
    {!initialPreparation && <><section className="identity-overview"><h2>准备测试账号</h2>
      <Typography.Paragraph>点击“打开登录浏览器”后，请在独立窗口中自行完成密码、单点登录或多因素认证。只有你明确确认后，界鉴才保存当前应用需要的有限登录状态。</Typography.Paragraph>
      <Alert type="info" showIcon message="账号数量由当前权限要求决定" description="检查准备页会列出每个业务主体所需的独立账号；在这里管理已创建账号的登录状态。" />
      {roles.length > 0 && <div className="identity-create">
        <Select aria-label="选择已确认业务主体" value={selectedRole} onChange={setSelectedRole} options={roles.map((role) => ({ value: role.actor_id, label: role.display_name }))} />
        <Input aria-label="测试账号名称" value={label} maxLength={128} onChange={(event) => setLabel(event.target.value)} placeholder="例如：普通用户A / 管理员测试账号" />
        <Button loading={busy} disabled={activeLogin || !selectedRole || !label.trim()} onClick={() => void createIdentity()}>添加测试账号</Button>
      </div>}
    </section>

    <section className="identity-role-section" aria-labelledby="identity-role-section-title">
      <div className="identity-role-heading"><div><Typography.Title id="identity-role-section-title" level={3}>按业务主体准备</Typography.Title><Typography.Paragraph type="secondary">各业务主体下只展示已有账号与当前登录状态；失效账号单独处理。</Typography.Paragraph></div><Space wrap><Tag>{preparedCount} 个账号已准备</Tag><Button loading={busy} onClick={() => void refresh()}>刷新账号状态</Button></Space></div>
      {roles.length === 0 && <Empty description="请先在业务边界中确认业务主体" />}
      <div className="identity-role-grid">{roles.map((role) => {
        const roleIdentities = identities.filter((identity) => identity.actor_id === role.actor_id && identity.actor_revision === role.revision)
        const rolePrepared = roleIdentities.filter((identity) => identity.status === 'PREPARED').length
        return <article className="identity-role-row" key={role.actor_id}>
          <div className="identity-role-row-header"><div><Typography.Text className="identity-role-kicker">业务主体角色</Typography.Text><Typography.Title level={4}>{role.display_name}</Typography.Title></div><Tag color={rolePrepared ? 'green' : 'orange'}>{rolePrepared ? `${rolePrepared} 个已准备` : '需要账号'}</Tag></div>
          <Typography.Paragraph>用于验证“{role.display_name}”在合法路径和禁止路径中的真实权限边界。</Typography.Paragraph>
          <div className="identity-role-accounts">{roleIdentities.length === 0
            ? <Typography.Text type="secondary">当前测试账号：尚未添加。请在上方为这个业务主体添加账号。</Typography.Text>
            : roleIdentities.map((identity) => <div className="identity-account-row" key={identity.identity_id}><div><Space wrap><Typography.Text strong>{identity.label}</Typography.Text>{statusTag(identity)}</Space><Typography.Text type="secondary">{identity.status === 'PREPARED' ? '可以用于业务演示' : identity.status === 'NEEDS_REVIEW' ? '需要清除旧状态后重新登录' : '需要在独立浏览器完成登录'}</Typography.Text></div><Space wrap>{identity.status === 'NOT_PREPARED' && <Button loading={busy} disabled={activeLogin} onClick={() => void start(identity.identity_id)}>打开登录浏览器</Button>}{identity.status === 'PREPARED' && <Button onClick={() => reset(identity)}>清除登录状态</Button>}{identity.status === 'NEEDS_REVIEW' && <Button onClick={() => reset(identity)}>清除旧状态</Button>}<Button danger onClick={() => remove(identity)}>删除</Button></Space></div>)}</div>
        </article>
      })}</div>
    </section>

    </>}
    {preparation?.status === 'WAITING_FOR_LOGIN' && <section className="identity-login-steps task-focus"><p className="editorial-eyebrow">当前需要你处理</p><h2>在已打开的浏览器中完成登录</h2>
      <p>测试账号：{preparationIdentity?.label ?? '当前测试账号'}</p><p className="editorial-muted">正常完成密码、单点登录或多因素认证，然后回到这里确认。</p><p>保存完成前，请保持登录窗口打开。</p>
      <Space wrap><Button type="primary" aria-label="我已完成登录" aria-busy={busy} loading={busy} onClick={() => void confirm()}>我已完成登录</Button><Button loading={busy} onClick={() => void cancel()}>取消准备</Button></Space>
      <p className="editorial-muted">只保存当前应用所需的有限登录状态，不保存密码。实际执行身份在检查中核验。</p>
    </section>}
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

    <TaskActionBar
      back={{ label: '返回检查准备', onClick: onBack, disabled: busy || activeLogin }}
      primary={activeLogin ? undefined : { label: '查看下一项准备', onClick: onContinuePreparation, disabled: busy || activeLogin || Boolean(syncError) }}
    />
  </EditorialPage>
}
