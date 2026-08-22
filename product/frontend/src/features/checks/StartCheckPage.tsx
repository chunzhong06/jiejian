/* 开始检查：只提交已登记执行配置，并展示当前真实过程。 */

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Collapse, List, Select, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { executionProfilesApi, type ExecutionProfileDto } from '../../api/executionProfiles'
import { runsApi, type RunDto } from '../../api/runs'
import type { ProjectDto } from '../../api/projects'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { lifecycleLabel, verdictLabel } from '../../app/presentation'
import { CheckProgress } from './CheckProgress'
import './checks.css'

export function StartCheckPage({ project, runs, onRefresh, onError, onNext }: { project: ProjectDto; runs: RunDto[]; onRefresh: () => void; onError: (error: ApiError) => void; onNext?: () => void }) {
  const [currentRun, setCurrentRun] = useState<RunDto | undefined>(runs[0])
  const [profiles, setProfiles] = useState<ExecutionProfileDto[]>([])
  const [selectedProfileId, setSelectedProfileId] = useState<string>()
  const [loading, setLoading] = useState(false)
  const latest = currentRun ?? runs[0]
  const canView = Boolean(latest && ['COMPLETED', 'SAFETY_STOPPED'].includes(String(latest.lifecycle)) && ['VERIFIED', 'INVALID'].includes(String(latest.result_integrity)))

  useEffect(() => { setCurrentRun(runs[0]) }, [runs])
  useEffect(() => {
    let active = true
    void executionProfilesApi.profiles(String(project.project_id)).then((items) => {
      if (!active) return
      setProfiles(items)
      setSelectedProfileId((value) => value && items.some((item) => String(item.profile_id) === value) ? value : items.length === 1 ? String(items[0].profile_id) : undefined)
    }).catch((error) => { if (active) onError(error as ApiError) })
    return () => { active = false }
  }, [project.project_id])
  useEffect(() => {
    const summary = runs[0]
    if (!summary?.run_id) return
    let active = true
    void runsApi.run(String(summary.run_id)).then((run) => { if (active) setCurrentRun(run) }).catch((error) => { if (active) onError(error as ApiError) })
    return () => { active = false }
  }, [runs[0]?.run_id, runs[0]?.lifecycle, runs[0]?.updated_at_us, runs[0]?.job?.state])
  const submit = async () => {
    if (!selectedProfileId) return
    setLoading(true)
    try { const result = await executionProfilesApi.submit(project.project_id, selectedProfileId); setCurrentRun(result.run); await onRefresh() } catch (error) { onError(error as ApiError) } finally { setLoading(false) }
  }
  const titleStatus = latest ? lifecycleLabel(latest.lifecycle) : '尚未开始'
  return <Space direction="vertical" size="large" className="full-width">
    <PageTaskHeader title="开始检查" description="选择已登记的执行配置，在受控环境中执行检查，并保留查看结果所需的事实。" status={titleStatus} next={canView ? '查看检查结果' : latest ? '后台检查状态会在这里更新' : '选择执行配置'} actionLabel={canView ? '查看检查结果' : undefined} onAction={canView ? onNext : undefined} />
    <Card title="当前检查" extra={latest?.run_id ? <Typography.Text type="secondary">{lifecycleLabel(latest.lifecycle)}</Typography.Text> : undefined}>
      {!latest && <Typography.Paragraph type="secondary">尚未开始检查。</Typography.Paragraph>}
      {latest && <CheckProgress run={latest} onRefresh={onRefresh} onError={onError} />}
      {latest?.verdict && <Tag>当前安全结论：{verdictLabel(latest.verdict)}</Tag>}
    </Card>
    <Card title="选择执行配置">
      <Space direction="vertical" className="full-width">
        <Typography.Paragraph type="secondary">执行配置只能从权限规则页登记并重新校验；此处仅选择已登记配置并提交。</Typography.Paragraph>
        {profiles.length === 0 && <Alert type="info" showIcon message="当前项目暂无已登记执行配置。" />}
        <Select aria-label="已登记执行配置" className="full-width" placeholder={profiles.length > 1 ? '请选择配置' : profiles.length === 1 ? '已自动选择唯一配置' : '暂无可选配置'} value={selectedProfileId} onChange={setSelectedProfileId} options={profiles.map((item, index) => ({ value: String(item.profile_id), label: `执行配置 ${index + 1}` }))} />
        <Button type="primary" loading={loading} disabled={!selectedProfileId} onClick={() => void submit()}>开始检查</Button>
      </Space>
    </Card>
    <Collapse ghost items={[{ key: 'history', label: '历史检查', children: <List dataSource={runs.slice(1, 11)} locale={{ emptyText: '没有其他检查记录' }} renderItem={(run) => <List.Item><Space direction="vertical"><Typography.Text strong>{lifecycleLabel(run.lifecycle)}</Typography.Text><Typography.Text>{run.verdict ? verdictLabel(run.verdict) : '尚无结论'}</Typography.Text><Tag>{String(run.result_integrity) === 'VERIFIED' ? '结果已验证' : '结果尚未确认'}</Tag></Space></List.Item>} /> }]} />
  </Space>
}
