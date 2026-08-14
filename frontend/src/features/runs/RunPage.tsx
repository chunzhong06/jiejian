/* =============================================================================
 * 测试页面
 *
 * 定位
 *   已登记 Project 发起 Verification Run 的用户能力页面
 *
 * 职责
 *   提交 Run｜保存最近资源标识｜触发控制壳刷新
 *
 * 调用链
 *   ControlShell → RunPage → runsApi.create
 * ============================================================================= */

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Collapse, Input, List, Select, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { runsApi } from '../../api/runs'
import { permissionExecutionApi } from '../../api/permissionExecution'
import { JobProgress } from './JobProgress'
import { StageGuide } from '../../components/StageGuide'
import { lifecycleLabel, verdictLabel } from '../sharedStatus'

type Item = Record<string, any>
const resourceKey = 'jiejian.resource'

function remember(key: string, value: unknown) {
  localStorage.setItem(key, JSON.stringify(value))
}

export function RunPage({ project, runs, onRefresh, onError, onNext }: { project: Item; runs: Item[]; onRefresh: () => void; onError: (e: ApiError) => void; onNext?: () => void }) {
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [profilePath, setProfilePath] = useState('')
  const [profiles, setProfiles] = useState<Item[]>([])
  const [selectedProfileId, setSelectedProfileId] = useState<string>()
  const [profileLoading, setProfileLoading] = useState(false)
  const [profileMessage, setProfileMessage] = useState<{ type: 'success' | 'info' | 'warning'; text: string } | null>(null)
  const create = async () => { try { const result = await runsApi.createRun(project.project_id); remember(resourceKey, result.run); await onRefresh() } catch (e) { onError(e as ApiError) } }
  const loadProfiles = async () => {
    setProfileLoading(true)
    try {
      const items = await permissionExecutionApi.profiles(String(project.project_id))
      setProfiles(items)
      setSelectedProfileId((current) => current && items.some((item) => item.profile_id === current) ? current : items[0]?.profile_id)
      setProfileMessage(null)
    } catch (e) { onError(e as ApiError) } finally { setProfileLoading(false) }
  }
  useEffect(() => { if (advancedOpen) void loadProfiles() }, [advancedOpen, project.project_id])
  const registerProfile = async (revalidate: boolean) => {
    const path = profilePath.trim()
    if (!path) { setProfileMessage({ type: 'warning', text: '请输入本机 Permission Profile JSON 绝对路径。' }); return }
    setProfileLoading(true)
    try {
      const record = await permissionExecutionApi.register(path, revalidate)
      if (String(record.project_id) !== String(project.project_id)) {
        setProfileMessage({ type: 'warning', text: `配置属于项目 ${String(record.project_id)}，与当前项目 ${String(project.project_id)} 不一致，未选择也未提交。` })
        return
      }
      setProfileMessage({ type: 'success', text: revalidate ? '配置已重新校验并更新。' : '配置已登记。' })
      await loadProfiles()
      setSelectedProfileId(String(record.profile_id))
    } catch (e) { onError(e as ApiError) } finally { setProfileLoading(false) }
  }
  const submitProfile = async () => {
    if (!selectedProfileId) { setProfileMessage({ type: 'warning', text: '请先登记并选择一个复杂权限配置。' }); return }
    setProfileLoading(true)
    try {
      const result = await permissionExecutionApi.submit(String(project.project_id), selectedProfileId)
      if (result.run) remember(resourceKey, result.run)
      setProfileMessage({ type: 'success', text: '复杂权限检查已提交，运行进度将沿用当前测试页刷新。' })
      await onRefresh()
    } catch (e) { onError(e as ApiError) } finally { setProfileLoading(false) }
  }
  const latest = runs[0]
  const canVerify = Boolean(latest && ['COMPLETED', 'SAFETY_STOPPED'].includes(String(latest.lifecycle)) && ['VERIFIED', 'INVALID'].includes(String(latest.result_integrity)))
  const missing = latest ? (canVerify ? '尚未确认' : latest.lifecycle === 'FAILED' ? '检查失败，请查看恢复提示或重新开始' : latest.lifecycle === 'CANCELLED' ? '已取消，可重新开始' : lifecycleLabel(latest.lifecycle)) : '尚未开始检查'
  return <Space direction="vertical" size="large" style={{ width: '100%' }}><StageGuide stage="测试" what="后台在隔离环境中执行已确认检查" why="隔离执行可以限制影响范围，并保留后续验证所需的事实" missing={missing} next={canVerify ? '查看验证证据' : missing} onNext={canVerify ? onNext : undefined} nextLabel="查看验证结果" /><Collapse onChange={(keys) => setAdvancedOpen(Array.isArray(keys) ? keys.includes('permission-v2') : keys === 'permission-v2')} items={[{ key: 'permission-v2', label: '高级：复杂权限检查（Permission Profile V2）', children: <Card size="small" loading={profileLoading}>
    <Space direction="vertical" className="full-width">
      <Typography.Paragraph type="secondary">配置文件只在本次页面内使用，不会写入浏览器本地存储。重新校验必须由用户显式触发。</Typography.Paragraph>
      <Input aria-label="Permission Profile JSON 路径" placeholder="D:\\profiles\\permission-profile.json" value={profilePath} onChange={(event) => setProfilePath(event.target.value)} />
      <Space wrap><Button onClick={() => void registerProfile(false)}>登记配置</Button><Button onClick={() => void registerProfile(true)} disabled={!profilePath.trim()}>重新校验</Button></Space>
      {profileMessage && <Alert type={profileMessage.type} showIcon message={profileMessage.text} />}
      <Typography.Text strong>当前项目已登记配置</Typography.Text>
      <Select aria-label="已登记 Permission Profile" className="full-width" placeholder={profiles.length ? '选择配置' : '当前项目暂无已登记配置'} value={selectedProfileId} onChange={setSelectedProfileId} options={profiles.map((item) => ({ value: String(item.profile_id), label: `${String(item.profile_id)} · ${String(item.contract_id)} v${String(item.contract_version)}` }))} />
      <Button type="primary" disabled={!selectedProfileId} onClick={() => void submitProfile()}>开始复杂权限检查</Button>
    </Space>
  </Card> }]} /><Card title="测试" extra={<Button type="primary" onClick={() => void create()}>开始一次检查</Button>}><List dataSource={runs} locale={{ emptyText: '尚未开始检查' }} renderItem={(run) => {
    const integrity = String(run.result_integrity ?? 'UNAVAILABLE')
    const integrityColor = integrity === 'VERIFIED' ? 'green' : integrity === 'INVALID' ? 'red' : 'default'
    const terminalMessage = run.lifecycle === 'FAILED' ? '检查失败，请查看恢复提示或重新开始' : run.lifecycle === 'CANCELLED' ? '已取消，可重新开始' : undefined
    return <List.Item><Space direction="vertical"><List.Item.Meta title={lifecycleLabel(run.lifecycle)} description={terminalMessage ?? (run.verdict ? verdictLabel(run.verdict) : '结果仍在处理，结论尚未发布')} /><Space><Tag color={integrityColor}>结果完整性：{integrity === 'VERIFIED' ? '已验证' : integrity === 'INVALID' ? '无效' : '尚未确认'}</Tag>{integrity === 'INVALID' && <Typography.Text type="danger">结果完整性无效，安全结论不可用</Typography.Text>}</Space><JobProgress job={run.job} onRefresh={onRefresh} onError={onError} /><Collapse ghost items={[{ key: 'details', label: '高级：检查与运行细节', children: <Space direction="vertical"><Typography.Text>运行标识：{run.run_id}</Typography.Text><Typography.Text>检查规则：{run.contract_id ? `${run.contract_id} v${run.contract_version}` : '尚未确认'}</Typography.Text>{run.verdict && <Typography.Text>原始结论：{run.verdict}</Typography.Text>}</Space> }]} /></Space></List.Item>
  }} /></Card></Space>
}
