/* 系统状态
 * 集中读取模型服务与当前运行环境，并在窗口重新获得焦点时刷新。
 * 该 Hook 不参与项目 readiness 或安全结论计算，失败统一降级为未知状态。
 */

import { useCallback, useEffect, useState } from 'react'
import { llmApi, type AIAssistanceSettings, type LLMProfile } from '../api/llm'
import { systemApi, type SystemStatus } from '../api/system'

const unknownStatus: SystemStatus = { api: 'unknown', worker: 'unknown', browser: 'unknown' }

export function useSystemStatus() {
  const [profiles, setProfiles] = useState<LLMProfile[]>([])
  const [profilesFailed, setProfilesFailed] = useState(false)
  const [aiSettings, setAiSettings] = useState<AIAssistanceSettings>({ enabled: false, default_profile_name: null, updated_at_us: 0 })
  const [aiSettingsFailed, setAiSettingsFailed] = useState(false)
  const [status, setStatus] = useState<SystemStatus>(unknownStatus)

  const refresh = useCallback(() => {
    void systemApi.status().then(setStatus).catch(() => setStatus(unknownStatus))
  }, [])

  useEffect(() => {
    void llmApi.profiles()
      .then((next) => { setProfiles(next); setProfilesFailed(false) })
      .catch(() => setProfilesFailed(true))
    void llmApi.settings().then((value) => { setAiSettings(value); setAiSettingsFailed(false) }).catch(() => setAiSettingsFailed(true))
  }, [])
  useEffect(() => {
    refresh()
    const onFocus = () => refresh()
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [refresh])

  return { profiles, setProfiles, profilesFailed, aiSettings, setAiSettings, aiSettingsFailed, status, refresh }
}
