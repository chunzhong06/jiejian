/* 首次接入欢迎页：承载目录入口与三种内置演示选择。 */

import { Alert, Button, Card, Collapse, Input, Space, Typography } from 'antd'
import type { DemoStatus, DemoVariant } from '../../../api/onboarding'

const demoCards: Array<{ variant: DemoVariant; title: string; description: string; outcome: string }> = [
  { variant: 'fixed', title: '安全示例', description: '看看权限正确生效时，界鉴如何形成安全结论。', outcome: '预期：未发现权限越界' },
  { variant: 'vulnerable', title: '权限漏洞示例', description: '接口看起来拒绝了请求，但真实数据仍被修改。', outcome: '预期：发现权限越界' },
  { variant: 'inconclusive', title: '证据不足示例', description: '关键观察不可用时，界鉴为什么不能误判为安全。', outcome: '预期：证据不足，暂时无法下结论' },
]

export function OnboardingWelcome({ loading, manualPath, chooserMessage, error, demo, onManualPathChange, onChooseFolder, onSubmitManualPath, onStartDemo, onStopDemo, onContinueDemo }: {
  loading: boolean
  manualPath: string
  chooserMessage: string
  error: string
  demo: DemoStatus | null
  onManualPathChange: (value: string) => void
  onChooseFolder: () => void
  onSubmitManualPath: () => void
  onStartDemo: (variant: DemoVariant) => void
  onStopDemo: () => void
  onContinueDemo: () => void
}) {
  return <Card className="onboarding-wizard onboarding-welcome" bordered={false}>
    <Typography.Title level={2}>检查你的应用有没有权限越界</Typography.Title>
    <Typography.Paragraph>先选择应用文件夹，界鉴只读取少量常见配置，不会运行项目或安装依赖。</Typography.Paragraph>
    <Button type="primary" size="large" loading={loading} onClick={onChooseFolder}>选择应用文件夹</Button>
    <Typography.Title level={4}>试用内置演示</Typography.Title>
    <div className="onboarding-demo-grid">
      {demoCards.map((card) => <Card key={card.variant} size="small" className="onboarding-demo-card" title={card.title}><Space direction="vertical" className="full-width"><Typography.Paragraph>{card.description}</Typography.Paragraph><Typography.Text type="secondary">{card.outcome}</Typography.Text><Button type="primary" block loading={loading} disabled={loading} onClick={() => onStartDemo(card.variant)}>开始体验</Button></Space></Card>)}
    </div>
    <Typography.Paragraph type="secondary" className="onboarding-demo-note">演示数据，不代表真实项目。</Typography.Paragraph>
    <Collapse ghost items={[{ key: 'manual', label: '无法打开目录选择器？', children: <Space.Compact className="onboarding-manual-path"><Input aria-label="应用文件夹绝对路径" value={manualPath} onChange={(event) => onManualPathChange(event.target.value)} placeholder="输入应用文件夹绝对路径" /><Button type="primary" loading={loading} onClick={onSubmitManualPath}>识别文件夹</Button></Space.Compact> }]} />
    {chooserMessage && <Alert className="onboarding-inline-alert" type="info" showIcon message={chooserMessage} />}
    {error && <Alert className="onboarding-inline-alert" type="error" showIcon message={error} />}
    {demo && demo.status !== 'stopped' && <Alert className="onboarding-inline-alert" type={demo.status === 'failed' ? 'error' : demo.status === 'running' ? 'success' : 'info'} showIcon message={demo.message} action={demo.status === 'running' ? <Space><Button size="small" onClick={onContinueDemo}>继续查看演示</Button><Button size="small" onClick={onStopDemo} loading={loading}>停止演示</Button></Space> : undefined} />}
  </Card>
}
