// 代码变化页按新到旧展示 Agent 修改和权限影响，不把 Agent 声明当成真实差异。

import { Alert, Button, Card, Empty, Space, Spin, Tag, Typography } from 'antd'
import { useEffect, useState } from 'react'
import type { ApiError } from '../../api/http'
import type { ProductStatusDto, ProjectDto } from '../../api/projects'
import { sourceChangesApi, type SourceChangeViewDto } from '../../api/sourceChanges'
import { formatTimestamp } from '../../app/presentation'
import { PageTaskHeader } from '../../components/PageTaskHeader'

export function ChangesPage({ project, status, onError, onNavigate }: {
  project: ProjectDto
  status: ProductStatusDto | null
  onError: (error: ApiError) => void
  onNavigate: (path: string) => void
}) {
  const [changes, setChanges] = useState<SourceChangeViewDto[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let active = true
    setLoading(true)
    void sourceChangesApi.list(project.project_id).then((items) => {
      if (active) setChanges(items)
    }).catch((error) => {
      if (active) onError(error as ApiError)
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [onError, project.project_id])

  const verifiedChangeId = status?.latest_result?.verified_change_id ?? null
  return <div className="changes-page">
    <PageTaskHeader title="变化与待办" description="每次 Agent 修改都与上一份源码快照比较，并重新核对权限规则、测试准备和当前安全基线。" status={changes.length ? `${changes.length} 次变化` : '等待 Agent 代码变化'} />
    <Alert type="info" showIcon message="人的权限决定会被保留" description="界鉴会加入新发现并标记失效内容，但不会让 Agent 自动批准、删除或改写权限规则。" />
    {loading && <div className="page-loading"><Spin /></div>}
    {!loading && changes.length === 0 && <Empty description="当前还没有 Agent 代码变化记录" />}
    <div className="change-timeline">{changes.map((change, index) => {
      const verified = change.change_id === verifiedChangeId
      return <Card key={change.change_id} className={`change-card${index === 0 ? ' is-latest' : ''}`}>
        <div className="change-card-heading">
          <div><Space wrap><Typography.Title level={4}>{change.reason}</Typography.Title>{index === 0 && <Tag color="blue">最近变化</Tag>}{verified && <Tag color="green">已纳入当前基线</Tag>}</Space><Typography.Text type="secondary">{formatTimestamp(change.created_at_us)}</Typography.Text></div>
          <Space wrap>{change.mapping_review_required_count > 0 && <Button onClick={() => onNavigate('/permissions')}>重新确认权限规则</Button>}{index === 0 && !verified && <Button type="primary" onClick={() => onNavigate('/validation')}>检查这次变化</Button>}</Space>
        </div>
        <Typography.Paragraph>{change.summary}</Typography.Paragraph>
        <div className="change-metrics"><span>实际变化 <strong>{change.actual_changed_path_count}</strong> 个文件</span><span>直接影响 <strong>{change.directly_affected_count}</strong> 条规则</span><span>待重新确认 <strong>{change.mapping_review_required_count}</strong> 条</span></div>
        <ChangePaths change={change} />
      </Card>
    })}</div>
  </div>
}

function ChangePaths({ change }: { change: SourceChangeViewDto }) {
  const groups = [
    ['新增', change.added_paths],
    ['修改', change.modified_paths],
    ['删除', change.removed_paths],
  ] as const
  return <details className="change-paths"><summary>查看实际文件变化</summary><div className="change-path-groups">{groups.map(([label, paths]) => <section key={label}><Typography.Text strong>{label} {paths.length}</Typography.Text>{paths.length ? <ul>{paths.map((path) => <li key={`${label}-${path}`}><Typography.Text code>{path}</Typography.Text></li>)}</ul> : <Typography.Text type="secondary">无</Typography.Text>}</section>)}</div></details>
}
