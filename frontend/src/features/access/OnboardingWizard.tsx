/* 首次使用向导：组织目录识别、普通信息补充和快速任务提交，不执行候选命令。 */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Checkbox, Collapse, Descriptions, Form, Input, List, Progress, Space, Steps, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { DiscoveryResult, OnboardingSession, onboardingApi, QuickCheckResult } from '../../api/onboarding'

const SESSION_KEY = 'jiejian.onboarding.session'

type Submitted = Pick<QuickCheckResult, 'project_id' | 'run_id' | 'job_id'> & { demo_data?: boolean }
type Confirmations = OnboardingSession['confirmations']

const emptyConfirmations: Confirmations = {
  app_started: false,
  target_authorized: false,
  recovery_confirmed: false,
  dangerous_inference_confirmed: false,
}

function projectNameFromPath(path: string) {
  const clean = path.replace(/[\\/]+$/, '')
  return clean.split(/[\\/]/).pop() || '我的应用'
}

function ordinaryError(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback
}

export function OnboardingWizard({ onSubmitted }: { onSubmitted?: (result: Submitted) => void }) {
  const [session, setSession] = useState<OnboardingSession | null>(null)
  const [discovery, setDiscovery] = useState<DiscoveryResult | null>(null)
  const [path, setPath] = useState('')
  const [manualPath, setManualPath] = useState('')
  const [projectName, setProjectName] = useState('')
  const [step, setStep] = useState(0)
  const [loading, setLoading] = useState(false)
  const [chooserMessage, setChooserMessage] = useState('')
  const [error, setError] = useState('')
  const [selectedCandidateSource, setSelectedCandidateSource] = useState('')
  const [targetAddress, setTargetAddress] = useState('')
  const [primaryName, setPrimaryName] = useState('')
  const [comparisonName, setComparisonName] = useState('')
  const [primaryResource, setPrimaryResource] = useState('')
  const [comparisonResource, setComparisonResource] = useState('')
  const [primaryPassword, setPrimaryPassword] = useState('')
  const [comparisonPassword, setComparisonPassword] = useState('')
  const [readPath, setReadPath] = useState('/resources/{resource_id}')
  const [recoveryPath, setRecoveryPath] = useState('/reset')
  const [confirmations, setConfirmations] = useState<Confirmations>(emptyConfirmations)
  const [demo, setDemo] = useState<Awaited<ReturnType<typeof onboardingApi.demoStatus>> | null>(null)

  const applySession = (next: OnboardingSession) => {
    setSession(next)
    if (next.status === 'SUBMITTED') {
      setStep(3)
    } else if (!next.confirmations.app_started) {
      setStep(0)
    } else if (!next.target_address || !next.confirmations.target_authorized) {
      setStep(1)
    } else if (!next.primary_display_name || !next.comparison_display_name || !next.primary_resource_id || !next.comparison_resource_id || !next.primary_configured || !next.comparison_configured) {
      setStep(2)
    } else {
      setStep(3)
    }
    setProjectName(next.project_name)
    setTargetAddress(next.target_address ?? '')
    setPrimaryName(next.primary_display_name ?? '')
    setComparisonName(next.comparison_display_name ?? '')
    setPrimaryResource(next.primary_resource_id ?? '')
    setComparisonResource(next.comparison_resource_id ?? '')
    setReadPath(next.read_only_path_template ?? '/resources/{resource_id}')
    setRecoveryPath(next.recovery_path ?? '/reset')
    setConfirmations(next.confirmations)
    setSelectedCandidateSource(next.startup_candidate_source ?? '')
  }

  const inspectRestoredPath = async (sourcePath: string) => {
    try {
      setDiscovery(await onboardingApi.inspect(sourcePath))
      setChooserMessage('已重新识别应用文件夹。')
    } catch {
      setChooserMessage('暂时无法重新识别应用文件夹；会话答案仍已保留，请稍后重试。')
    }
  }

  useEffect(() => {
    const sessionId = localStorage.getItem(SESSION_KEY)
    if (sessionId) {
      setLoading(true)
      void onboardingApi.getSession(sessionId).then((next) => {
        applySession(next)
        setPath(next.source_path)
        void inspectRestoredPath(next.source_path)
      }).catch(() => {
        localStorage.removeItem(SESSION_KEY)
        setError('之前的新手会话已失效，请重新选择应用文件夹。')
      }).finally(() => setLoading(false))
    }
    void onboardingApi.demoStatus().then(setDemo).catch(() => undefined)
  }, [])

  const update = async (patch: Parameters<typeof onboardingApi.updateSession>[2]) => {
    if (!session || session.status === 'SUBMITTED') return null
    const next = await onboardingApi.updateSession(session.session_id, session.revision, {
      ...patch,
      confirmations: { ...session.confirmations, ...patch.confirmations },
    })
    applySession(next)
    return next
  }

  const inspectAndCreate = async (selectedPath: string) => {
    setLoading(true)
    setError('')
    setChooserMessage('')
    try {
      const result = await onboardingApi.inspect(selectedPath)
      setDiscovery(result)
      const created = await onboardingApi.createSession(selectedPath, projectNameFromPath(selectedPath))
      localStorage.setItem(SESSION_KEY, created.session_id)
      applySession(created)
      setPath(selectedPath)
      setStep(0)
    } catch (e) {
      setError(`识别应用文件夹失败：${ordinaryError(e, '请确认路径存在且可读取。')}`)
    } finally {
      setLoading(false)
    }
  }

  const chooseFolder = async () => {
    setLoading(true)
    setError('')
    try {
      const result = await onboardingApi.selectFolder()
      if (result.status === 'cancelled') {
        setChooserMessage('已取消选择。你也可以在下方输入应用文件夹的绝对路径。')
      } else if (result.status === 'unavailable') {
        setChooserMessage(result.message ?? '目录选择器暂时不可用，请输入应用文件夹的绝对路径。')
      } else if (result.path) {
        await inspectAndCreate(result.path)
      }
    } catch (e) {
      setError(`打开目录选择器失败：${ordinaryError(e, '请改用手工绝对路径。')}`)
    } finally {
      setLoading(false)
    }
  }

  const submitManualPath = async () => {
    if (!manualPath.trim()) {
      setChooserMessage('请输入应用文件夹的绝对路径。')
      return
    }
    await inspectAndCreate(manualPath.trim())
  }

  const copyCandidate = async (command: string) => {
    try {
      await navigator.clipboard?.writeText(command)
      setChooserMessage('已复制候选命令。界鉴不会执行它，请由你自行启动应用。')
    } catch {
      setChooserMessage('无法自动复制，请手动选择命令文本；界鉴不会执行它。')
    }
  }

  const startDemo = async () => {
    setLoading(true)
    setError('')
    try {
      const result = await onboardingApi.demoStart()
      setDemo(result)
      if (result.project_id && result.run_id && result.job_id) onSubmitted?.({ project_id: result.project_id, run_id: result.run_id, job_id: result.job_id, demo_data: true })
    } catch (e) {
      setError(`启动内置演示失败：${ordinaryError(e, '请稍后重试，并查看可展开的诊断信息。')}`)
    } finally {
      setLoading(false)
    }
  }

  const stopDemo = async () => {
    setLoading(true)
    try {
      setDemo(await onboardingApi.demoStop())
    } catch (e) {
      setError(`停止内置演示失败：${ordinaryError(e, '请稍后重试。')}`)
    } finally {
      setLoading(false)
    }
  }

  const goNext = async () => {
    if (!session) return
    setLoading(true)
    setError('')
    try {
      if (step === 0) {
        if (!confirmations.app_started) {
          setError('请先确认应用已经在本机运行；界鉴不会替你启动候选命令。')
          return
        }
        await update({ project_name: projectName.trim() || session.project_name, startup_candidate_source: selectedCandidateSource || 'manual:user-started', confirmations: { ...confirmations, app_started: true } })
      } else if (step === 1) {
        if (!/^https?:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/.test(targetAddress)) {
          setError('地址格式不符合快速检查要求：请输入带明确端口的 http/https://127.0.0.1 地址。')
          return
        }
        if (!confirmations.target_authorized) {
          setError('请先确认只访问这个 127.0.0.1 回环地址。')
          return
        }
        await update({ target_address: targetAddress, confirmations: { ...confirmations, target_authorized: true } })
      } else if (step === 2) {
        if (!primaryName.trim() || !comparisonName.trim() || !primaryResource.trim() || !comparisonResource.trim()) {
          setError('请填写两个账号的显示名和各自拥有的资源标识。')
          return
        }
        if ((!primaryPassword && !comparisonPassword) && (!session.primary_configured || !session.comparison_configured)) {
          setError('请输入两个测试账号的密码；密码只提交到当前会话，不会保存到浏览器。')
          return
        }
        if (Boolean(primaryPassword) !== Boolean(comparisonPassword)) {
          setError('如需更新密码，请同时填写两个测试账号的密码。')
          return
        }
        const updated = await update({ primary_display_name: primaryName.trim(), comparison_display_name: comparisonName.trim(), primary_resource_id: primaryResource.trim(), comparison_resource_id: comparisonResource.trim(), confirmations: { ...confirmations } })
        if (primaryPassword && comparisonPassword && updated) {
          await onboardingApi.putCredentials(updated.session_id, primaryPassword, comparisonPassword)
          setPrimaryPassword('')
          setComparisonPassword('')
          const refreshed = await onboardingApi.getSession(updated.session_id)
          applySession(refreshed)
        }
      } else if (step === 3) {
        if (!readPath.trim() || !recoveryPath.trim()) {
          setError('请填写只读路径和恢复路径。')
          return
        }
        if (!confirmations.recovery_confirmed || !confirmations.dangerous_inference_confirmed) {
          setError('请确认恢复方式，以及系统将按你确认的归属和路径生成检查。')
          return
        }
        await update({ read_only_path_template: readPath.trim(), recovery_path: recoveryPath.trim(), confirmations: { ...confirmations, recovery_confirmed: true, dangerous_inference_confirmed: true } })
      }
      setStep((current) => Math.min(current + 1, 3))
    } catch (e) {
      setError(`保存这一步失败：${ordinaryError(e, '请检查信息后重试。')}`)
    } finally {
      setLoading(false)
    }
  }

  const quickCheck = async () => {
    if (!session || session.status === 'SUBMITTED') return
    setLoading(true)
    setError('')
    try {
      const latest = await onboardingApi.getSession(session.session_id)
      applySession(latest)
      if (!latest.primary_configured || !latest.comparison_configured) {
        setStep(2)
        setError('还缺少两个测试凭据，请重新输入；刷新后密码不会保留。')
        return
      }
      const result = await onboardingApi.quickCheck(session.session_id)
      if (result.project_id && result.run_id && result.job_id) onSubmitted?.({ project_id: result.project_id, run_id: result.run_id, job_id: result.job_id })
    } catch (e) {
      setError(`开始快速检查失败：${ordinaryError(e, '请检查还缺什么并重试。')}`)
    } finally {
      setLoading(false)
    }
  }

  const missing = session?.missing_items ?? []
  const submitted = session?.status === 'SUBMITTED'
  const candidateItems = discovery?.start_candidates ?? []
  const hintItems = useMemo(() => [
    ...(discovery?.config_hints ?? []),
    ...(discovery?.interface_hints ?? []),
    ...(discovery?.auth_hints ?? []),
  ], [discovery])

  if (!session) {
    return <Card className="onboarding-wizard onboarding-welcome" bordered={false}>
      <Typography.Title level={2}>检查你的应用有没有权限越界</Typography.Title>
      <Typography.Paragraph>先选择应用文件夹，界鉴只读取少量常见配置，不会运行项目或安装依赖。</Typography.Paragraph>
      <Space wrap>
        <Button type="primary" size="large" loading={loading} onClick={() => void chooseFolder()}>选择应用文件夹</Button>
        <Button size="large" loading={loading} disabled={loading} onClick={() => void startDemo()}>试用内置演示</Button>
      </Space>
      <Typography.Paragraph type="secondary" className="onboarding-demo-note">演示数据，不代表真实项目。</Typography.Paragraph>
      <Collapse ghost items={[{ key: 'manual', label: '无法打开目录选择器？', children: <Space.Compact className="onboarding-manual-path"><Input aria-label="应用文件夹绝对路径" value={manualPath} onChange={(event) => setManualPath(event.target.value)} placeholder="输入应用文件夹绝对路径" /><Button type="primary" loading={loading} onClick={() => void submitManualPath()}>识别文件夹</Button></Space.Compact> }]} />
      {chooserMessage && <Alert className="onboarding-inline-alert" type="info" showIcon message={chooserMessage} />}
      {error && <Alert className="onboarding-inline-alert" type="error" showIcon message={error} />}
      {demo && demo.status !== 'stopped' && <Alert className="onboarding-inline-alert" type={demo.status === 'failed' ? 'error' : demo.status === 'running' ? 'success' : 'info'} showIcon message={demo.message} action={demo.status === 'running' ? <Space><Button size="small" onClick={() => { if (demo.project_id && demo.run_id && demo.job_id) onSubmitted?.({ project_id: demo.project_id, run_id: demo.run_id, job_id: demo.job_id, demo_data: true }) }}>继续查看演示</Button><Button size="small" onClick={() => void stopDemo()} loading={loading}>停止演示</Button></Space> : undefined} />}
    </Card>
  }

  return <Card className="onboarding-wizard" bordered={false}>
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div className="onboarding-heading"><Typography.Title level={3}>准备一次快速检查</Typography.Title><Typography.Text type="secondary">只读取少量配置；启动命令由你决定，界鉴不会替你执行。</Typography.Text></div>
      {submitted && <Alert type="success" showIcon message="检查已提交" description="这次新手检查已进入后台，当前会话不能再修改。请到测试阶段查看真实状态。" />}
      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError('')} />}
      {chooserMessage && <Alert type="info" showIcon message={chooserMessage} closable onClose={() => setChooserMessage('')} action={chooserMessage.includes('暂时无法重新识别') ? <Button size="small" onClick={() => void inspectRestoredPath(session.source_path)} loading={loading}>重新识别</Button> : undefined} />}
      <Descriptions size="small" column={{ xs: 1, sm: 2 }} items={[{ key: 'path', label: '应用文件夹', children: path || session.source_path }, { key: 'project', label: '项目名称', children: <Input aria-label="项目名称" value={projectName} disabled={submitted || loading} onChange={(event) => setProjectName(event.target.value)} /> }]} />
      {discovery && <Card size="small" title="识别结果" className="onboarding-discovery">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Text>项目类型：{discovery.detected_types.length ? discovery.detected_types.join('、') : '暂未识别'}</Typography.Text>
          {candidateItems.length > 0 && <List size="small" header="可能的启动方式（只可复制，不会执行）" dataSource={candidateItems} renderItem={(candidate) => <List.Item actions={[<Button key="select" disabled={submitted || loading} type={selectedCandidateSource === candidate.source ? 'primary' : 'link'} onClick={() => setSelectedCandidateSource(candidate.source)}>{selectedCandidateSource === candidate.source ? '已记录来源' : '记录来源'}</Button>, <Button key="copy" disabled={submitted || loading} type="link" onClick={() => void copyCandidate(candidate.command)}>复制</Button>]}><Space direction="vertical" size={0}><Typography.Text>{candidate.label}</Typography.Text><Typography.Text code>{candidate.command}</Typography.Text><Typography.Text type="secondary">{candidate.safety_note}</Typography.Text></Space></List.Item>} />}
          {hintItems.length > 0 && <List size="small" header="配置、API 和认证线索" dataSource={hintItems} renderItem={(hint) => <List.Item><Typography.Text>{hint.detail}（来源：{hint.source}）</Typography.Text></List.Item>} />}
          {discovery.warnings.map((warning) => <Alert key={`${warning.code}-${warning.message}`} type="warning" showIcon message={warning.message} />)}
        </Space>
      </Card>}
      <Steps current={step} responsive items={[{ title: '启动应用' }, { title: '允许访问的地址' }, { title: '两个测试账号' }, { title: '检查与恢复' }]} />
      {step === 0 && <Card title="应用怎样启动" size="small"><Typography.Paragraph>用途：告诉界鉴应用已经由你启动。示例：复制候选命令，在本机自行启动后勾选确认。</Typography.Paragraph><Checkbox disabled={submitted || loading} checked={confirmations.app_started} onChange={(event) => setConfirmations({ ...confirmations, app_started: event.target.checked })}>应用已经在本机运行</Checkbox><Typography.Paragraph type="secondary">安全影响：候选命令只供复制，界鉴不会运行脚本或安装依赖。</Typography.Paragraph></Card>}
      {step === 1 && <Card title="允许访问哪些地址" size="small"><Typography.Paragraph>快速检查只访问明确授权的本机回环地址，不扫描公网。</Typography.Paragraph><Form layout="vertical"><Form.Item label="目标地址" required extra="示例：http://127.0.0.1:8765"><Input aria-label="目标地址" disabled={submitted || loading} value={targetAddress} onChange={(event) => setTargetAddress(event.target.value)} placeholder="http://127.0.0.1:8765" /></Form.Item><Checkbox disabled={submitted || loading} checked={confirmations.target_authorized} onChange={(event) => setConfirmations({ ...confirmations, target_authorized: event.target.checked })}>我已授权界鉴只访问这个回环地址</Checkbox></Form></Card>}
      {step === 2 && <Card title="测试账号有哪些" size="small"><Typography.Paragraph>用途：用两个身份互换资源，检查权限边界。密码只在本次提交时使用，成功后立即清空；刷新后若已配置，可以留空。</Typography.Paragraph><div className="onboarding-form-grid"><Form.Item label="主账号显示名" required><Input aria-label="主账号显示名" disabled={submitted || loading} value={primaryName} onChange={(event) => setPrimaryName(event.target.value)} /></Form.Item><Form.Item label="对照账号显示名" required><Input aria-label="对照账号显示名" disabled={submitted || loading} value={comparisonName} onChange={(event) => setComparisonName(event.target.value)} /></Form.Item><Form.Item label="主账号拥有的资源标识" required><Input aria-label="主账号拥有的资源标识" disabled={submitted || loading} value={primaryResource} onChange={(event) => setPrimaryResource(event.target.value)} placeholder="owner-resource" /></Form.Item><Form.Item label="对照账号拥有的资源标识" required><Input aria-label="对照账号拥有的资源标识" disabled={submitted || loading} value={comparisonResource} onChange={(event) => setComparisonResource(event.target.value)} placeholder="attacker-resource" /></Form.Item><Form.Item label="主账号密码"><Input.Password aria-label="主账号密码" disabled={submitted || loading} autoComplete="new-password" value={primaryPassword} onChange={(event) => setPrimaryPassword(event.target.value)} /></Form.Item><Form.Item label="对照账号密码"><Input.Password aria-label="对照账号密码" disabled={submitted || loading} autoComplete="new-password" value={comparisonPassword} onChange={(event) => setComparisonPassword(event.target.value)} /></Form.Item></div></Card>}
      {step === 3 && <Card title="检查后怎样恢复数据" size="small"><Typography.Paragraph>界鉴会在每个用例后调用恢复接口，避免演示或测试数据互相影响。</Typography.Paragraph><div className="onboarding-form-grid"><Form.Item label="只读路径" required extra="示例：/resources/{resource_id}"><Input aria-label="只读路径" disabled={submitted || loading} value={readPath} onChange={(event) => setReadPath(event.target.value)} /></Form.Item><Form.Item label="恢复路径" required extra="示例：/reset"><Input aria-label="恢复路径" disabled={submitted || loading} value={recoveryPath} onChange={(event) => setRecoveryPath(event.target.value)} /></Form.Item></div><Checkbox disabled={submitted || loading} checked={confirmations.recovery_confirmed} onChange={(event) => setConfirmations({ ...confirmations, recovery_confirmed: event.target.checked })}>我已确认恢复方式</Checkbox><br /><Checkbox disabled={submitted || loading} checked={confirmations.dangerous_inference_confirmed} onChange={(event) => setConfirmations({ ...confirmations, dangerous_inference_confirmed: event.target.checked })}>系统将按我确认的归属和路径生成检查</Checkbox></Card>}
      {missing.length > 0 && <Alert type="warning" showIcon message="还缺什么" description={missing.join('、')} />}
      <Space wrap>
        {step > 0 && <Button onClick={() => setStep((current) => current - 1)} disabled={submitted || loading}>上一步</Button>}
        {step < 3 && <Button type="primary" onClick={() => void goNext()} loading={loading} disabled={submitted}>保存并继续</Button>}
        {step === 3 && <Button type="primary" onClick={() => void quickCheck()} loading={loading} disabled={submitted}>开始快速检查</Button>}
      </Space>
      <Progress percent={Math.round(((step + 1) / 4) * 100)} showInfo={false} />
    </Space>
  </Card>
}
