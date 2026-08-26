/* 开始检查：展示当前自动差分计划，并无 Profile 参数地提交唯一普通检查链。 */

import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Collapse, Descriptions, List, Space, Tag, Typography } from 'antd'
import { checksApi, type CheckPreviewDto } from '../../api/checks'
import { ApiError } from '../../api/http'
import { runsApi, type RunDto } from '../../api/runs'
import type { ProjectDto } from '../../api/projects'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { lifecycleLabel, verdictLabel } from '../../app/presentation'
import { CheckProgress } from './CheckProgress'
import './checks.css'

type StartCheckProps = {
  project: ProjectDto
  runs: RunDto[]
  onRefresh: () => void
  onError: (error: ApiError) => void
  onResolved?: () => void
  onNext?: () => void
  onPrepare?: (path: string) => void
}

export function StartCheckPage({ project, runs, onRefresh, onError, onResolved, onNext, onPrepare }: StartCheckProps) {
  const [currentRun, setCurrentRun] = useState<RunDto | undefined>(runs[0])
  const [preview, setPreview] = useState<CheckPreviewDto | null>(null)
  const [loadingPreview, setLoadingPreview] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const reconciledTerminalRun = useRef<string | null>(null)
  const latest = currentRun ?? runs[0]
  const uncoveredActionCount = preview?.actions.filter((action) => !action.ready).length ?? 0
  const executableActionCount = preview?.actions.filter((action) => action.ready).length ?? 0
  const allowCount = preview?.actions.flatMap((action) => action.checks).filter((item) => item.expectation === 'ALLOW').length ?? 0
  const denyCount = preview?.actions.flatMap((action) => action.checks).filter((item) => item.expectation === 'DENY').length ?? 0
  const canView = Boolean(latest && ['COMPLETED', 'SAFETY_STOPPED'].includes(String(latest.lifecycle)) && ['VERIFIED', 'INVALID'].includes(String(latest.result_integrity)))

  useEffect(() => { setCurrentRun(runs[0]) }, [runs])
  useEffect(() => {
    let active = true
    setLoadingPreview(true)
    void checksApi.preview(String(project.project_id)).then((value) => {
      if (active) { setPreview(value); onResolved?.() }
    }).catch((error) => { if (active) onError(error as ApiError) }).finally(() => { if (active) setLoadingPreview(false) })
    return () => { active = false }
  }, [project.project_id])
  useEffect(() => {
    const summary = runs[0]
    if (!summary?.run_id) return
    let active = true
    void runsApi.run(String(summary.run_id)).then((run) => { if (active) setCurrentRun(run) }).catch((error) => { if (active) onError(error as ApiError) })
    return () => { active = false }
  }, [runs[0]?.run_id, runs[0]?.lifecycle, runs[0]?.updated_at_us, runs[0]?.job?.state])
  useEffect(() => {
    if (!latest?.run_id || !['COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED'].includes(String(latest.lifecycle))) return
    const terminalKey = `${latest.run_id}:${latest.lifecycle}:${latest.job?.state ?? ''}`
    if (reconciledTerminalRun.current === terminalKey) return
    reconciledTerminalRun.current = terminalKey
    // Run 与 Readiness 分接口读取；观察到终态后再取一次，避免展示旧活动任务与新 Run 的竞态组合。
    void onRefresh()
  }, [latest?.run_id, latest?.lifecycle, latest?.job?.state, onRefresh])

  const submit = async () => {
    if (!preview?.ready) return
    setSubmitting(true)
    try {
      const result = await checksApi.submit(String(project.project_id))
      setCurrentRun(result.run)
      await onRefresh()
      onResolved?.()
    } catch (error) {
      onError(error as ApiError)
    } finally {
      setSubmitting(false)
    }
  }

  const titleStatus = latest ? lifecycleLabel(latest.lifecycle) : preview?.ready ? '可以开始' : '准备未完成'
  return <Space direction="vertical" size="large" className="full-width check-start-page">
    <PageTaskHeader title="开始检查" description="核对当前业务动作、测试账号与差分范围，然后由界鉴在受控环境中自动检查。" status={titleStatus} next={canView ? '查看检查结果' : preview?.ready ? '确认后开始检查' : preview?.next_label ?? '完成检查准备'} actionLabel={canView ? '查看检查结果' : undefined} onAction={canView ? onNext : undefined} />
    <Card className="check-preview-card" title="检查预览" extra={preview?.ready ? <Tag color="success">准备完成</Tag> : <Tag color="warning">仍有缺项</Tag>}>
      {loadingPreview && <Typography.Text type="secondary">正在核对当前检查范围……</Typography.Text>}
      {!loadingPreview && preview?.actions.length === 0 && <Alert type="info" showIcon message="还没有可检查的业务动作" />}
      <Space direction="vertical" size={24} className="full-width check-preview-content">
        {preview && <Descriptions className="check-preview-summary" column={{ xs: 1, sm: 2, md: 4 }}>
          <Descriptions.Item label="可检查动作数">{executableActionCount}</Descriptions.Item>
          <Descriptions.Item label="检查用例数">{preview.case_count}</Descriptions.Item>
          <Descriptions.Item label="应该允许 / 应该拒绝">{allowCount} / {denyCount}</Descriptions.Item>
          <Descriptions.Item label="权限要求未覆盖">{uncoveredActionCount}</Descriptions.Item>
        </Descriptions>}
        {preview?.actions.map((action) => <Card className="check-preview-action" key={action.action_candidate_id} type="inner" title={action.action_display_name} extra={<Tag color={action.ready ? 'success' : 'warning'}>{action.ready ? '可以检查' : '需要补充'}</Tag>}>
          {action.resource_logical_name && <Typography.Paragraph type="secondary">测试资源：{action.resource_logical_name}</Typography.Paragraph>}
          {action.gaps.length > 0 && <Alert type="warning" showIcon message="这个动作暂未覆盖" description={action.gaps.map((gap) => gap.message).join('；')} />}
          <List className="check-preview-list" dataSource={action.checks} locale={{ emptyText: '尚无账号检查项' }} renderItem={(item) => <List.Item extra={<Tag color={item.expectation === 'ALLOW' ? 'green' : item.expectation === 'DENY' ? 'red' : 'default'}>{item.expectation === 'ALLOW' ? '应该允许' : item.expectation === 'DENY' ? '应该拒绝' : '尚未确认'}</Tag>}>
            <List.Item.Meta title={item.subject_label} description={`${item.subject_role_display_name} · ${relationLabels[item.relation] ?? item.relation}${item.gaps.length ? ` · ${item.gaps.map((gap) => gap.message).join('、')}` : ''}`} />
          </List.Item>} />
        </Card>)}
        {preview?.ready && <Alert type="success" showIcon message={`将执行 ${preview.case_count} 个检查用例，形成 ${preview.differential_pair_count} 组允许/拒绝对照${uncoveredActionCount > 0 ? `，另外 ${uncoveredActionCount} 个动作暂未覆盖` : ''}。`} />}
        {!loadingPreview && preview && !preview.ready && preview.gaps.length > 0 && <Alert type="warning" showIcon message="当前还不能开始检查" description={preview.gaps.map((gap) => gap.message).join('；')} action={preview.next_path && onPrepare ? <Button onClick={() => onPrepare(preview.next_path!)}>{preview.next_label ?? '去完成准备'}</Button> : undefined} />}
        <Button className="check-start-action" type="primary" size="large" loading={submitting} disabled={!preview?.ready} onClick={() => void submit()}>开始检查</Button>
      </Space>
    </Card>
    <Card title="当前检查" extra={latest?.run_id ? <Typography.Text type="secondary">{lifecycleLabel(latest.lifecycle)}</Typography.Text> : undefined}>
      {!latest && <Typography.Paragraph type="secondary">尚未开始检查。</Typography.Paragraph>}
      {latest && <CheckProgress run={latest} actions={preview?.actions} onRefresh={onRefresh} onError={onError} onNavigate={onPrepare} />}
      {latest?.verdict && <Tag>当前安全结论：{verdictLabel(latest.verdict)}</Tag>}
    </Card>
    <Collapse ghost items={[{ key: 'history', label: '历史检查', children: <List dataSource={runs.slice(1, 11)} locale={{ emptyText: '没有其他检查记录' }} renderItem={(run) => <List.Item><Space direction="vertical"><Typography.Text strong>{lifecycleLabel(run.lifecycle)}</Typography.Text><Typography.Text>{run.verdict ? verdictLabel(run.verdict) : '尚无结论'}</Typography.Text><Tag>{String(run.result_integrity) === 'VERIFIED' ? '结果已验证' : '结果尚未确认'}</Tag></Space></List.Item>} /> }]} />
  </Space>
}

const relationLabels: Record<string, string> = {
  OWNS: '资源所有者',
  SAME_ROLE_OTHER_ACCOUNT: '同角色其他账号',
  OTHER_ROLE: '其他角色账号',
}
