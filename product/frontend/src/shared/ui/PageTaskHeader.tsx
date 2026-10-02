// 旧调用入口复用同一页面页头；加载态与普通任务态不维护第二套标题尺度。

import { EditorialHeader } from './Editorial'
import { StatusBadge } from './StatusBadge'

export function PageTaskHeader({
  title,
  description,
  status,
}: {
  title: string
  description: string
  status?: string
}) {
  return <EditorialHeader title={title} status={status && <StatusBadge kind="lifecycle">{status}</StatusBadge>}>
    <p className="editorial-muted">{description}</p>
  </EditorialHeader>
}
