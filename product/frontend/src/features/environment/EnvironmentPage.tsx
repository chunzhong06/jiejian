// 应用与环境展示运行事实；继续原项目和重新开始各自明确，保存记录不增加历史入口。
import { LoadingState } from '../../shared/ui/LoadingState'
import { Alert, Button } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { useEffect, useState } from 'react'
import type { ProjectDto } from '../../api/applications/projects'
import { ApiError } from '../../api/http'
import { experienceApi, type OfficialExperienceDto } from '../../api/applications/experience'
import type { WorkspaceViewDto } from '../../api/workspace'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { OfficialSamplePanel } from './OfficialSamplePanel'
import { ApplicationRuntimeSettings } from '../access/ControlledRuntimePanel'
import './environment.css'

const labels = { NOT_STARTED: '尚未启动', STARTING: '正在启动', RUNNING: '正在运行', STOPPING: '正在停止', STOPPED: '已停止', FAILED: '启动失败', UNKNOWN: '状态待核对' }
export function EnvironmentPage({ project, workspace, onChanged, onNavigate, onError, onRemoveCurrent }: {
  onRemoveCurrent?: () => void; project: ProjectDto | null; workspace: WorkspaceViewDto | null
  onChanged: (value: OfficialExperienceDto) => Promise<void>; onNavigate: (path: string) => void; onError: (error: ApiError) => void
}) {
  const [value, setValue] = useState<OfficialExperienceDto | null>(null)
  const [failed, setFailed] = useState(false)
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [showOfficial, setShowOfficial] = useState(false)
  useEffect(() => {
    let current = true
    setLoading(true); setFailed(false); setValue(null)
    void experienceApi.status().then(next => { if (current) setValue(next) }).catch(() => { if (current) setFailed(true) }).finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [project?.project_id, revision])
  const belongs = Boolean(project && value && (value.project_id === project.project_id || value.history_project_id === project.project_id))
  const official = !project || belongs || showOfficial
  const lifecycle = value?.lifecycle ?? (value?.active ? 'RUNNING' : 'UNKNOWN')
  const stopped = lifecycle === 'STOPPED'
  const canResume=stopped&&value?.runtime_kind==='NODE_ESM'&&value.workspace_retained&&value.recovery_state==='EXITED'
  const title = failed ? '暂时无法核对环境状态' : !official ? '核对当前应用的运行方式' : canResume ? '示例已停止，可继续上次项目' : stopped ? '示例已停止，可重新开始' : lifecycle === 'RUNNING' ? '示例正在运行' : lifecycle === 'FAILED' ? '示例启动未完成' : lifecycle === 'NOT_STARTED' ? '准备一个独立的示例环境' : '核对当前环境，再继续工作'
  // 尚未取得归属事实时不先把示例判成普通应用，避免显示错误的操作入口。
  if (loading) return <EditorialPage label="应用与环境" width="welcome"><EditorialHeader eyebrow={project?.name || '界鉴设置'} title="应用与环境"/><div className="environment-toolbar"><Button type="link" icon={<ArrowLeftOutlined aria-hidden/>} onClick={() => onNavigate('/workspace')}>返回概览</Button></div><LoadingState>正在读取应用运行状态。</LoadingState></EditorialPage>
  return <EditorialPage label="应用与环境" width="welcome">
    <div className="environment-toolbar"><Button type="link" icon={<ArrowLeftOutlined aria-hidden/>} onClick={() => onNavigate('/workspace')}>返回概览</Button><Button loading={loading} onClick={() => setRevision(n => n + 1)}>刷新应用运行状态</Button></div>
    <EditorialHeader eyebrow={project?.name || '界鉴设置'} title="应用与环境"><p className="editorial-muted">{title}。</p></EditorialHeader>
    {failed && <Alert className="flow-feedback" type="warning" showIcon message="环境信息读取失败，旧状态已撤下" description="刷新只读取当前事实，不会再次启动或重置环境。"/>}
    {!official && !failed && project && <ApplicationRuntimeSettings key={project.project_id} projectId={project.project_id} onNavigate={onNavigate}/>}
    <div className="environment-facts"><div><i data-state="history"/><span>待测应用<strong>{project?.name || (official ? '官方示例' : '尚未选择')}</strong></span></div><div><i data-state={official && lifecycle === 'RUNNING' ? 'ready' : 'unknown'}/><span>{official ? '示例环境' : '应用连接'}<strong>{failed ? '状态未知' : official ? labels[lifecycle] : workspace?.connection.endpoint_status === 'CONFIRMED' ? '已确认地址' : '需要核对地址'}</strong></span></div><div><i data-state="history"/><span>历史事实<strong>不随当前环境状态改写</strong></span></div></div>
    <section className="environment-focus" aria-label="环境下一步">
      <div className="environment-focus-copy"><p className="editorial-eyebrow">下一步</p><h2>{!official ? '确认应用正在运行' : lifecycle === 'RUNNING' ? '继续当前任务' : canResume?'继续上次示例':'从全新示例开始'}</h2><p className="editorial-muted">{!official ? '应用启动后，回到接入页核对访问地址。' : lifecycle === 'RUNNING' ? '回到总览，继续确认权限、准备材料与检查。' : canResume?'保留上次的项目、代码与权限，重新核对登录和受实例变化影响的材料。':'启动独立的新项目，再确认权限、准备账号与材料。已有记录会保留。'}</p></div>
      <div className="environment-focus-actions">
        {!official ? <Button type="primary" onClick={() => onNavigate('/application')}>核对应用连接</Button> : lifecycle === 'RUNNING' ? <Button type="primary" onClick={() => onNavigate('/workspace')}>返回当前任务</Button> : !failed && <OfficialSamplePanel compact value={value} onError={onError} onChanged={async next => { setValue(next); await onChanged(next) }}/>}
        {!official && <Button type="link" onClick={() => setShowOfficial(true)}>查看官方示例环境</Button>}
      </div>
    </section>
    {official && lifecycle === 'RUNNING' && <section className="environment-details environment-controls" aria-label="管理当前示例环境"><OfficialSamplePanel expanded value={value} onError={onError} onChanged={async next => { setValue(next); await onChanged(next) }}/></section>}
    <details className="environment-details"><summary>查看运行详情与当前限制</summary><p>{value?.last_error_code ? `最近一次环境操作未完成（${value.last_error_code}）。请先核对当前状态。` : official ? '环境操作只管理界鉴创建的实例；状态不明确时不能据此重复启动。' : '仅停止界鉴本次拥有的运行实例；外部应用进程与数据不会被清理。'}</p>{value?.origin && belongs && <p>最近一次示例地址：{value.origin}</p>}<p>本地环境是否可用，与某轮检查是否通过是不同事实。</p></details>

    {project && onRemoveCurrent && <section className="application-management"><div><h2>移除应用</h2><p>{belongs ? '移除时会一并停止属于本应用的官方实例；源码、权限规则、候选与检查历史保留；再次接入时可选择恢复或全新接入。' : '移除时停止界鉴拥有的运行实例，保留源码、权限规则、候选与检查历史；再次接入时可选择恢复或全新接入。外部应用进程不受影响。'}</p></div><Button danger onClick={onRemoveCurrent}>{belongs ? '停止并移除当前应用' : '移除当前应用'}</Button></section>}
  </EditorialPage>
}
