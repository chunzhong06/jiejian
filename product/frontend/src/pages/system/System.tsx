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
import {TaskSurface} from '../../shared/ui/TaskSurface'
import {Badge,ErrorNote,Loading,Notice} from '../../shared/ui/feedback'
import {Dialog} from '../../shared/ui/Dialog'
import {Field,Heading,ObjectIdentity} from '../../shared/ui/layout'
import './styles.css'

export function System({route,projectId,embedded=false}:{route:Route;projectId?:string;embedded?:boolean}){
  const [updating,setUpdating]=useState(route.query.get('view')==='update')
  // 设置工作面保持挂载；从诊断中的链接进入更新时也要同步展开状态。
  useEffect(()=>{setUpdating(route.query.get('view')==='update');if(route.query.get('view')!=='update')return;const target=document.getElementById('settings-update');target?.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});target?.focus({preventScroll:true})},[route.query.get('view')])
  return <div className="jj-system-page">{!embedded&&!updating&&<Heading title="运行与维护"/>}
    <div className={updating?undefined:"jj-system-columns"}>{!updating&&<RuntimeDetails/>}<section id="settings-update" className={updating?"jj-system-maintenance-task":"jj-system-workspace jj-system-update"} aria-labelledby={updating?undefined:"settings-update-title"} tabIndex={-1}>{!updating&&<h2 id="settings-update-title" className="jj-sr-only">版本与更新</h2>}<Updates projectId={projectId} expanded={updating} onOpen={()=>setUpdating(true)} onClose={()=>setUpdating(false)}/></section></div>
  </div>
}

