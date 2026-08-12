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

import { Button, Card, List, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { runsApi } from '../../api/runs'
import { JobProgress } from './JobProgress'

type Item = Record<string, any>
const resourceKey = 'jiejian.resource'

function remember(key: string, value: unknown) {
  localStorage.setItem(key, JSON.stringify(value))
}

export function RunPage({ project, runs, onRefresh, onError }: { project: Item; runs: Item[]; onRefresh: () => void; onError: (e: ApiError) => void }) {
  const create = async () => { try { const result = await runsApi.createRun(project.project_id); remember(resourceKey, result.run); await onRefresh() } catch (e) { onError(e as ApiError) } }
  return <Card title="测试" extra={<Button type="primary" onClick={() => void create()}>创建 Run</Button>}><List dataSource={runs} locale={{ emptyText: '暂无运行' }} renderItem={(run) => {
    const integrity = String(run.result_integrity ?? 'UNAVAILABLE')
    const integrityColor = integrity === 'VERIFIED' ? 'green' : integrity === 'INVALID' ? 'red' : 'default'
    return <List.Item><Space direction="vertical"><List.Item.Meta title={run.run_id} description={`生命周期：${run.lifecycle} · Contract ${run.contract_id} v${run.contract_version}`} /><Space><Tag color={integrityColor}>结果完整性：{integrity}</Tag>{integrity === 'INVALID' ? <Typography.Text type="danger">结果无效，已隐藏 Gate verdict</Typography.Text> : run.verdict && <Tag color={run.verdict === 'PASS' ? 'green' : run.verdict === 'BLOCK' ? 'red' : 'gold'}>Gate verdict：{run.verdict}</Tag>}</Space><JobProgress job={run.job} onRefresh={onRefresh} onError={onError} /></Space></List.Item>
  }} /></Card>
}
