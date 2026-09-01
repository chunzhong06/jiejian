// 代码变化页按新到旧展示 Agent 修改和权限影响，不把 Agent 声明当成真实差异。

import { Alert, Button, Card, Space, Spin, Tag, Typography } from 'antd'
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

  const revalidation = status?.revalidation ?? null
  const currentTitle = loading
    ? '正在读取当前代码变化。'
    : revalidation?.status === 'NO_CHANGE' || changes.length === 0
      ? '当前没有需要重新核对的代码变化。'
      : revalidation
        ? revalidationLabel(revalidation.status)
        : `已记录 ${changes.length} 次 Agent 变化，等待确认本轮影响。`

  return <div className="changes-page">
    <PageTaskHeader title="变化" description="查看 Agent 提交了什么、界鉴实际发现了什么，以及哪些权限需要重新核对。" status={changes.length ? `${changes.length} 次变化` : '等待后续变化'} />
    <section className={`changes-overview${!loading && changes.length === 0 ? ' is-idle' : ''}`} aria-labelledby="changes-current-title" aria-busy={loading}>
      <div className="changes-overview-copy">
        <span className="changes-overview-eyebrow">当前变化判断</span>
        <Typography.Title id="changes-current-title" level={3}>{currentTitle}</Typography.Title>
        <Typography.Paragraph>
          人确认的权限规则保持不变。Agent 通过 MCP 提交变化后，界鉴会核对真实文件差异，并指出需要重新确认或检查的规则。
        </Typography.Paragraph>
      </div>
      {loading
        ? <div className="changes-overview-loading"><Spin /><Typography.Text type="secondary">正在读取应用源码与变化记录</Typography.Text></div>
        : <div className="changes-overview-state">
          <Typography.Text strong>{revalidation?.summary ?? '等待 Agent 提交下一次代码变化。'}</Typography.Text>
          <Typography.Text type="secondary">Agent 可以提交变化和发起获准检查，但不能批准、删除或改写人的权限决定。</Typography.Text>
        </div>}
    </section>
    <div className="change-timeline">{changes.map((change) => {
      const current = status?.revalidation?.change_id === change.change_id ? status.revalidation : null
      const latest = changes[0]?.change_id === change.change_id
      const verified = current?.status === 'VERIFIED'
      return <Card key={change.change_id} className={`change-card${latest ? ' is-latest' : ''}`}>
        <div className="change-card-heading">
          <div className="change-card-copy"><Space wrap><Typography.Title level={4}>{change.reason}</Typography.Title>{latest && <Tag color="blue">最近变化</Tag>}{verified && <Tag color="green">已纳入当前安全基线</Tag>}</Space><div className="change-card-meta"><span>{change.submitted_by}</span><span aria-hidden="true">·</span><span>{formatTimestamp(change.created_at_us)}</span></div></div>
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
