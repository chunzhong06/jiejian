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
    <EditorialPage label="应用接入任务" width={step === 4 ? undefined : 'form'}>
      <EditorialHeader eyebrow={selected?.name || '接入新的应用'} title={step === 4 ? '核对应用里的角色与动作' : step === 2 ? '连接运行中的应用' : '接入你的应用'}><p className="editorial-muted">{step === 4 ? '先确认应用里有哪些人、可以执行哪些操作。下一步再决定本轮要检查哪些权限。' : step === 2 ? '确认本机运行地址及访问授权，随后继续原来的准备任务。' : '选择源码目录，授权只读分析，得到可供你核对的业务线索。应用可以稍后再启动。'}</p></EditorialHeader>
      <ApplicationSetup selected={selected} endpointStatus={endpointStatus} requestConnection={requestConnection} officialSampleAvailable={officialSampleAvailable} officialSampleBusy={officialSampleBusy} onStartOfficialSample={onStartOfficialSample} onConnected={onConnected} onChanged={onUnderstandingChanged} onBack={onBack} onContinue={onContinue} onStageChanged={setStep} />
    </EditorialPage>
  )
}
