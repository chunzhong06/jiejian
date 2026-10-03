// 环境工作面区分产品服务、托管示例与普通应用；历史入口不触发重新启动。
import { Alert, Button, Spin } from 'antd'
import { ArrowLeftOutlined, InboxOutlined } from '@ant-design/icons'
import { useEffect, useState } from 'react'
import type { ProjectDto } from '../../api/applications/projects'
import { ApiError } from '../../api/http'
import { experienceApi, type OfficialExperienceDto } from '../../api/applications/experience'
import type { SystemStatus } from '../../api/system/system'
import type { WorkspaceViewDto } from '../../api/workspace'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { OfficialSamplePanel } from './OfficialSamplePanel'
import { EnvironmentHistory } from './EnvironmentHistory'
import { ApplicationRuntimeSettings } from '../access/ControlledRuntimePanel'
import { formatTimestamp } from '../../shared/format/time'
import './environment.css'

const labels = { NOT_STARTED: '尚未启动', STARTING: '正在启动', RUNNING: '正在运行', STOPPING: '正在停止', STOPPED: '已停止', FAILED: '启动失败', UNKNOWN: '状态待核对' }
export function EnvironmentPage({ project, workspace, systemStatus, onChanged, onNavigate, onError, onRemoveCurrent }: {
  onRemoveCurrent?: () => void; project: ProjectDto | null; workspace: WorkspaceViewDto | null; systemStatus: SystemStatus
  onChanged: (value: OfficialExperienceDto) => Promise<void>; onNavigate: (path: string) => void; onError: (error: ApiError) => void
}) {
  const [value, setValue] = useState<OfficialExperienceDto | null>(null)
  const [failed, setFailed] = useState(false)
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [history, setHistory] = useState<Awaited<ReturnType<typeof experienceApi.history>> | null>(null)
  const [historyProject, setHistoryProject] = useState<string | null>(null)
  const [showOfficial, setShowOfficial] = useState(false)
  useEffect(() => {
    let current = true
    setLoading(true); setFailed(false); setValue(null); setHistory(null)
    void Promise.all([experienceApi.status(), experienceApi.history()]).then(([next, records]) => { if (current) { setValue(next); setHistory(records) } }).catch(() => { if (current) setFailed(true) }).finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [project?.project_id, revision])
  const belongs = Boolean(project && value && (value.project_id === project.project_id || value.history_project_id === project.project_id))
  const official = !project || belongs || showOfficial
  const lifecycle = value?.lifecycle ?? (value?.active ? 'RUNNING' : 'UNKNOWN')
  const stopped = lifecycle === 'STOPPED'
  const freshStartReady = official && stopped && value?.workspace_retained && value?.recovery_state === 'EXITED'
  const title = failed ? '暂时无法核对环境状态' : !official ? '核对当前应用的运行方式' : stopped ? '示例已停止，原项目记录仍可查看' : lifecycle === 'RUNNING' ? '示例正在运行' : lifecycle === 'FAILED' ? '示例启动未完成' : lifecycle === 'NOT_STARTED' ? '准备一个独立的示例环境' : '核对当前环境，再继续工作'
  if (historyProject) return <EnvironmentHistory key={historyProject} projectId={historyProject} onBack={() => setHistoryProject(null)} onError={onError}/>
  // 尚未取得归属事实时不先把示例判成普通应用，避免显示错误的操作入口。
  if (loading) return <EditorialPage label="应用环境"><EditorialHeader eyebrow="当前应用 / 运行环境" title="正在读取环境状态"/><Spin/></EditorialPage>
  return <EditorialPage label="应用环境">
    <div className="environment-toolbar"><Button type="link" icon={<ArrowLeftOutlined aria-hidden/>} onClick={() => onNavigate('/workspace')}>返回当前工作</Button><Button loading={loading} onClick={() => setRevision(n => n + 1)}>刷新环境状态</Button></div>
    <EditorialHeader eyebrow="当前应用 / 运行环境" title={title}><p className="editorial-muted">{official ? '每次启动均创建新的同步导出示例；旧项目归档，检查与证据保留。' : '可连接自行启动的应用，或确认后使用界鉴支持的运行方式。已有权限与历史保留。'}</p></EditorialHeader>
    {failed && <Alert className="flow-feedback" type="warning" showIcon message="环境信息读取失败，旧状态已撤下" description="刷新只读取当前事实，不会再次启动或重置环境。"/>}
    {!official && !failed && project && <ApplicationRuntimeSettings key={project.project_id} projectId={project.project_id} onNavigate={onNavigate}/>}
    <div className="environment-facts"><div><i data-state={systemStatus.api === 'available' ? 'ready' : 'unknown'}/><span>界鉴服务<strong>{systemStatus.api === 'available' ? '当前可访问' : '状态待核对'}</strong></span></div><div><i data-state={official && lifecycle === 'RUNNING' ? 'ready' : 'unknown'}/><span>{official ? '示例环境' : '应用连接'}<strong>{failed ? '状态未知' : official ? labels[lifecycle] : workspace?.connection.endpoint_status === 'CONFIRMED' ? '已确认地址' : '需要核对地址'}</strong></span></div><div><i data-state="history"/><span>历史事实<strong>不随当前环境状态改写</strong></span></div></div>
    {freshStartReady && <OfficialSamplePanel expanded value={value} onError={onError} onChanged={async next => { setValue(next); await onChanged(next) }}/> }
    {!freshStartReady && <section className="environment-focus" aria-label="环境下一步"><div className="environment-illustration" aria-hidden="true"><InboxOutlined/></div><div className="environment-focus-body"><p className="editorial-eyebrow">下一步</p><h2>{!official ? '确认应用正在运行' : stopped ? '重新建立示例环境' : lifecycle === 'RUNNING' ? '继续当前任务' : '核对并准备环境'}</h2><p className="editorial-muted">{!official ? '应用启动后，回到接入页核对访问地址。已有权限和历史记录继续保留。' : stopped ? '新项目需要重新确认权限、准备账号与材料。旧项目归档后仍可查看检查与修复记录。' : '只有确认操作后才改变环境，现有检查结论保持不变。'}</p>
      <div className="environment-focus-actions">
        {official && value?.history_project_id ? <Button onClick={() => setHistoryProject(value.history_project_id!)}>查看原项目历史</Button> : project && <Button onClick={() => onNavigate('/history')}>查看当前应用历史</Button>}
        {!official ? <Button type="primary" onClick={() => onNavigate('/application')}>核对应用连接</Button> : lifecycle === 'RUNNING' ? <Button type="primary" onClick={() => onNavigate('/workspace')}>返回当前任务</Button> : null}
      </div>
      {official && lifecycle !== 'RUNNING' && !failed && <OfficialSamplePanel value={value} onError={onError} onChanged={async next => { setValue(next); await onChanged(next) }}/>}
      {!official && <div className="environment-support-link"><Button type="link" onClick={() => setShowOfficial(true)}>查看官方示例环境</Button></div>}
    </div></section>}
    {official && !freshStartReady && <div className="environment-retention"><section><h3>将继续保留</h3><p>已经保存的检查结果</p><p>原问题与修复记录</p></section><section><h3>新环境需要重新准备</h3><p>应用运行条件</p><p>临时账号状态与适用材料</p></section></div>}
    {official && lifecycle === 'RUNNING' && <section className="environment-details environment-controls" aria-label="管理当前示例环境"><OfficialSamplePanel expanded value={value} onError={onError} onChanged={async next => { setValue(next); await onChanged(next) }}/></section>}
    <details className="environment-details"><summary>查看运行详情与当前限制</summary><p>{value?.last_error_code ? `最近一次环境操作未完成（${value.last_error_code}）。请先核对当前状态。` : official ? '环境操作只管理界鉴创建的实例；状态不明确时不能据此重复启动。' : '仅停止界鉴本次拥有的运行实例；外部应用进程与数据不会被清理。'}</p>{value?.origin && belongs && <p>最近一次示例地址：{value.origin}</p>}<p>本地环境是否可用，与某轮检查是否通过是不同事实。</p></details>
    {official && history && <details className="environment-details"><summary>查看环境操作记录</summary>{history.items.length ? history.items.map(item => <article key={item.operation_id}><p>{item.operation === 'stop' ? '停止环境' : '建立环境'} · {formatTimestamp(item.started_at_us)} · {item.state === 'SUCCEEDED' ? '操作已完成' : item.state === 'FAILED' ? '操作未完成' : '需要核对'}</p>{item.project_id && <Button type="link" onClick={() => setHistoryProject(item.project_id)}>查看该项目历史</Button>}</article>) : <p>尚无持久化的环境操作记录，不从旧日志猜测。</p>}{history.has_more && <p>这里只显示最近一段操作，不代表全部历史。</p>}</details>}
    {project && onRemoveCurrent && <section className="application-management"><div><h2>应用管理</h2><p>{belongs ? '移除时会一并停止属于本应用的官方实例；源码与历史检查保留。' : '移除时停止界鉴拥有的运行实例，保留源码与检查事实；外部应用进程不受影响。'}</p></div><Button danger onClick={onRemoveCurrent}>{belongs ? '停止并移除当前应用' : '移除当前应用'}</Button></section>}
  </EditorialPage>
}
