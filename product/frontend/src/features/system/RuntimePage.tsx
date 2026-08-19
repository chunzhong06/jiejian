// 运行环境只读概览；将内部探针投影为用户可理解的服务状态。

import { Card, Col, Row, Statistic, Tag, Typography } from 'antd'
import { LLMProfile } from '../../api/llm'
import { SystemStatus } from '../../api/system'

function label(value: unknown) {
  const raw = String(value ?? 'unknown')
  return raw === 'available' || raw === 'running' ? '可用' : raw === 'stopped' || raw === 'unavailable' ? '不可用' : '未知'
}
export function RuntimePage({ status, profiles, failed }: { status: SystemStatus; profiles: LLMProfile[]; failed: boolean }) {
  const model = failed ? '未知' : profiles.some((profile) => profile.enabled && profile.secret_configured) ? '已配置' : '未知'
  return <Card title="运行环境"><Typography.Paragraph type="secondary">这里显示服务端确认的运行状态；未知状态不会被推断为可用。</Typography.Paragraph><Row gutter={[16, 16]}>
    <Col xs={24} sm={12} lg={6}><Statistic title="服务" value={label(status.api)} /></Col>
    <Col xs={24} sm={12} lg={6}><Statistic title="执行" value={label(status.worker)} /></Col>
    <Col xs={24} sm={12} lg={6}><Statistic title="浏览器" value={label(status.browser)} /></Col>
    <Col xs={24} sm={12} lg={6}><Statistic title="模型" value={model} /></Col>
  </Row><Tag color="blue">状态来自当前运行环境</Tag></Card>
}
