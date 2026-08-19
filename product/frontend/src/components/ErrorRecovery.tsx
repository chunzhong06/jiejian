// 统一呈现可恢复错误与诊断详情；默认视图不暴露未经整理的内部异常。

import { Alert, Button, Collapse, Space, Typography } from 'antd'
import { ApiError } from '../api/http'

function reasonFor(code: string) {
  if (code === 'ONBOARDING_SESSION_CONFLICT') return ['会话内容已在其他页面更新。', '请刷新恢复最新答案，再继续当前步骤。']
  if (/TARGET|ADDRESS|URL|LOOPBACK|SCOPE|AUTH/i.test(code)) return ['目标地址或授权范围不符合当前检查边界。', '返回对应输入步骤，重新确认地址和授权范围。']
  if (/SECRET|CREDENTIAL|PASSWORD/i.test(code)) return ['测试凭据未配置或已被清理。', '返回接入，重新输入两份测试凭据。']
  return ['当前信息不足，需要重新确认输入或服务状态。', '刷新状态后重试；仍失败时返回接入重新确认。']
}

export function ErrorRecovery({ error, onRetry, onBackAccess, onClose }: { error: ApiError; onRetry: () => void; onBackAccess: () => void; onClose?: () => void }) {
  const [reason, action] = reasonFor(error.code)
  return <Alert
    className="error-recovery"
    type="error"
    showIcon
    closable={Boolean(onClose)}
    onClose={onClose}
    message="这一步没有完成"
    description={<Space direction="vertical" size="small" style={{ width: '100%' }}>
      <div><Typography.Text strong>发生了什么：</Typography.Text> {error.message}</div>
      <div><Typography.Text strong>可能原因：</Typography.Text> {reason}</div>
      <div><Typography.Text strong>现在怎么做：</Typography.Text> {action}</div>
      <Space wrap><Button size="small" onClick={onRetry}>刷新状态并重试</Button><Button size="small" onClick={onBackAccess}>返回接入</Button></Space>
      <Collapse ghost items={[{ key: 'diagnostic', label: '诊断信息', children: <Space direction="vertical"><Typography.Text code>错误码：{error.code}</Typography.Text>{error.traceId && <Typography.Text code>trace_id：{error.traceId}</Typography.Text>}</Space> }]} />
    </Space>}
  />
}
