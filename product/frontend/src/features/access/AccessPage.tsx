/* =============================================================================
 * 接入页面
 *
 * 定位
 *   本地 ExecutionProfile 路径进入控制面的首个用户能力页面
 *
 * 职责
 *   收集项目路径｜调用项目登记 API｜把已登记 Project 交给控制壳
 *
 * 调用链
 *   ControlShell → AccessPage → projectsApi.register
 * ============================================================================= */

import { Button, Card, Collapse, Form, Input, List, Space, Tag, Typography } from 'antd'
import { OnboardingWizard } from './OnboardingWizard'
import { PageTaskHeader } from '../../components/PageTaskHeader'

type Item = Record<string, any>

export function AccessPage({
  projects,
  selected,
  runs,
  onSelect,
  onRegister,
  onOnboardingSubmitted,
  onContinue,
  loading,
}: {
  projects: Item[]
  selected: Item | null
  runs: Item[]
  onSelect: (p: Item) => void
  onContinue: () => void
  onRegister: (v: { path: string }) => void
  onOnboardingSubmitted?: (result: { project_id: string; run_id: string; job_id: string; demo_data?: boolean }) => void
  loading: boolean
}) {
  return (
    <>
      <PageTaskHeader title="应用接入" description="选择要检查的应用，并确认检查范围与授权信息。" status={selected ? '已选择应用' : '尚未选择应用'} next={selected ? '继续完善权限规则' : '选择应用文件夹开始'} actionLabel={selected ? '去权限规则' : undefined} onAction={selected ? onContinue : undefined} />
      <OnboardingWizard onSubmitted={onOnboardingSubmitted} />
      <Collapse className="access-advanced" items={[{ key: 'advanced', label: '高级配置（ExecutionProfile、已有应用与继续入口）', forceRender: true, children: <div className="access-grid">
        <Card title="接入项目" extra={<Tag>{projects.length} 个项目</Tag>}>
          <Form className="access-form" layout="inline" onFinish={onRegister}>
            <Form.Item name="path" rules={[{ required: true, message: '请输入 ExecutionProfile 绝对路径' }]}>
              <Input placeholder="D:\\profiles\\profile.json" style={{ width: 'min(420px, 100%)' }} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>注册并校验</Button>
          </Form>
          <List className="project-list" dataSource={[...projects].sort((a, b) => Number(b.updated_at_us ?? 0) - Number(a.updated_at_us ?? 0))} locale={{ emptyText: '尚未注册项目' }} renderItem={(project) => (
            <List.Item actions={[<Button type="link" onClick={() => onSelect(project)} key="open">打开</Button>]}>
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
              <div className="overview-item">当前权限规则<br /><Typography.Text>{selected.governed_contract_id ? '已绑定' : '尚未确认'}</Typography.Text></div>
              <div className="overview-item">最近检查<br /><Typography.Text>{runs[0] ? `${runs[0].lifecycle} · ${runs[0].verdict ?? '尚无结论'}` : '暂无'}</Typography.Text></div>
            </div>
            <Button type="primary" disabled={!selected} onClick={onContinue}>去权限规则</Button>
          </Space> : <Typography.Text type="secondary">暂无已确认的当前项目</Typography.Text>}
        </Card>
      </div> }]} />
    </>
  )
}
