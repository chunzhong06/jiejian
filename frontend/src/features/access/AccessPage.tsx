/* =============================================================================
 * 接入页面
 *
 * 定位
 *   本地 Project bundle 路径进入控制面的首个用户能力页面
 *
 * 职责
 *   收集项目路径｜调用项目登记 API｜把已登记 Project 交给控制壳
 *
 * 调用链
 *   ControlShell → AccessPage → projectsApi.register
 * ============================================================================= */

import { Button, Card, Form, Input, List, Space, Tag, Typography } from 'antd'

type Item = Record<string, any>

export function AccessPage({
  projects,
  selected,
  runs,
  onSelect,
  onRegister,
  onContinue,
  loading,
}: {
  projects: Item[]
  selected: Item | null
  runs: Item[]
  onSelect: (p: Item) => void
  onContinue: () => void
  onRegister: (v: { path: string }) => void
  loading: boolean
}) {
  return (
    <>
      <Card className="access-hero" variant="borderless">
        <Typography.Title level={2}>从安全意图到交付门禁</Typography.Title>
        <Typography.Paragraph>登记真实项目，整理可执行契约，经过受控验证后形成可追溯的交付结论。</Typography.Paragraph>
        <Button type="primary" disabled={!selected} onClick={onContinue}>继续建约</Button>
        {!selected && <Typography.Text type="secondary">请选择一个已从控制面确认的项目后继续。</Typography.Text>}
      </Card>
      <div className="access-grid">
        <Card title="接入项目" extra={<Tag>{projects.length} 个项目</Tag>}>
          <Form className="access-form" layout="inline" onFinish={onRegister}>
            <Form.Item name="path" rules={[{ required: true, message: '请输入项目 YAML 绝对路径' }]}>
              <Input placeholder="D:\\demo\\project.yaml" style={{ width: 'min(420px, 100%)' }} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>注册并校验</Button>
          </Form>
          <List className="project-list" dataSource={[...projects].sort((a, b) => Number(b.updated_at_us ?? 0) - Number(a.updated_at_us ?? 0))} locale={{ emptyText: '尚未注册项目' }} renderItem={(project) => (
            <List.Item
              actions={[<Button type="link" onClick={() => onSelect(project)} key="open">打开</Button>]}
            >
              <List.Item.Meta title={project.name} description={`${project.project_id} · ${project.status}`} />
            </List.Item>
          )} />
        </Card>
        <Card title="当前工作概览">
          {selected ? <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Typography.Text strong>{selected.name}</Typography.Text>
            <div className="overview-list">
              <div className="overview-item">项目状态<br /><Typography.Text>{selected.status ?? '未知'}</Typography.Text></div>
              <div className="overview-item">Run 数量<br /><Typography.Text>{runs.length}</Typography.Text></div>
              <div className="overview-item">治理 Contract<br /><Typography.Text>{selected.governed_contract_id ? `${selected.governed_contract_id} v${selected.governed_contract_version}` : '暂无'}</Typography.Text></div>
              <div className="overview-item">最近 Run<br /><Typography.Text>{runs[0] ? `${runs[0].lifecycle} · ${runs[0].verdict ?? '等待结论'}` : '暂无'}</Typography.Text></div>
            </div>
          </Space> : <Typography.Text type="secondary">暂无已确认的当前项目</Typography.Text>}
        </Card>
      </div>
    </>
  )
}
