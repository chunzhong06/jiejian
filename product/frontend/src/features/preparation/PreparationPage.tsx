// 测试准备总览把账号、业务流程和当前检查配置组织为可持续维护的能力区。

import { Button, Card, Space, Tag, Typography } from 'antd'
import type { ProjectReadinessDto } from '../../api/projects'
import { PageTaskHeader } from '../../components/PageTaskHeader'

export function PreparationPage({ readiness, onNavigate }: {
  readiness: ProjectReadinessDto
  onNavigate: (path: string) => void
}) {
  const permissionActions = readiness.permission_actions ?? []
  const cards = [
    {
      key: 'identities',
      title: '测试账号',
      ready: permissionActions.length > 0 && !permissionActions.some((action) => action.gaps.some((gap) => gap.startsWith('TEST_IDENTITY_') || gap === 'MISSING_SUBJECT')),
      description: '为已确认权限组准备受控登录状态，用于允许与拒绝的差分检查。',
      route: '/identities',
      action: '管理测试账号',
    },
    {
      key: 'flows',
      title: '业务流程与真实后果',
      ready: readiness.completed_flow_available,
      description: '维护关键操作、测试资源、结果观察和现场恢复；应用变化后只补齐失效部分。',
      route: '/flows',
      action: '管理业务流程',
    },
    {
      key: 'profile',
      title: '当前检查配置',
      ready: readiness.execution_profile_available,
      description: '根据最新权限规则和测试准备生成；事实变化后必须重新生成。',
      route: '/validation',
      action: '前往验证运行',
    },
  ]
  const readyCount = cards.filter((card) => card.ready).length
  return <div className="preparation-page">
    <PageTaskHeader title="测试准备" description="测试账号、真实业务流程和恢复方式会随应用持续维护，不需要每次从头接入。" status={`${readyCount}/${cards.length} 项可用`} />
    <div className="preparation-grid">{cards.map((card) => <Card key={card.key} className="preparation-card">
      <Space direction="vertical" size={14}>
        <Space wrap><Typography.Title level={3}>{card.title}</Typography.Title><Tag color={card.ready ? 'green' : 'orange'}>{card.ready ? '当前可用' : '需要处理'}</Tag></Space>
        <Typography.Paragraph type="secondary">{card.description}</Typography.Paragraph>
        <Button type={card.ready ? 'default' : 'primary'} onClick={() => onNavigate(card.route)}>{card.action}</Button>
      </Space>
    </Card>)}</div>
    <div className="preparation-footer"><Button onClick={() => onNavigate('/permissions')}>返回权限规则</Button><Button type="primary" onClick={() => onNavigate('/validation')}>前往验证运行</Button></div>
  </div>
}
