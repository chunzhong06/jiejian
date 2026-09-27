// 任务局部动作区：加载状态与可访问名称分开，返回和刷新不冒充新的业务提交。

import { Button, Popconfirm, Space } from 'antd'

type TaskAction = {
  label: string
  ariaLabel?: string
  onClick?: () => void
  submitForm?: string
  danger?: boolean
  confirm?: {
    title: string
    description: string
    okText?: string
    cancelText?: string
  }
  disabled?: boolean
  loading?: boolean
}

export function TaskActionBar({
  back,
  refresh,
  restart,
  primary,
}: {
  back?: TaskAction
  refresh?: TaskAction
  restart?: TaskAction
  primary?: TaskAction
}) {
  if (!back && !refresh && !restart && !primary) return null
  return <footer className="task-action-bar" aria-label="当前步骤操作">
    <Space className="task-action-group" size={8} wrap>
      {back && <Button aria-label={back.ariaLabel ?? back.label} aria-busy={Boolean(back.loading)} onClick={back.onClick} disabled={back.disabled} loading={back.loading}>{back.label}</Button>}
      {refresh && <Button aria-label={refresh.ariaLabel ?? refresh.label} aria-busy={Boolean(refresh.loading)} onClick={refresh.onClick} disabled={refresh.disabled} loading={refresh.loading}>{refresh.label}</Button>}
      {restart && (restart.confirm
        ? <Popconfirm title={restart.confirm.title} description={restart.confirm.description} okText={restart.confirm.okText} cancelText={restart.confirm.cancelText} onConfirm={restart.onClick}><Button danger={restart.danger} disabled={restart.disabled} loading={restart.loading}>{restart.label}</Button></Popconfirm>
        : <Button danger={restart.danger} onClick={restart.onClick} disabled={restart.disabled} loading={restart.loading}>{restart.label}</Button>)}
      {primary && <Button type="primary" aria-label={primary.ariaLabel ?? primary.label} aria-busy={Boolean(primary.loading)} htmlType={primary.submitForm ? 'submit' : 'button'} form={primary.submitForm} onClick={primary.onClick} disabled={primary.disabled} loading={primary.loading}>{primary.label}</Button>}
    </Space>
  </footer>
}
