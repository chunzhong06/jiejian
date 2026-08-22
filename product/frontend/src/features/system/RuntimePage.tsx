// 运行环境概览：展示服务实际采用的解释器、工具链与自动恢复状态。

import { Alert, Card, Col, Descriptions, Row, Statistic, Tag, Typography } from 'antd'
import { LLMProfile } from '../../api/llm'
import { SystemStatus } from '../../api/system'

function label(value: unknown) {
  const raw = String(value ?? 'unknown')
  return raw === 'available' || raw === 'running' ? '可用' : raw === 'stopped' || raw === 'unavailable' ? '不可用' : '未知'
}

export function RuntimePage({ status, profiles, failed }: { status: SystemStatus; profiles: LLMProfile[]; failed: boolean }) {
  const model = failed ? '未知' : profiles.some((profile) => profile.enabled && profile.secret_configured) ? '已配置' : '未知'
  const environment = status.environment
  const python = environment?.python
  const issues = Array.isArray(python?.issues) ? python.issues : []
  return <Card title="运行环境">
    <Typography.Paragraph type="secondary">以下信息来自当前服务进程，用于确认界鉴没有误用用户级 Python 包或另一套工具链。</Typography.Paragraph>
    {python?.user_site_on_sys_path && <Alert type="error" showIcon message="检测到用户级 Python 包来源" description="请退出界鉴并重新运行 start.cmd，让启动器恢复项目环境隔离。" />}
    {issues.length > 0 && <Alert style={{ marginTop: 12 }} type="warning" showIcon message="运行环境存在异常" description={issues.join('；')} />}
    <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
      <Col xs={24} sm={12} lg={6}><Statistic title="服务" value={label(status.api)} /></Col>
      <Col xs={24} sm={12} lg={6}><Statistic title="执行" value={label(status.worker)} /></Col>
      <Col xs={24} sm={12} lg={6}><Statistic title="浏览器" value={label(status.browser)} /></Col>
      <Col xs={24} sm={12} lg={6}><Statistic title="模型" value={model} /></Col>
    </Row>
    <Descriptions style={{ marginTop: 20 }} bordered size="small" column={1}>
      <Descriptions.Item label="Python">{python?.version ?? '未提供'} · {python?.environment_type ?? '来源未知'}</Descriptions.Item>
      <Descriptions.Item label="Python 可执行文件"><Typography.Text copyable>{python?.executable ?? '未提供'}</Typography.Text></Descriptions.Item>
      <Descriptions.Item label="Python 环境目录"><Typography.Text copyable>{python?.prefix ?? '未提供'}</Typography.Text></Descriptions.Item>
      <Descriptions.Item label="用户级包">{python?.user_site_on_sys_path ? '正在使用' : '未使用'}</Descriptions.Item>
      <Descriptions.Item label="Node.js">{environment?.node?.version ?? '未提供'} · <Typography.Text copyable>{environment?.node?.executable ?? '未提供'}</Typography.Text></Descriptions.Item>
      <Descriptions.Item label="pnpm">{environment?.pnpm?.version ?? '未提供'} · <Typography.Text copyable>{environment?.pnpm?.executable ?? '未提供'}</Typography.Text></Descriptions.Item>
      <Descriptions.Item label="Playwright">{environment?.playwright?.package_version ?? '未提供'} · <Typography.Text copyable>{environment?.playwright?.chromium_executable ?? '未提供'}</Typography.Text></Descriptions.Item>
      <Descriptions.Item label="前端依赖">{environment?.frontend_dependencies ?? '未确认'}</Descriptions.Item>
      <Descriptions.Item label="本次自动恢复任务">{status.recovered_jobs ?? 0}</Descriptions.Item>
    </Descriptions>
    <Tag style={{ marginTop: 16 }} color={python?.ok === false ? 'red' : 'blue'}>{python?.ok === false ? '环境需要处理' : '状态来自当前运行环境'}</Tag>
  </Card>
}
