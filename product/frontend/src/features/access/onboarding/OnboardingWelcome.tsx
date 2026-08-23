/* 首次接入欢迎页：只承载受限目录选择与手工路径回退。 */

import { Alert, Button, Card, Collapse, Input, Space, Typography } from 'antd'

export function OnboardingWelcome({ loading, manualPath, chooserMessage, error, onManualPathChange, onChooseFolder, onSubmitManualPath }: {
  loading: boolean
  manualPath: string
  chooserMessage: string
  error: string
  onManualPathChange: (value: string) => void
  onChooseFolder: () => void
  onSubmitManualPath: () => void
}) {
  return <Card className="onboarding-wizard onboarding-welcome" bordered={false}>
    <Typography.Title level={2}>检查你的应用有没有权限越界</Typography.Title>
    <Typography.Paragraph>先选择应用文件夹，界鉴只读取少量常见配置，不会运行项目或安装依赖。</Typography.Paragraph>
    <Button type="primary" size="large" loading={loading} onClick={onChooseFolder}>选择应用文件夹</Button>
    <Collapse ghost items={[{ key: 'manual', label: '无法打开目录选择器？', children: <Space.Compact className="onboarding-manual-path"><Input aria-label="应用文件夹绝对路径" value={manualPath} onChange={(event) => onManualPathChange(event.target.value)} placeholder="输入应用文件夹绝对路径" /><Button type="primary" loading={loading} onClick={onSubmitManualPath}>识别文件夹</Button></Space.Compact> }]} />
    {chooserMessage && <Alert className="onboarding-inline-alert" type="info" showIcon message={chooserMessage} />}
    {error && <Alert className="onboarding-inline-alert" type="error" showIcon message={error} />}
  </Card>
}
