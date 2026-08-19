// 产品页面统一任务标题、状态和主操作布局。

import { Button, Space, Tag, Typography } from 'antd'

export function PageTaskHeader({
  title,
  description,
  status,
  next,
  actionLabel,
  onAction,
  disabled,
}: {
  title: string
  description: string
  status?: string
  next?: string
  actionLabel?: string
  onAction?: () => void
  disabled?: boolean
}) {
  return <section className="page-task-header" aria-labelledby={`page-title-${title}`}>
    <div className="page-task-header-main">
      <div>
        <Typography.Title id={`page-title-${title}`} level={2}>{title}</Typography.Title>
        <Typography.Paragraph type="secondary">{description}</Typography.Paragraph>
      </div>
      {status && <Tag color="blue">{status}</Tag>}
    </div>
    {(next || onAction) && <Space className="page-task-header-next" wrap>
      {next && <Typography.Text type="secondary">下一步：{next}</Typography.Text>}
      {onAction && actionLabel && <Button type="primary" onClick={onAction} disabled={disabled}>{actionLabel}</Button>}
    </Space>}
  </section>
}