function RuntimeDetails(){
  const read=useRead('system-diagnostics',systemApi.diagnostics,0,systemApi.refreshDiagnostics)
  const [error,setError]=useState<unknown>(),[copied,setCopied]=useState(false),[summaryOpen,setSummaryOpen]=useState(false)
  useEffect(()=>{if(!copied)return;const timer=setTimeout(()=>setCopied(false),2200);return()=>clearTimeout(timer)},[copied])
  const data=read.data
  const copy=async()=>{if(!data)return;setError(undefined);try{await navigator.clipboard.writeText(data.summary_text);setCopied(true)}catch{setError(new Error('未能复制，请下载诊断摘要。'))}}
  const download=()=>{if(!data)return;const url=URL.createObjectURL(new Blob([data.summary_text],{type:'text/plain;charset=utf-8'}));const anchor=document.createElement('a');anchor.href=url;anchor.download='界鉴诊断.txt';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
  // 复制反馈跟随摘要所在阅读层，避免错误出现在浮层背后的页面。
  return <section className="jj-system-workspace jj-system-diagnostics" aria-labelledby="settings-diagnostics-title"><header><div><h2 id="settings-diagnostics-title">运行诊断</h2>{data&&<p>上次核对 {new Date(data.checked_at).toLocaleString('zh-CN',{hour12:false})}</p>}</div></header>
    {Boolean(read.error||(!summaryOpen&&error))&&<div className="jj-system-feedback"><ErrorNote error={read.error??error}/></div>}
    {!data?<Loading>正在核对本机运行环境</Loading>:<>
      {data.components.length>0&&<ul className="jj-system-components" aria-label="运行组件" data-paired={data.components.length%2===0}>{data.components.map(item=><li key={item.key}><ObjectIdentity name={<span>{item.label}</span>} status={<Badge tone={item.ready?'positive':'caution'}>{item.ready?'可用':'需要检查'}</Badge>}/>{!item.ready&&<div className="jj-system-component-issue"><p>{item.key==='frontend'?(data.frontend_identity?.reason||'界面构建身份尚未确认'):item.key==='python'?(data.environment?.python?.issues?.[0]||'当前运行环境未通过核对'):item.key==='browser'?'受控检查浏览器尚不可用':'执行服务尚未就绪，检查暂不能运行'}</p></div>}</li>)}</ul>}
      {data.components.some(item=>!item.ready)&&<p className="jj-system-attention-note">先处理上方未通过核对的组件，再继续检查。</p>}
      {!data.components.length&&<p className="jj-muted">本次没有可展示的组件状态，请查看诊断摘要。</p>}
      <div className="jj-system-diagnostic-tools"><Button kind={data.components.some(item=>!item.ready)?'primary':undefined} onClick={()=>setSummaryOpen(true)}>查看诊断摘要 <ArrowRightOutlined aria-hidden="true"/></Button></div>
      {data.last_exit&&<div className="jj-system-exit"><span className="jj-small jj-muted">最近退出记录</span><Badge tone={data.last_exit.state==='STOPPED'?'positive':'caution'}>{data.last_exit.state==='STOPPED'?'已正常停止':'需要核对'}</Badge><span className="jj-muted jj-small">{new Date(data.last_exit.finished_at*1000).toLocaleString('zh-CN',{hour12:false})}</span></div>}
      {summaryOpen&&<Dialog title="诊断摘要" onClose={()=>setSummaryOpen(false)}>{Boolean(error)&&<ErrorNote error={error}/>}<pre className="jj-system-summary">{data.summary_text}</pre><div className="jj-task-actions"><Button kind="quiet" complete={copied} icon={<CopyOutlined aria-hidden="true"/>} onClick={()=>void copy()}>{copied?'已复制':'复制摘要'}</Button><Button icon={<DownloadOutlined aria-hidden="true"/>} onClick={download}>下载摘要</Button></div></Dialog>}
    </>}
  </section>
}

function Updates({projectId,expanded,onOpen,onClose}:{projectId?:string;expanded:boolean;onOpen:()=>void;onClose:()=>void}){
  const read=useRead('system-update',systemApi.updateInfo)
  const [directory,setDirectory]=useState(''),[operation,setOperation]=useState<UpdateOperation>(),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),[sent,setSent]=useState(false),[draftChanged,setDraftChanged]=useState(false)
  const current=operation??(!draftChanged?read.data?.operation:undefined)
  const pending=current&&['WAITING_FOR_EXIT','STARTING'].includes(current.phase)
  const complete=current?.phase==='READY',failed=current?.phase==='FAILED'
  const unconfirmed=sent&&current?.phase==='PREVIEWED'
  useEffect(()=>{if(current&&['WAITING_FOR_EXIT','STARTING'].includes(current.phase))onOpen()},[current?.phase])
  const changeDirectory=(value:string)=>{setDirectory(value);setOperation(undefined);setDraftChanged(true);setSent(false)}
  const chooseAnother=()=>{changeDirectory('');setError(undefined)}
  const select=async()=>{setBusy(true);setError(undefined);try{const value=await onboardingApi.selectFolder();if(value.status==='selected'&&value.path){changeDirectory(value.path)}else if(value.status==='unavailable')setError(new Error(value.message??'目录选择暂时不可用，请填写路径。'))}catch(value){setError(value)}finally{setBusy(false)}}
  const preview=async()=>{setBusy(true);setError(undefined);try{setOperation(await systemApi.previewUpdate(directory,scopedPath('/workspace',projectId)))}catch(value){setError(value)}finally{setBusy(false)}}
  const confirm=async()=>{if(!current||sent||busy)return;setBusy(true);setError(undefined);setSent(true);try{setOperation(await systemApi.confirmUpdate(current.operation_id))}catch{setError(new Error('更新结果尚未确认，请查询这次更新。版本切换会在后台继续。'))}finally{setBusy(false)}}
  const recover=async()=>{if(!current)return;setBusy(true);setError(undefined);try{setOperation(await systemApi.updateOutcome(current.operation_id));read.reload()}catch(value){setError(value)}finally{setBusy(false)}}
  const content=<>{(error??read.error)&&<ErrorNote error={error??read.error}/>} {!read.data?<Loading>正在读取版本与工作区</Loading>:<>
    <section className="jj-update-workspace">
      <header className="jj-update-current"><div>{expanded&&<span className="jj-small jj-muted">当前版本</span>}<div className="jj-update-version"><ObjectIdentity name={<strong className="jj-current-version">界鉴 {read.data.version}</strong>} status={<Badge>{read.data.portable?read.data.platform==='linux'?'Linux 运行包':'Windows 便携版':'源码运行'}</Badge>}/></div></div><details className="jj-update-location"><summary>工作区位置</summary><p>{read.data.workspace}</p></details></header>
      {expanded&&(!read.data.portable||read.data.update_supported===false?<div className="jj-update-form"><p>{read.data.portable?'当前平台请解压新运行包，并使用原工作区启动以完成兼容性核对和迁移。':'当前通过源码运行。请在源码工作区更新代码后重新运行启动入口；已有应用与报告沿用原工作区。便携包的目录切换不适用于当前运行方式。'}</p></div>:current?<>
        <div className="jj-update-result" data-phase={complete?'complete':failed?'failed':pending||sent?'pending':'preview'} key={current.phase+String(sent)}>
          <div className="jj-update-result-heading">
            <span className="jj-update-result-icon" aria-hidden="true">{complete?<CheckCircleOutlined/>:failed?<WarningOutlined/>:pending||sent?<LoadingOutlined spin/>:<DownloadOutlined/>}</span>
            <div><h2>{complete?'版本切换已完成':failed?'版本切换未完成':unconfirmed?'版本切换结果待确认':pending?current.phase==='STARTING'?'正在启动所选版本':'正在停止当前服务':'准备使用界鉴 '+current.target_version}</h2><p>{complete?'原有应用、权限规则、材料和报告已保留。':failed?'原工作区已保留，请核对新版本目录后重新预览。':unconfirmed?'查看上次更新结果，确认启动器是否已经完成版本切换。':pending?'正在切换版本，稍后会重新打开界面。':'已核对版本文件及其与工作区的兼容性。'}</p></div>
            {complete&&<ActionLink kind="primary" href={'#'+scopedPath('/workspace',projectId)}>{projectId?'返回应用':'打开工作区'} <ArrowRightOutlined aria-hidden="true"/></ActionLink>}
          </div>
          {complete?<p className="jj-update-next">继续检查前，请核对登录与证明状态。</p>:failed?current.reason&&<Notice tone="negative">{current.reason}</Notice>:pending||sent?<Button busy={busy} onClick={()=>void recover()}>查询更新结果</Button>:<>
            <p className="jj-update-path">{current.target_release}</p>
            <div className="jj-update-impact"><strong>切换时停止当前任务</strong><p>使用原工作区，登录与证明可能需要重新核对。</p></div>
            <div className="jj-update-confirm"><p>{current.workspace_upgrade?'此次切换将升级工作区结构，保留应用与报告；升级后不支持自动降级。':'请使用来源可信的运行包。文件核对不包含发布者签名认证。'}</p><Button kind="primary" busy={busy} onClick={()=>void confirm()}>停止并切换版本 <ArrowRightOutlined aria-hidden="true"/></Button></div>
          </>}
        </div>
        <footer className="jj-update-footer"><details><summary>版本切换详情</summary><dl className="jj-facts"><div><dt>版本目录</dt><dd>{current.target_release}</dd></div><div><dt>工作区</dt><dd>{current.workspace}</dd></div></dl></details>{!pending&&(!sent||complete||failed)&&<Button kind="quiet" onClick={chooseAnother}>{complete?'选择其他版本目录':'更换版本目录'}</Button>}</footer>
      </>:<div className="jj-update-form" key="directory">
        <div><p>选择完整解压的界鉴版本目录。</p></div>
        <div className="jj-update-picker"><Field label="新版本所在目录"><input value={directory} onChange={event=>changeDirectory(event.target.value)} placeholder="粘贴路径，或选择目录" disabled={busy}/></Field><Button disabled={busy} onClick={()=>void select()}>选择目录</Button></div>
        <div className="jj-update-confirm"><p>先查看新版本是否兼容，并核对将保留的工作区。确认切换后，才会停止当前服务。</p><Button kind="primary" busy={busy} disabled={!directory.trim()} onClick={()=>void preview()}>预览更新 <ArrowRightOutlined aria-hidden="true"/></Button></div>
      </div>)}
      {!expanded&&<div className="jj-task-actions"><Button kind="quiet" onClick={onOpen}>{current?'查看更新记录':'查看更新方式'} <ArrowRightOutlined aria-hidden="true"/></Button></div>}
    </section>
  </>}</>
  return expanded?<TaskSurface level={2} title="更新界鉴" onBack={onClose} backLabel="返回运行与维护">{content}</TaskSurface>:content
}
