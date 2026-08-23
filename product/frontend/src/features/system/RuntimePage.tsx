// 运行环境页：展示当前实际运行时，并通过后端同一维护服务预览、确认和执行缓存操作。

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Col, Descriptions, Modal, Row, Space, Spin, Statistic, Tag, Typography } from 'antd'
import { LLMProfile } from '../../api/llm'
import { CacheOperation, CacheOperationResult, CacheStatus, systemApi, SystemStatus } from '../../api/system'

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

const operationLabels: Record<CacheOperation, string> = {
  prune: '按预算清理',
  clean: '清空可重建缓存',
  'runtime-repair': '修复损坏运行时',
}

const cacheLabels: Record<string, string> = {
  uv: 'uv 缓存',
  pnpm_store: 'pnpm store',
  npm: 'npm 缓存',
  vite: 'Vite 缓存',
  downloads: '下载缓存',
  startup: '启动缓存',
  retired_runtime: '可回收旧运行时',
}

export function RuntimePage({ status, profiles, failed }: { status: SystemStatus; profiles: LLMProfile[]; failed: boolean }) {
  const model = failed ? '未知' : profiles.some((profile) => profile.enabled && profile.secret_configured) ? '已配置' : '未知'
  const environment = status.environment
  const python = environment?.python
  const issues = Array.isArray(python?.issues) ? python.issues : []
  const [cache, setCache] = useState<CacheStatus | null>(null)
  const [preview, setPreview] = useState<CacheOperationResult | null>(null)
  const [selectedOperation, setSelectedOperation] = useState<CacheOperation | null>(null)
  const [busy, setBusy] = useState(false)
  const [maintenanceError, setMaintenanceError] = useState<string | null>(null)
  const [completed, setCompleted] = useState<CacheOperationResult | null>(null)

  const refreshCache = () => {
    void systemApi.cacheStatus().then(setCache).catch((error: Error) => setMaintenanceError(error.message))
  }
  useEffect(refreshCache, [])

  const showPreview = async (operation: CacheOperation) => {
    setBusy(true); setMaintenanceError(null); setCompleted(null)
    try {
      const result = await systemApi.cacheOperation(operation, { confirmed: false, dry_run: true })
      setSelectedOperation(operation); setPreview(result)
    } catch (error) { setMaintenanceError((error as Error).message) }
    finally { setBusy(false) }
  }
  const execute = async () => {
    if (!selectedOperation) return
    setBusy(true); setMaintenanceError(null)
    try {
      const result = await systemApi.cacheOperation(selectedOperation, { confirmed: true, dry_run: false })
      setCompleted(result); setCache(result.status); setPreview(null); setSelectedOperation(null)
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

    <Card title="缓存与运行时维护" extra={busy ? <Spin size="small" /> : <Button onClick={refreshCache}>刷新状态</Button>}>
      <Typography.Paragraph type="secondary">所有操作都由后端维护服务执行。预览和结果不会包含数据库、Evidence、报告或凭据。</Typography.Paragraph>
      {maintenanceError && <Alert type="error" showIcon message="维护操作失败" description={maintenanceError} closable onClose={() => setMaintenanceError(null)} />}
      {completed && <Alert style={{ marginBottom: 12 }} type="success" showIcon message="维护操作已完成" description={`已处理 ${completed.removed.length} 项，共 ${bytes(completed.estimated_bytes)}。${completed.requires_restart ? '请重新启动界鉴以重建运行时。' : ''}`} />}
      <Row gutter={[12, 12]}>
        {Object.entries(cache?.entries ?? {}).map(([name, entry]) => <Col xs={24} md={8} key={name}><Card size="small"><Statistic title={cacheLabels[name] ?? name} value={bytes(entry.bytes)} /><Tag color={entry.over_budget ? 'orange' : 'green'}>{entry.over_budget ? '超过软预算' : '预算内'}</Tag></Card></Col>)}
      </Row>
      <Alert style={{ marginTop: 12 }} type="info" showIcon message="产品事实始终保留" description={`不受影响：${cache?.protected.data ?? 'var/data'}、当前运行时、数据库、证据、报告和凭据。`} />
      <Space wrap style={{ marginTop: 16 }}>
        <Button disabled={busy} onClick={() => void showPreview('prune')}>按预算清理</Button>
        <Button disabled={busy} onClick={() => void showPreview('clean')}>清空可重建缓存</Button>
        <Button disabled={busy} onClick={() => void showPreview('runtime-repair')}>修复损坏运行时</Button>
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
      <Typography.Paragraph>预计处理 {preview?.targets.length ?? 0} 项，共 {bytes(preview?.estimated_bytes)}。</Typography.Paragraph>
      {(preview?.targets ?? []).slice(0, 8).map((target) => <Typography.Paragraph key={target.path}><Typography.Text copyable>{target.path}</Typography.Text> · {bytes(target.estimated_bytes)}</Typography.Paragraph>)}
      <Alert type="warning" showIcon message="确认范围" description="只处理以上可重建内容；var/data、当前有效运行时、数据库、Evidence、报告和凭据不会被删除。" />
    </Modal>
  </Space>
}
