// 应用接入页：只承载目录连接、地址确认、源码授权和应用内容审阅的正式路径。

import { ApplicationSetup } from './ApplicationSetup'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import type { ProjectDto, ProjectReadinessDto } from '../../api/projects'
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
  endpointStatus?: ProjectReadinessDto['endpoint_status']
  officialSampleAvailable?: boolean
  officialSampleBusy?: boolean
  onStartOfficialSample?: () => Promise<boolean>
  onConnected: (project: ProjectDto) => void
  onUnderstandingChanged: () => void
  onBack: () => void
  onContinue: () => void
}) {
  return (
    <div className="task-page">
      <PageTaskHeader title="应用接入" description="选择本地应用，确认访问地址，再审阅界鉴发现的权限组与关键业务动作。" status={selected ? '正在准备当前应用' : '等待选择应用'} />
      <ApplicationSetup selected={selected} endpointStatus={endpointStatus} officialSampleAvailable={officialSampleAvailable} officialSampleBusy={officialSampleBusy} onStartOfficialSample={onStartOfficialSample} onConnected={onConnected} onChanged={onUnderstandingChanged} onBack={onBack} onContinue={onContinue} />
    </div>
  )
}
