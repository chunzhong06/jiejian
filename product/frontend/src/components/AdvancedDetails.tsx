// 高级详情容器：统一收纳内部标识、诊断与专业配置，避免挤占普通任务主线。

import { Collapse } from 'antd'
import type { ReactNode } from 'react'

export function AdvancedDetails({ children, label = '高级详情' }: { children: ReactNode; label?: string }) {
  return <Collapse className="advanced-details" items={[{ key: 'details', label, children }]} />
}
