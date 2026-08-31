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

  return <div className="changes-page">
    <PageTaskHeader title="变化与待办" description="每次 Agent 修改都与上一份源码快照比较，并重新核对权限规则、测试准备和当前安全基线。" status={changes.length ? `${changes.length} 次变化` : '等待 Agent 代码变化'} />
    <Alert type="info" showIcon message="人的权限决定会被保留" description="界鉴会加入新发现并标记失效内容，但不会让 Agent 自动批准、删除或改写权限规则。" />
    {status?.revalidation?.status === 'NO_CHANGE' && <Alert type="success" showIcon message="无待处理变化" description={status.revalidation.summary} />}
    {loading && <div className="page-loading"><Spin /></div>}
    {!loading && changes.length === 0 && <Empty description="当前还没有 Agent 代码变化记录" />}
    <div className="change-timeline">{changes.map((change) => {
      const current = status?.revalidation?.change_id === change.change_id ? status.revalidation : null
      const latest = changes[0]?.change_id === change.change_id
      const verified = current?.status === 'VERIFIED'
      return <Card key={change.change_id} className={`change-card${latest ? ' is-latest' : ''}`}>
        <div className="change-card-heading">
          <div><Space wrap><Typography.Title level={4}>{change.reason}</Typography.Title>{latest && <Tag color="blue">最近变化</Tag>}{verified && <Tag color="green">已纳入当前安全基线</Tag>}</Space><Typography.Text type="secondary">{formatTimestamp(change.created_at_us)}</Typography.Text></div>
          <Space wrap>{current?.next_path && <Button type={current.status === 'READY' ? 'primary' : 'default'} onClick={() => onNavigate(current.next_path ?? '/changes')}>{current.next_label ?? '继续处理'}</Button>}</Space>
        </div>
        <Typography.Paragraph>{change.summary}</Typography.Paragraph>
        {current && <Alert type={verified ? 'success' : current.status === 'STALE' ? 'warning' : 'info'} showIcon message={revalidationLabel(current.status)} description={current.summary} />}
        <div className="change-metrics"><span>实际变化 <strong>{change.actual_changed_path_count}</strong> 个文件</span><span>直接影响 <strong>{change.directly_affected_count}</strong> 条规则</span><span>待重新确认 <strong>{change.mapping_review_required_count}</strong> 条</span></div>
        <ChangePaths change={change} />
      </Card>
    })}</div>
  </div>
}

function revalidationLabel(status: NonNullable<ProductStatusDto['revalidation']>['status']) {
  return ({
    NO_CHANGE: '无待处理变化', REVIEW_REQUIRED: '需要重新确认实现映射',
    PREPARATION_REQUIRED: '需要补齐测试准备', READY: '可以检查这次变化',
    VERIFIED: '已纳入当前安全基线', STALE: '当前变化已失效',
  } as const)[status]
}

function ChangePaths({ change }: { change: SourceChangeViewDto }) {
  const groups = [
    ['新增', change.added_paths],
    ['修改', change.modified_paths],
    ['删除', change.removed_paths],
  ] as const
  return <details className="change-paths"><summary>查看实际文件变化</summary><div className="change-path-groups">{groups.map(([label, paths]) => <section key={label}><Typography.Text strong>{label} {paths.length}</Typography.Text>{paths.length ? <ul>{paths.map((path) => <li key={`${label}-${path}`}><Typography.Text code>{path}</Typography.Text></li>)}</ul> : <Typography.Text type="secondary">无</Typography.Text>}</section>)}</div></details>
}
