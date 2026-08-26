/* =============================================================================
 * 接入页面
 *
 * 定位
 *   普通用户连接本地应用并建立应用理解的首个产品页面
 *
 * 职责
 *   承载默认应用理解向导｜恢复已有 Project｜隔离旧版高级接入
 *
 * 调用链
 *   ControlShell → AccessPage → ApplicationSetup / 高级旧版接入
 * ============================================================================= */

import { Button, Card, Collapse, Form, Input, List, Space, Tag, Typography } from 'antd'
import { ApplicationSetup } from './ApplicationSetup'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { lifecycleLabel, productStatusLabel, verdictLabel } from '../../app/presentation'
import type { ProjectDto } from '../../api/projects'
import type { RunDto } from '../../api/runs'
import './access.css'

export function AccessPage({
  projects,
  selected,
  runs,
  onSelect,
  onConnected,
  onUnderstandingChanged,
  onRegister,
  onContinue,
  loading,
}: {
  projects: ProjectDto[]
  selected: ProjectDto | null
  runs: RunDto[]
  onSelect: (project: ProjectDto) => void
  onConnected: (project: ProjectDto) => void
  onUnderstandingChanged: () => void
  onContinue: () => void
  onRegister: (v: { path: string }) => void
  loading: boolean
}) {
  return (
    <>
      <PageTaskHeader title="应用接入" description="选择本地应用，确认访问地址，再审阅界鉴发现的权限组与关键业务动作。" status={selected ? '已选择应用' : '尚未选择应用'} next={selected ? '完成当前应用理解' : '选择应用文件夹开始'} />
      <ApplicationSetup selected={selected} onConnected={onConnected} onChanged={onUnderstandingChanged} onContinue={onContinue} />
      <Collapse className="access-advanced" items={[{ key: 'advanced', label: '高级配置（已有 Profile 项目）', children: <div className="access-grid">
        <Card title="接入项目" extra={<Tag>{projects.length} 个项目</Tag>}>
          <Form className="access-form" layout="inline" onFinish={onRegister}>
            <Form.Item name="path" rules={[{ required: true, message: '请输入 Web 执行配置的绝对路径' }]}>
              <Input placeholder="D:\\profiles\\profile.json" style={{ width: 'min(420px, 100%)' }} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>注册并校验</Button>
          </Form>
          <List className="project-list" dataSource={[...projects].sort((a, b) => Number(b.updated_at_us ?? 0) - Number(a.updated_at_us ?? 0))} locale={{ emptyText: '尚未注册项目' }} renderItem={(project) => (
            <List.Item actions={[<Button type="link" onClick={() => onSelect(project)} key="open">打开</Button>]}>
              <List.Item.Meta title={project.name} description={`${project.project_id} · ${productStatusLabel('project', project.status)}`} />
            </List.Item>
          )} />
        </Card>
        <Card title="当前工作概览">
          {selected ? <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Typography.Text strong>{selected.name}</Typography.Text>
            <div className="overview-list">
              <div className="overview-item">应用状态<br /><Typography.Text>{productStatusLabel('project', selected.status)}</Typography.Text></div>
              <div className="overview-item">检查次数<br /><Typography.Text>{runs.length}</Typography.Text></div>
              <div className="overview-item">当前权限规则<br /><Typography.Text>{selected.governed_contract_id ? '已绑定' : '尚未确认'}</Typography.Text></div>
              <div className="overview-item">最近检查<br /><Typography.Text>{runs[0] ? `${lifecycleLabel(runs[0].lifecycle)} · ${verdictLabel(runs[0].verdict)}` : '暂无'}</Typography.Text></div>
            </div>
            <Button type="primary" disabled={!selected} onClick={onContinue}>去业务流程</Button>
          </Space> : <Typography.Text type="secondary">暂无已确认的当前项目</Typography.Text>}
        </Card>
      </div> }]} />
    </>
  )
}
