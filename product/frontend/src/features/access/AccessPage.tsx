// 应用接入页：只承载目录连接、地址确认、源码授权和应用内容审阅的正式路径。

import { ApplicationSetup } from './ApplicationSetup'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import type { ProjectDto } from '../../api/applications/projects'
import type { WorkspaceConnectionDto } from '../../api/workspace'
import './access.css'
import { useEffect, useState } from 'react'

export function AccessPage({
  selected,
  endpointStatus,
  requestConnection,
  officialSampleAvailable,
  officialSampleBusy,
  onStartOfficialSample,
  onConnected,
  onUnderstandingChanged,
  onBack,
  onContinue,
}: {
  selected: ProjectDto | null
  endpointStatus?: WorkspaceConnectionDto['endpoint_status']
  requestConnection?: boolean
  officialSampleAvailable?: boolean
  officialSampleBusy?: boolean
  onStartOfficialSample?: () => Promise<boolean>
  onConnected: (project: ProjectDto) => void
  onUnderstandingChanged: () => unknown
  onBack: () => void
  onContinue: () => void
  onProvidedBoundary?: () => void
}) {
  const [step, setStep] = useState(0)
  useEffect(() => setStep(0), [selected?.project_id])
  return (
    <EditorialPage label="应用接入任务" width="form">
      <EditorialHeader eyebrow={selected?.name || '当前应用'} title={step === 4 ? '审阅识别到的业务' : '接入本地应用'}><p className="editorial-muted">{step === 4 ? '先确认谁可以对哪些资源做什么。' : '选择源码目录，先整理业务与权限。需要实际操作时，再连接运行中的应用。'}</p></EditorialHeader>
      <ApplicationSetup selected={selected} endpointStatus={endpointStatus} requestConnection={requestConnection} officialSampleAvailable={officialSampleAvailable} officialSampleBusy={officialSampleBusy} onStartOfficialSample={onStartOfficialSample} onConnected={onConnected} onChanged={onUnderstandingChanged} onBack={onBack} onContinue={onContinue} onStageChanged={setStep} />
    </EditorialPage>
  )
}
