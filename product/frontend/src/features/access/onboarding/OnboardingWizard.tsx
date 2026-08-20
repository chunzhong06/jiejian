/* 首次使用向导编排：组织目录识别、普通信息补充和快速任务提交，不执行候选命令。 */

import { useEffect, useState } from 'react'
import { ApiError } from '../../../api/http'
import { DemoVariant, DiscoveryResult, OnboardingSession, onboardingApi, QuickCheckResult } from '../../../api/onboarding'
import { browserState } from '../../../app/browserState'
import { OnboardingSteps, type OnboardingFields } from './OnboardingSteps'
import { OnboardingWelcome } from './OnboardingWelcome'

const FOLDER_SELECTOR_CLIENT_TIMEOUT_MS = 125_000

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

  const applySession = (next: OnboardingSession, position = true) => {
    setSession(next)
    if (position) {
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
    const sessionId = browserState.readOnboardingSession()
    if (sessionId) {
      setLoading(true)
      void onboardingApi.getSession(sessionId).then((next) => {
        applySession(next)
        setPath(next.source_path)
        void inspectRestoredPath(next.source_path)
      }).catch(() => {
        browserState.clearOnboardingSession()
        setError('之前的新手会话已失效，请重新选择应用文件夹。')
      }).finally(() => setLoading(false))
    }
    void onboardingApi.demoStatus().then(setDemo).catch(() => undefined)
  }, [])

  const update = async (patch: Parameters<typeof onboardingApi.updateSession>[2]) => {
    if (!session || session.status === 'SUBMITTED') return null
    const confirmations = {
      app_started: patch.confirmations?.app_started ?? session.confirmations.app_started,
      target_authorized: patch.confirmations?.target_authorized ?? session.confirmations.target_authorized,
      recovery_confirmed: patch.confirmations?.recovery_confirmed ?? session.confirmations.recovery_confirmed,
      dangerous_inference_confirmed: patch.confirmations?.dangerous_inference_confirmed ?? session.confirmations.dangerous_inference_confirmed,
    }
    const next = await onboardingApi.updateSession(session.session_id, session.revision, {
      ...patch,
      confirmations,
    })
    applySession(next, false)
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
      browserState.writeOnboardingSession(created.session_id)
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
    setChooserMessage('系统目录选择器已打开，请在系统窗口中完成选择；如果没有出现在前台，请查看任务栏或按 Alt+Tab。')
    const controller = new AbortController()
    const timeout = globalThis.setTimeout(() => controller.abort(), FOLDER_SELECTOR_CLIENT_TIMEOUT_MS)
    try {
      const result = await onboardingApi.selectFolder(controller.signal)
      if (result.status === 'cancelled') {
        setChooserMessage('已取消选择。你也可以在下方输入应用文件夹的绝对路径。')
      } else if (result.status === 'unavailable') {
        setChooserMessage(result.message ?? '目录选择器暂时不可用，请输入应用文件夹的绝对路径。')
      } else if (result.path) {
        await inspectAndCreate(result.path)
      }
    } catch (e) {
      setError(e instanceof DOMException && e.name === 'AbortError'
        ? '打开目录选择器超时：请重试，或改用手工绝对路径。'
        : `打开目录选择器失败：${ordinaryError(e, '请改用手工绝对路径。')}`)
    } finally {
      globalThis.clearTimeout(timeout)
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

  const startDemo = async (variant: DemoVariant) => {
    setLoading(true)
    setError('')
    try {
      const result = await onboardingApi.demoStart(variant)
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
      const latest = await update({
        read_only_path_template: readPath.trim(),
        recovery_path: recoveryPath.trim(),
        confirmations: {
          ...confirmations,
          recovery_confirmed: true,
          dangerous_inference_confirmed: true,
        },
      })
      if (!latest) return
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
  if (!session) return <OnboardingWelcome loading={loading} manualPath={manualPath} chooserMessage={chooserMessage} error={error} demo={demo} onManualPathChange={setManualPath} onChooseFolder={() => void chooseFolder()} onSubmitManualPath={() => void submitManualPath()} onStartDemo={(variant) => void startDemo(variant)} onStopDemo={() => void stopDemo()} onContinueDemo={() => { if (demo?.project_id && demo.run_id && demo.job_id) onSubmitted?.({ project_id: demo.project_id, run_id: demo.run_id, job_id: demo.job_id, demo_data: true }) }} />

  const fields: OnboardingFields = { targetAddress, primaryName, comparisonName, primaryResource, comparisonResource, primaryPassword, comparisonPassword, readPath, recoveryPath }
  const changeField = <K extends keyof OnboardingFields>(key: K, value: OnboardingFields[K]) => {
    const setters: { [P in keyof OnboardingFields]: (next: OnboardingFields[P]) => void } = {
      targetAddress: setTargetAddress,
      primaryName: setPrimaryName,
      comparisonName: setComparisonName,
      primaryResource: setPrimaryResource,
      comparisonResource: setComparisonResource,
      primaryPassword: setPrimaryPassword,
      comparisonPassword: setComparisonPassword,
      readPath: setReadPath,
      recoveryPath: setRecoveryPath,
    }
    setters[key](value)
  }
  return <OnboardingSteps session={session} discovery={discovery} path={path} projectName={projectName} step={step} loading={loading} error={error} chooserMessage={chooserMessage} selectedCandidateSource={selectedCandidateSource} fields={fields} confirmations={confirmations} missing={missing} submitted={submitted} onProjectNameChange={setProjectName} onFieldChange={changeField} onConfirmationsChange={setConfirmations} onSelectedCandidateSourceChange={setSelectedCandidateSource} onCopyCandidate={(command) => void copyCandidate(command)} onRetryDiscovery={() => void inspectRestoredPath(session.source_path)} onCloseError={() => setError('')} onCloseMessage={() => setChooserMessage('')} onBack={() => setStep((current) => current - 1)} onNext={() => void goNext()} onQuickCheck={() => void quickCheck()} />
}
