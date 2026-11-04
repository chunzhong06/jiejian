import {useEffect,useState} from 'react'
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import CheckCircleOutlined from '@ant-design/icons/CheckCircleOutlined';
import CopyOutlined from '@ant-design/icons/CopyOutlined';
import DownloadOutlined from '@ant-design/icons/DownloadOutlined';
import LoadingOutlined from '@ant-design/icons/LoadingOutlined';
import WarningOutlined from '@ant-design/icons/WarningOutlined';
import {systemApi,type UpdateOperation} from '../../entities/runtime/api/system'
import {onboardingApi} from '../../entities/application/api/onboarding'
import {useRead} from '../../shared/lib/useRead'
import {scopedPath,type Route} from '../../shared/lib/navigation'
import {ActionLink,Button} from '../../shared/ui/actions'
import {Badge,ErrorNote,Loading,Notice} from '../../shared/ui/feedback'
import {Field,Heading} from '../../shared/ui/layout'
import {settingsPath} from '../../shared/lib/settings'
import './styles.css'

export function System({route,projectId,embedded=false}:{route:Route;projectId?:string;embedded?:boolean}){
  useEffect(()=>{if(route.query.get('view')!=='update')return;const target=document.getElementById('settings-update');target?.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});target?.focus({preventScroll:true})},[route.query.get('view')])
  return <div className="jj-system-page">{!embedded&&<Heading title="运行与维护"/>}
    <div className="jj-system-columns"><RuntimeDetails projectId={projectId}/><section id="settings-update" className="jj-system-workspace jj-system-update" aria-labelledby="settings-update-title" tabIndex={-1}><header><h2 id="settings-update-title">版本与更新</h2></header><Updates projectId={projectId}/></section></div>
  </div>
}

