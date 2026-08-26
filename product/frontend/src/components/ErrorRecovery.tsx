// 统一呈现服务端确定性诊断与可恢复入口；本地网络异常只使用固定降级文案。

import { Alert, Button, Collapse, Space, Typography } from 'antd'
import { ApiError } from '../api/http'

export function ErrorRecovery({ error, onRetry, onNavigate, onClose }: { error: ApiError; onRetry: () => void; onNavigate: (path: string) => void; onClose?: () => void }) {
  const diagnosis = error.diagnosis
  const headline = diagnosis?.headline ?? '当前信息不足'
  const shortMessage = diagnosis?.short_message ?? '请刷新状态后重试；仍失败时保留错误码并检查运行环境。'
  const route = diagnosis?.route ?? '/settings/system'
  return <Alert
    className="error-recovery"
    type="error"
    showIcon
    closable={Boolean(onClose)}
    onClose={onClose}
    message="这一步没有完成"
    description={<Space direction="vertical" size="small" style={{ width: '100%' }}>
      <div><Typography.Text strong>系统判断：</Typography.Text> {headline}</div>
      <div><Typography.Text strong>发生了什么：</Typography.Text> {error.message}</div>
      <div><Typography.Text strong>现在怎么做：</Typography.Text> {shortMessage}</div>
      {diagnosis?.cleanup_warnings.map((warning) => <div key={warning}><Typography.Text type="warning">附加提示：{warning}</Typography.Text></div>)}
      <Space wrap><Button size="small" onClick={onRetry}>刷新状态并重试</Button><Button size="small" onClick={() => onNavigate(route)}>前往处理页面</Button></Space>
      <Collapse ghost items={[{ key: 'diagnostic', label: '诊断信息', children: <Space direction="vertical"><Typography.Text code>错误码：{error.code}</Typography.Text>{error.traceId && <Typography.Text code>trace_id：{error.traceId}</Typography.Text>}</Space> }]} />
    </Space>}
  />
}
