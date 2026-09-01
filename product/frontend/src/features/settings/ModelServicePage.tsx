// AI 辅助概览页；普通界面只展示当前模型连接，不暴露内部 Profile 管理。

import { Button, Card, Tag, Typography } from 'antd'
import { LLMProfile } from '../../api/llm'

const providerLabels: Record<string, string> = { openai: 'OpenAI', deepseek: 'DeepSeek', gemini: 'Gemini' }

export function ModelServicePage({ profiles, onManage }: { profiles: LLMProfile[]; onManage: () => void }) {
  const current = profiles.find((profile) => profile.enabled && profile.secret_configured) ?? profiles[0]
  const scope = [
    ...['应用接入', '账号准备', '录制', '权限确认', '检查准备', '错误解释'].map((area) => ({ area, participation: '只排序/解释' })),
    { area: '允许/拒绝权限规则', participation: '否' },
    { area: 'PASS/BLOCK/INCONCLUSIVE', participation: '否' },
    { area: '真实执行', participation: '否' },
  ]
  return <Card title="AI 辅助" extra={<Button type="primary" onClick={onManage}>打开 AI 辅助设置</Button>}>
    <Typography.Paragraph type="secondary">AI 只在系统确定事实之上提供辅助，不能决定权限要求或检查结论。</Typography.Paragraph>
    <Typography.Title level={5}>AI 参与范围</Typography.Title>
    <table className="assistant-scope-table" aria-label="AI参与范围"><thead><tr><th>页面环节</th><th>作用</th></tr></thead><tbody>
      {scope.map((item) => <tr key={item.area}><td>{item.area}</td><td>{item.participation}</td></tr>)}
    </tbody></table>
    <div className="assistant-current-service">
      <div><Typography.Text type="secondary">当前模型服务</Typography.Text><Typography.Title level={5}>{current ? `${providerLabels[current.provider] ?? current.provider} · ${current.model}` : '尚未连接'}</Typography.Title></div>
      <Tag>{current?.connection_status === 'available' ? '可用' : current?.connection_status === 'configured' ? '已配置' : current?.connection_status === 'testing' ? '检查中' : '尚未连接'}</Tag>
    </div>
  </Card>
}
