/* 浏览器恢复状态边界：只保存非秘密的界面定位信息，不承担应用状态管理。 */

import type { ProjectDto } from '../api/projects'
import type { RecordingDto } from '../api/recordings'

const keys = {
  project: 'jiejian.project',
  recording: 'jiejian.resource',
  onboardingSession: 'product.backend.workflows.onboarding.session',
  jobCursor: 'jiejian.cursor',
} as const

function readJson<T>(key: string): T | null {
  try {
    return JSON.parse(localStorage.getItem(key) ?? 'null') as T | null
  } catch {
    localStorage.removeItem(key)
    return null
  }
}

function writeJson(key: string, value: unknown) {
  localStorage.setItem(key, JSON.stringify(value))
}

export const browserState = {
  readProject: () => readJson<ProjectDto>(keys.project),
  writeProject: (project: ProjectDto) => writeJson(keys.project, project),
  clearProject: () => localStorage.removeItem(keys.project),

  readRecording: () => readJson<RecordingDto>(keys.recording),
  writeRecording: (recording: RecordingDto) => writeJson(keys.recording, recording),
  clearRecording: () => localStorage.removeItem(keys.recording),

  readOnboardingSession: () => localStorage.getItem(keys.onboardingSession),
  writeOnboardingSession: (sessionId: string) => localStorage.setItem(keys.onboardingSession, sessionId),
  clearOnboardingSession: () => localStorage.removeItem(keys.onboardingSession),

  readJobCursor: (jobId: string) => {
    const raw = localStorage.getItem(`${keys.jobCursor}.${jobId}`)
    if (raw === null) return 0
    try {
      const parsed = JSON.parse(raw) as unknown
      const value = Number(parsed)
      return Number.isFinite(value) && value >= 0 ? value : 0
    } catch {
      const value = Number(raw)
      return Number.isFinite(value) && value >= 0 ? value : 0
    }
  },
  writeJobCursor: (jobId: string, sequence: number) => localStorage.setItem(`${keys.jobCursor}.${jobId}`, String(sequence)),
}
