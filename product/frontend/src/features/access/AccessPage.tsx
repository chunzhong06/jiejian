// 应用接入页：只承载目录连接、地址确认、源码授权和应用内容审阅的正式路径。

import { ApplicationSetup } from './ApplicationSetup'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import type { ProjectDto } from '../../api/projects'
import type { WorkspaceConnectionDto } from '../../api/workspace'
import './access.css'

export function AccessPage({
  selected,
  endpointStatus,
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
  officialSampleAvailable?: boolean
  officialSampleBusy?: boolean
  onStartOfficialSample?: () => Promise<boolean>
  onConnected: (project: ProjectDto) => void
  onUnderstandingChanged: () => void
  onBack: () => void
  onContinue: () => void
}) {
  return (
    <EditorialPage label="应用接入任务">
      <EditorialHeader eyebrow="应用接入" title={selected ? '确认应用与业务动作，再建立权限' : '从你的本地应用开始'}><p className="editorial-muted">选择本地应用，确认访问地址，再审阅找到的业务动作。</p></EditorialHeader>
      <ApplicationSetup selected={selected} endpointStatus={endpointStatus} officialSampleAvailable={officialSampleAvailable} officialSampleBusy={officialSampleBusy} onStartOfficialSample={onStartOfficialSample} onConnected={onConnected} onChanged={onUnderstandingChanged} onBack={onBack} onContinue={onContinue} />
    </EditorialPage>
  )
}
