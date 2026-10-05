// 运行环境页：展示当前实际运行时，并通过同一维护服务管理闲置运行文件。

import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { StatusBadge } from '../../shared/ui/StatusBadge'
import './runtime.css'
import { Alert, Card, Col, Descriptions, Row, Statistic, Typography } from 'antd'
import { LLMProfile } from '../../api/assistance/llm'
import { SystemStatus } from '../../api/system/system'
import { MaintenancePanel } from './MaintenancePanel'
import { frontendBuildId, frontendIdentityState } from '../../shared/runtime/buildIdentity'

function label(value: unknown) {
  const raw = String(value ?? 'unknown')
  return raw === 'available' || raw === 'running' ? '可用' : raw === 'unavailable' ? '不可用' : raw === 'stopped' ? '不可用' : '未知'
}

export function RuntimePage({ status, profiles, failed }: { status: SystemStatus; profiles: LLMProfile[]; failed: boolean }) {
  const model = failed ? '未知' : profiles.some((profile) => profile.enabled && profile.secret_configured) ? '已配置' : '未知'
  const environment = status.environment
  const python = environment?.python
  const issues = Array.isArray(python?.issues) ? python.issues : []
  return <EditorialPage label="界鉴运行与维护">
    <EditorialHeader eyebrow="界鉴自身" title="界鉴运行与维护"><p className="editorial-muted">查看界鉴的服务、执行器和浏览器组件，维护本工具的缓存与日志。</p></EditorialHeader>
    <Card title="界鉴运行状态" className="runtime-panel">
      <Typography.Paragraph type="secondary">以下信息来自当前服务进程，用于确认界鉴没有误用用户级 Python 包或另一套工具链。</Typography.Paragraph>
      {python?.user_site_on_sys_path && <Alert type="error" showIcon message="检测到用户级 Python 包来源" description="请退出界鉴并重新运行 start.cmd，让启动器恢复项目环境隔离。" />}
      {issues.length > 0 && <Alert type="warning" showIcon message="运行环境存在异常" description={issues.join('；')} />}
      {status.worker === 'unavailable' && <Alert type="info" showIcon message="检查执行器当前不可用。" description="暂时无法开始新的检查。请核对执行器状态，必要时重新启动界鉴。" />}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}><Statistic title="服务" value={label(status.api)} /></Col>
        <Col xs={24} sm={12} lg={6}><Statistic title="执行" value={label(status.worker)} /></Col>
        <Col xs={24} sm={12} lg={6}><Statistic title="浏览器" value={label(status.browser)} /></Col>
        <Col xs={24} sm={12} lg={6}><Statistic title="模型" value={model} /></Col>
      </Row>
      <details className="runtime-details"><summary>查看运行版本与组件详情</summary><Descriptions bordered size="small" column={1}>
        <Descriptions.Item label="界鉴版本">{status.version ?? '未提供'}</Descriptions.Item>
        <Descriptions.Item label="页面资源对应">{frontendIdentityState(status.frontend_identity) === 'CURRENT' ? '当前页面与服务资源一致' : frontendIdentityState(status.frontend_identity) === 'UPDATE_AVAILABLE' ? '当前页面需要刷新以加载新资源' : (status.frontend_identity?.reason ?? '服务尚未提供页面版本信息，请重启界鉴后查看')}<div className="editorial-muted">页面：{frontendBuildId?.slice(0,12) ?? '未提供'} · 服务：{status.frontend_identity?.build_id?.slice(0,12) ?? '未取得'}</div></Descriptions.Item>
        <Descriptions.Item label="运行模式">{environment?.runtime_mode === 'development' ? '源码运行' : environment?.runtime_mode ?? '未提供'} · {environment?.runtime_fingerprint ?? '无指纹'}</Descriptions.Item>
        <Descriptions.Item label="Python">{python?.version ?? '未提供'} · {python?.environment_type ?? '来源未知'}</Descriptions.Item>
        <Descriptions.Item label="Python 可执行文件"><Typography.Text copyable>{python?.executable ?? '未提供'}</Typography.Text></Descriptions.Item>
        <Descriptions.Item label="Python 环境目录"><Typography.Text copyable>{python?.prefix ?? '未提供'}</Typography.Text></Descriptions.Item>
        <Descriptions.Item label="用户级包">{python?.user_site_on_sys_path === true ? '正在使用' : python?.user_site_on_sys_path === false ? '未使用' : '未知'}</Descriptions.Item>
        <Descriptions.Item label="uv">{environment?.uv?.version ?? '未提供'} · <Typography.Text copyable>{environment?.uv?.executable ?? '未提供'}</Typography.Text></Descriptions.Item>
        <Descriptions.Item label="Node.js">{`${environment?.node?.version ?? '未提供'} · ${environment?.node?.executable ?? '未提供'} · 受控本地应用运行时`}</Descriptions.Item>
        <Descriptions.Item label="pnpm">{`${environment?.pnpm?.version ?? '未提供'} · ${environment?.pnpm?.executable ?? '未提供'}${environment?.pnpm?.required === false ? ' · 仅构建时需要' : ''}`}</Descriptions.Item>
        <Descriptions.Item label="Playwright">{environment?.playwright?.package_version ?? '未提供'} · <Typography.Text copyable>{environment?.playwright?.chromium_executable ?? '未提供'}</Typography.Text></Descriptions.Item>
        <Descriptions.Item label="前端资源">
          {environment?.frontend?.mode === 'source-build'
            ? <>源码构建 · {environment.frontend.build_state === 'reused' ? '已复用' : '已更新'} · <Typography.Text copyable>{environment.frontend.dist ?? '路径未提供'}</Typography.Text></>
            : environment?.frontend?.dependencies ?? '前端资源未确认'}
        </Descriptions.Item>
        <Descriptions.Item label="本次自动恢复任务">{status.recovered_jobs ?? '未读取'}</Descriptions.Item>
      </Descriptions></details>
      <StatusBadge kind="lifecycle" tone={python?.ok === false ? 'danger' : 'info'}>{python?.ok === false ? '环境需要处理' : '状态来自当前运行环境'}</StatusBadge>
    </Card>

    <MaintenancePanel/>

    <footer className="editorial-muted runtime-license">界面字体 MiSans · <a href={new URL('../../assets/fonts/misans/MiSans-LICENSE.pdf', import.meta.url).href} target="_blank" rel="noreferrer">字体许可</a></footer>
  </EditorialPage>
}
