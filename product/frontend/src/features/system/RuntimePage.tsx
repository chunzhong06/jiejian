// 运行环境页：展示当前实际运行时，并通过后端同一服务维护三类本地可删除数据。

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Col, Collapse, Descriptions, Modal, Row, Space, Spin, Statistic, Tag, Typography } from 'antd'
import { LLMProfile } from '../../api/llm'
import { MaintenanceOperation, MaintenanceOperationResult, MaintenanceStatus, systemApi, SystemStatus } from '../../api/system'

function label(value: unknown) {
  const raw = String(value ?? 'unknown')
  return raw === 'available' || raw === 'running' ? '可用' : raw === 'stopped' || raw === 'unavailable' ? '不可用' : '未知'
}

function bytes(value: number | undefined) {
  if (!value) return '0 B'
  const units = ['B', 'KiB', 'MiB', 'GiB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1 }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

const operationLabels: Record<MaintenanceOperation, string> = {
  'clear-assistant-cache': '清空 AI 辅助缓存',
  'clear-logs': '清理历史运行日志',
  'clear-temporary': '清理临时运行文件',
  'clear-all': '清理全部可删除内容',
  'repair-runtime': '修复运行环境',
}

const logCategoryLabels: Record<string, string> = {
  startup: '启动', app: '应用', workers: '执行器', runner: '检查运行', recording: '录制',
  'identity-preparations': '账号准备', 'official-samples': '官方示例',
}

export function RuntimePage({ status, profiles, failed }: { status: SystemStatus; profiles: LLMProfile[]; failed: boolean }) {
  const model = failed ? '未知' : profiles.some((profile) => profile.enabled && profile.secret_configured) ? '已配置' : '未知'
  const environment = status.environment
  const python = environment?.python
  const issues = Array.isArray(python?.issues) ? python.issues : []
  const [maintenance, setMaintenance] = useState<MaintenanceStatus | null>(null)
  const [preview, setPreview] = useState<MaintenanceOperationResult | null>(null)
  const [selectedOperation, setSelectedOperation] = useState<MaintenanceOperation | null>(null)
  const [busy, setBusy] = useState(false)
  const [maintenanceError, setMaintenanceError] = useState<string | null>(null)
  const [completed, setCompleted] = useState<MaintenanceOperationResult | null>(null)

  const refreshMaintenance = () => {
    void systemApi.maintenanceStatus().then(setMaintenance).catch((error: Error) => setMaintenanceError(error.message))
  }
  useEffect(refreshMaintenance, [])

  const showPreview = async (operation: MaintenanceOperation) => {
    setBusy(true); setMaintenanceError(null); setCompleted(null)
    try {
      const result = await systemApi.maintenanceOperation(operation, { confirmed: false, dry_run: true })
      setSelectedOperation(operation); setPreview(result)
    } catch (error) { setMaintenanceError((error as Error).message) }
    finally { setBusy(false) }
  }
  const execute = async () => {
    if (!selectedOperation || !preview) return
    setBusy(true); setMaintenanceError(null)
    try {
      const result = await systemApi.maintenanceOperation(selectedOperation, { confirmed: true, dry_run: false, plan_id: preview.plan_id })
      setCompleted(result); setMaintenance(result.status); setPreview(null); setSelectedOperation(null)
    } catch (error) { setMaintenanceError((error as Error).message) }
    finally { setBusy(false) }
  }

  return <Space direction="vertical" size={16} style={{ width: '100%' }}>
    <Card title="运行环境">
      <Typography.Paragraph type="secondary">以下信息来自当前服务进程，用于确认界鉴没有误用用户级 Python 包或另一套工具链。</Typography.Paragraph>
      {python?.user_site_on_sys_path && <Alert type="error" showIcon message="检测到用户级 Python 包来源" description="请退出界鉴并重新运行 start.cmd，让启动器恢复项目环境隔离。" />}
      {issues.length > 0 && <Alert style={{ marginTop: 12 }} type="warning" showIcon message="运行环境存在异常" description={issues.join('；')} />}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} sm={12} lg={6}><Statistic title="服务" value={label(status.api)} /></Col>
        <Col xs={24} sm={12} lg={6}><Statistic title="执行" value={label(status.worker)} /></Col>
        <Col xs={24} sm={12} lg={6}><Statistic title="浏览器" value={label(status.browser)} /></Col>
        <Col xs={24} sm={12} lg={6}><Statistic title="模型" value={model} /></Col>
      </Row>
      <Descriptions style={{ marginTop: 20 }} bordered size="small" column={1}>
        <Descriptions.Item label="界鉴版本">{status.version ?? '未提供'}</Descriptions.Item>
        <Descriptions.Item label="运行模式">{environment?.runtime_mode === 'development' ? '源码运行' : environment?.runtime_mode ?? '未提供'} · {environment?.runtime_fingerprint ?? '无指纹'}</Descriptions.Item>
        <Descriptions.Item label="Python">{python?.version ?? '未提供'} · {python?.environment_type ?? '来源未知'}</Descriptions.Item>
        <Descriptions.Item label="Python 可执行文件"><Typography.Text copyable>{python?.executable ?? '未提供'}</Typography.Text></Descriptions.Item>
        <Descriptions.Item label="Python 环境目录"><Typography.Text copyable>{python?.prefix ?? '未提供'}</Typography.Text></Descriptions.Item>
        <Descriptions.Item label="用户级包">{python?.user_site_on_sys_path ? '正在使用' : '未使用'}</Descriptions.Item>
        <Descriptions.Item label="uv">{environment?.uv?.version ?? '未提供'} · <Typography.Text copyable>{environment?.uv?.executable ?? '未提供'}</Typography.Text></Descriptions.Item>
        <Descriptions.Item label="Node.js">{`${environment?.node?.version ?? '未提供'} · ${environment?.node?.executable ?? '未提供'}${environment?.node?.required === false ? ' · 仅构建时需要' : ''}`}</Descriptions.Item>
        <Descriptions.Item label="pnpm">{`${environment?.pnpm?.version ?? '未提供'} · ${environment?.pnpm?.executable ?? '未提供'}${environment?.pnpm?.required === false ? ' · 仅构建时需要' : ''}`}</Descriptions.Item>
        <Descriptions.Item label="Playwright">{environment?.playwright?.package_version ?? '未提供'} · <Typography.Text copyable>{environment?.playwright?.chromium_executable ?? '未提供'}</Typography.Text></Descriptions.Item>
        <Descriptions.Item label="前端资源">
          {environment?.frontend?.mode === 'source-build'
            ? <>源码构建 · {environment.frontend.build_state === 'reused' ? '已复用' : '已更新'} · <Typography.Text copyable>{environment.frontend.dist ?? '路径未提供'}</Typography.Text></>
            : environment?.frontend?.dependencies ?? '前端资源未确认'}
        </Descriptions.Item>
        <Descriptions.Item label="本次自动恢复任务">{status.recovered_jobs ?? 0}</Descriptions.Item>
      </Descriptions>
      <Tag style={{ marginTop: 16 }} color={python?.ok === false ? 'red' : 'blue'}>{python?.ok === false ? '环境需要处理' : '状态来自当前运行环境'}</Tag>
    </Card>

    <Card title="本地运行数据维护" extra={busy ? <Spin size="small" /> : <Button onClick={refreshMaintenance}>刷新状态</Button>}>
      <Typography.Paragraph type="secondary">这里只维护当前实例可安全删除的缓存、历史日志和临时文件；开发工具与构建缓存不在范围内。</Typography.Paragraph>
      {maintenanceError && <Alert type="error" showIcon message="维护操作失败" description={maintenanceError} closable onClose={() => setMaintenanceError(null)} />}
      {completed && <Alert style={{ marginBottom: 12 }} type={completed.counts.FAILED > 0 ? 'warning' : 'success'} showIcon message="维护操作已完成" description={`成功清理 ${completed.counts.DELETED} 项，安全跳过 ${completed.counts.ALREADY_MISSING + completed.counts.SKIPPED_IN_USE + completed.counts.SKIPPED_CHANGED} 项，失败 ${completed.counts.FAILED} 项。${completed.requires_restart ? '请重新启动界鉴以重建运行环境。' : ''}`} />}
      {completed?.results.some((item) => item.status !== 'DELETED') && <Collapse style={{ marginBottom: 12 }} items={[{ key: 'maintenance-results', label: '查看跳过与失败原因', children: <Space direction="vertical">{completed.results.filter((item) => item.status !== 'DELETED').map((item) => <Typography.Text key={item.item_id}>{item.label}：{item.reason}</Typography.Text>)}</Space> }]} />}
      <Row gutter={[12, 12]}>
        <Col xs={24} md={8}><Card size="small"><Statistic title="AI 辅助缓存" value={bytes(maintenance?.entries.assistant.bytes)} /><Typography.Text type="secondary">{maintenance?.entries.assistant.files ?? 0} 个文件</Typography.Text><div><Button style={{ marginTop: 12 }} disabled={busy} onClick={() => void showPreview('clear-assistant-cache')}>清空 AI 辅助缓存</Button></div></Card></Col>
        <Col xs={24} md={8}><Card size="small"><Statistic title="历史运行日志" value={bytes(maintenance?.entries.logs.bytes)} /><Typography.Text type="secondary">{maintenance?.entries.logs.files ?? 0} 个文件</Typography.Text><div><Button style={{ marginTop: 12 }} disabled={busy} onClick={() => void showPreview('clear-logs')}>清理历史运行日志</Button></div></Card></Col>
        <Col xs={24} md={8}><Card size="small"><Statistic title="临时运行文件" value={bytes(maintenance?.entries.temporary.bytes)} /><Typography.Text type="secondary">{maintenance?.entries.temporary.files ?? 0} 个文件</Typography.Text><div><Button style={{ marginTop: 12 }} disabled={busy} onClick={() => void showPreview('clear-temporary')}>清理临时运行文件</Button></div></Card></Col>
      </Row>
      {maintenance?.entries.logs.categories && <Collapse style={{ marginTop: 12 }} items={[{ key: 'logs', label: '查看日志分类占用', children: <Descriptions size="small" column={1}>{Object.entries(maintenance.entries.logs.categories).map(([name, entry]) => <Descriptions.Item key={name} label={logCategoryLabels[name] ?? name}>{bytes(entry.bytes)} · {entry.files} 个文件</Descriptions.Item>)}</Descriptions> }]} />}
      <Alert style={{ marginTop: 12 }} type="info" showIcon message="产品事实始终保留" description={`不受影响：${maintenance?.protected.data ?? 'var/data'}；应用、权限配置、数据库、证据、报告和凭据不会进入普通清理。`} />
      <Space wrap style={{ marginTop: 16 }}>
        <Button disabled={busy} onClick={() => void showPreview('clear-all')}>清理全部可删除内容</Button>
        <Button disabled={busy} onClick={() => void showPreview('repair-runtime')}>修复运行环境</Button>
      </Space>
    </Card>

    <Modal
      open={preview !== null}
      title={selectedOperation ? operationLabels[selectedOperation] : '维护预览'}
      okText="确认执行"
      cancelText="取消"
      confirmLoading={busy}
      onCancel={() => { setPreview(null); setSelectedOperation(null) }}
      onOk={() => void execute()}
    >
      <Typography.Paragraph>预计处理 {preview?.targets.length ?? 0} 项，共 {bytes(preview?.estimated_bytes)}。确认时只处理这份固定计划。</Typography.Paragraph>
      {(preview?.targets ?? []).slice(0, 8).map((target) => <Typography.Paragraph key={target.item_id}><Typography.Text>{target.label}</Typography.Text> · {target.relative_path} · {bytes(target.estimated_bytes)}</Typography.Paragraph>)}
      <Alert type="warning" showIcon message="确认范围" description="只处理以上可删除内容；不会删除应用、权限配置、数据库、证据、报告和凭据。" />
    </Modal>
  </Space>
}
