// 模型服务概览页；配置和连接测试仍复用同一设置抽屉与后端能力。

import { Button, Card, List, Tag, Typography } from 'antd'
import { LLMProfile } from '../../api/llm'

export function ModelServicePage({ profiles, onManage }: { profiles: LLMProfile[]; onManage: () => void }) {
  const scope = [
    ...['应用接入', '账号准备', '录制', '权限确认', '检查准备', '错误解释'].map((area) => ({ area, participation: '只排序/解释' })),
    { area: 'ALLOW/DENY', participation: '否' },
    { area: 'PASS/BLOCK/INCONCLUSIVE', participation: '否' },
    { area: '真实执行', participation: '否' },
  ]
  return <Card title="AI 辅助" extra={<Button type="primary" onClick={onManage}>打开 AI 辅助设置</Button>}>
    <Typography.Paragraph type="secondary">AI 只在系统确定事实之上提供辅助，不能决定权限要求或检查结论。</Typography.Paragraph>
    <Typography.Title level={5}>AI 参与范围</Typography.Title>
    <table className="assistant-scope-table" aria-label="AI参与范围"><thead><tr><th>页面环节</th><th>作用</th></tr></thead><tbody>
      {scope.map((item) => <tr key={item.area}><td>{item.area}</td><td>{item.participation}</td></tr>)}
    </tbody></table>
    <List dataSource={profiles} locale={{ emptyText: '尚未配置模型服务' }} renderItem={(profile) => <List.Item><List.Item.Meta title={profile.profile_name} description={`${profile.provider} · ${profile.model}`} /><Tag>{profile.connection_status === 'available' ? '可用' : profile.connection_status === 'configured' ? '已配置' : profile.connection_status === 'testing' ? '检查中' : '未知'}</Tag></List.Item>} />
  </Card>
}