function RuntimeDetails({projectId}:{projectId?:string}){
  const read=useRead('system-diagnostics',systemApi.diagnostics,0,systemApi.refreshDiagnostics)
  const [error,setError]=useState<unknown>(),[copied,setCopied]=useState(false)
  const data=read.data
  const copy=async()=>{if(!data)return;setError(undefined);try{await navigator.clipboard.writeText(data.summary_text);setCopied(true)}catch{setError(new Error('未能复制，请下载诊断摘要。'))}}
  const download=()=>{if(!data)return;const url=URL.createObjectURL(new Blob([data.summary_text],{type:'text/plain;charset=utf-8'}));const anchor=document.createElement('a');anchor.href=url;anchor.download='界鉴诊断.txt';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
  return <section className="jj-system-workspace jj-system-diagnostics" aria-labelledby="settings-diagnostics-title"><header><div><h2 id="settings-diagnostics-title">运行诊断</h2>{data&&<p>核对于 {new Date(data.checked_at).toLocaleString('zh-CN',{hour12:false})}</p>}</div></header>
    {(error??read.error)&&<div className="jj-system-feedback"><ErrorNote error={error??read.error}/></div>}
    {!data?<Loading>正在核对本机运行环境</Loading>:<>
      <div className="jj-system-components">{data.components.map(item=><div key={item.key}>{item.ready?<CheckCircleOutlined className="jj-positive"/>:<WarningOutlined className="jj-caution"/>}<strong>{item.label}</strong><Badge tone={item.ready?'positive':'caution'}>{item.ready?'可用':'需要检查'}</Badge></div>)}</div>
      {data.components.some(item=>!item.ready)&&<footer><p>请核对不可用的组件。包内组件不完整时，请使用匹配的完整发行包。</p><ActionLink href={'#'+scopedPath(settingsPath('system','update'),projectId)}>查看版本与更新 <ArrowRightOutlined/></ActionLink></footer>}
      <div className="jj-system-diagnostic-tools"><details className="jj-system-diagnostic"><summary>诊断摘要</summary><pre>{data.summary_text}</pre></details><div className="jj-inline-actions"><Button icon={<CopyOutlined aria-hidden="true"/>} onClick={()=>void copy()}>{copied?'已复制':'复制摘要'}</Button><Button kind="quiet" icon={<DownloadOutlined aria-hidden="true"/>} onClick={download}>下载</Button></div></div>
      {data.last_exit&&<div className="jj-system-exit"><span className="jj-small jj-muted">最近确认的退出</span><Badge tone={data.last_exit.state==='STOPPED'?'positive':'caution'}>{data.last_exit.state==='STOPPED'?'已正常停止':'需要核对'}</Badge><span className="jj-muted jj-small">{new Date(data.last_exit.finished_at*1000).toLocaleString('zh-CN',{hour12:false})}</span></div>}
    </>}
  </section>
}

function Updates({projectId}:{projectId?:string}){
  const read=useRead('system-update',systemApi.updateInfo)
  const [directory,setDirectory]=useState(''),[operation,setOperation]=useState<UpdateOperation>(),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),[sent,setSent]=useState(false),[draftChanged,setDraftChanged]=useState(false)
  const current=operation??(!draftChanged?read.data?.operation:undefined)
  const pending=current&&['WAITING_FOR_EXIT','STARTING'].includes(current.phase)
  const complete=current?.phase==='READY',failed=current?.phase==='FAILED'
  const unconfirmed=sent&&current?.phase==='PREVIEWED'
  const changeDirectory=(value:string)=>{setDirectory(value);setOperation(undefined);setDraftChanged(true);setSent(false)}
  const chooseAnother=()=>{changeDirectory('');setError(undefined)}
  const select=async()=>{setBusy(true);setError(undefined);try{const value=await onboardingApi.selectFolder();if(value.status==='selected'&&value.path){changeDirectory(value.path)}else if(value.status==='unavailable')setError(new Error(value.message??'目录选择暂时不可用，请填写路径。'))}catch(value){setError(value)}finally{setBusy(false)}}
  const preview=async()=>{setBusy(true);setError(undefined);try{setOperation(await systemApi.previewUpdate(directory,scopedPath('/workspace',projectId)))}catch(value){setError(value)}finally{setBusy(false)}}
  const confirm=async()=>{if(!current||sent||busy)return;setBusy(true);setError(undefined);setSent(true);try{setOperation(await systemApi.confirmUpdate(current.operation_id))}catch{setError(new Error('更新请求结果尚未确认，请查询原操作；启动器会继续交接。'))}finally{setBusy(false)}}
  const recover=async()=>{if(!current)return;setBusy(true);setError(undefined);try{setOperation(await systemApi.updateOutcome(current.operation_id));read.reload()}catch(value){setError(value)}finally{setBusy(false)}}
  return <>{(error??read.error)&&<ErrorNote error={error??read.error}/>} {!read.data?<Loading>正在读取版本与工作区</Loading>:<>
    <section className="jj-update-workspace">
      <header className="jj-update-current"><div><span className="jj-small jj-muted">当前版本</span><div className="jj-update-version"><strong className="jj-current-version">界鉴 {read.data.version}</strong><Badge>{read.data.portable?'Windows 便携版':'源码运行'}</Badge></div></div><details className="jj-update-location"><summary>工作区位置</summary><p>{read.data.workspace}</p></details></header>
      {!read.data.portable?<div className="jj-update-form"><p>当前为源码运行。本地发行切换适用于 Windows 便携版。</p></div>:current?<>
        <div className="jj-update-result" data-phase={complete?'complete':failed?'failed':pending||sent?'pending':'preview'} key={current.phase+String(sent)}>
          <div className="jj-update-result-heading">
            <span className="jj-update-result-icon" aria-hidden="true">{complete?<CheckCircleOutlined/>:failed?<WarningOutlined/>:pending||sent?<LoadingOutlined spin/>:<DownloadOutlined/>}</span>
            <div><h2>{complete?'版本切换已完成':failed?'版本切换未完成':unconfirmed?'交接状态待确认':pending?current.phase==='STARTING'?'正在启动所选发行':'正在停止当前服务':'准备使用界鉴 '+current.target_version}</h2><p>{complete?'原有应用、权限规则、材料和报告已保留。':failed?'原工作区保留，请核对发行目录后重新预览。':unconfirmed?'查询原操作，核对启动器的实际交接状态。':pending?'启动器正在交接，稍后会重新打开界面。':'发行文件和工作区兼容性已核对。'}</p></div>
            {complete&&<ActionLink kind="primary" href={'#'+scopedPath('/workspace',projectId)}>{projectId?'返回应用':'打开工作区'} <ArrowRightOutlined aria-hidden="true"/></ActionLink>}
          </div>
          {complete?<p className="jj-update-next">继续检查前，请核对登录与证明状态。</p>:failed?current.reason&&<Notice tone="negative">{current.reason}</Notice>:pending||sent?<Button busy={busy} onClick={()=>void recover()}>查询更新结果</Button>:<>
            <p className="jj-update-path">{current.target_release}</p>
            <div className="jj-update-impact"><strong>切换时停止当前任务</strong><p>使用原工作区，登录与证明可能需要重新核对。</p></div>
            <div className="jj-update-confirm"><p>{current.workspace_upgrade?'此次切换将升级工作区结构，保留应用与报告；升级后不支持自动降级。':'请确认发行包来源可信，文件核对不代表发布者签名认证。'}</p><Button kind="primary" busy={busy} onClick={()=>void confirm()}>停止并切换版本 <ArrowRightOutlined aria-hidden="true"/></Button></div>
          </>}
        </div>
        <footer className="jj-update-footer"><details><summary>交接详情</summary><dl><div><dt>发行目录</dt><dd>{current.target_release}</dd></div><div><dt>工作区</dt><dd>{current.workspace}</dd></div></dl></details>{!pending&&(!sent||complete||failed)&&<Button kind="quiet" onClick={chooseAnother}>{complete?'选择其他发行目录':'更换发行目录'}</Button>}</footer>
      </>:<div className="jj-update-form" key="directory">
        <div><p>选择完整解压的界鉴发行目录。</p></div>
        <div className="jj-update-picker"><Field label="新版本所在目录"><input value={directory} onChange={event=>changeDirectory(event.target.value)} placeholder="粘贴路径，或选择目录" disabled={busy}/></Field><Button disabled={busy} onClick={()=>void select()}>选择目录</Button></div>
        <div className="jj-update-confirm"><p>先核对兼容性，确认后才会停止当前服务。</p><Button kind="primary" busy={busy} disabled={!directory.trim()} onClick={()=>void preview()}>预览更新 <ArrowRightOutlined aria-hidden="true"/></Button></div>
      </div>}
    </section>
  </>}</>
}
