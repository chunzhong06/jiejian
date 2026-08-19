// 模型服务概览页；配置和连接测试仍复用同一设置抽屉与后端能力。

import { Button, Card, List, Tag, Typography } from 'antd'
import { LLMProfile } from '../../api/llm'

export function ModelServicePage({ profiles, onManage }: { profiles: LLMProfile[]; onManage: () => void }) {
  return <Card title="模型服务" extra={<Button type="primary" onClick={onManage}>管理模型服务</Button>}>
    <Typography.Paragraph type="secondary">模型服务只用于辅助生成待审内容，最终检查结论仍由规则和事实决定。</Typography.Paragraph>
    <List dataSource={profiles} locale={{ emptyText: '尚未配置模型服务' }} renderItem={(profile) => <List.Item><List.Item.Meta title={profile.profile_name} description={`${profile.provider} · ${profile.model}`} /><Tag>{profile.connection_status === 'available' ? '可用' : profile.connection_status === 'configured' ? '已配置' : profile.connection_status === 'testing' ? '检查中' : '未知'}</Tag></List.Item>} />
  </Card>
}
