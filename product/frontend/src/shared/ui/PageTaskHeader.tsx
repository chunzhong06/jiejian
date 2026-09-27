// 产品页面统一展示任务标题、短说明和状态；操作统一放在页面底部。

import { Typography } from 'antd'

export function PageTaskHeader({
  title,
  description,
  status,
}: {
  title: string
  description: string
  status?: string
}) {
  return <section className="page-task-header" aria-labelledby={`page-title-${title}`}>
    <div className="page-task-header-main">
      <div>
        <Typography.Title id={`page-title-${title}`} level={2}>{title}</Typography.Title>
        <Typography.Paragraph type="secondary">{description}</Typography.Paragraph>
      </div>
      {status && <span className="page-task-status"><i aria-hidden="true" />{status}</span>}
    </div>
  </section>
}
