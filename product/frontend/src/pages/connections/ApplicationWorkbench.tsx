import {Dialog} from '../../shared/ui/Dialog'
import {TaskSurface} from '../../shared/ui/TaskSurface'
import {useWorkflow} from '../../shared/lib/workflow'
import {useCallback,useRef,useState} from 'react'
import {workbenchApi,type ApplicationEnvironment,type TargetScope} from '../../entities/application/api/workbench'
import {projectsApi,type ProjectDto} from '../../entities/application/api/projects'
import {selectFolderPath} from '../../entities/application/api/onboarding'
import {DirectoryField} from '../../shared/ui/DirectoryField'
import {useRead} from '../../shared/lib/useRead'
import {operationId,readPending,savePending} from '../../shared/lib/operations'
import {go,readRoute,returnDestination,returnDestinationLabel,withReturnDestination,scopedPath} from '../../shared/lib/navigation'
import {Button,ActionLink} from '../../shared/ui/actions'
import {Heading,Field} from '../../shared/ui/layout'
import {Badge,ErrorNote,Loading} from '../../shared/ui/feedback'
import {routePage} from '../../shared/lib/routePage'
import {assertProject} from '../../shared/model/page'
import {Tabs} from '../../shared/ui/Tabs'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import './workbench.css'

const SourceLibrary=routePage(()=>import('./SourceLibrary').then(module=>({default:module.SourceLibrary})),'/application')
const Connect=routePage(()=>import('./Connect').then(module=>({default:module.Connect})),'/application')
const Understanding=routePage(()=>import('./Understanding').then(module=>({default:module.Understanding})),'/application')

export function ApplicationWorkbench({selected,existingProjectId,onChanged}:{selected?:ProjectDto;existingProjectId?:string;onChanged:(id:string)=>void}) {
  const workflow=useWorkflow(),route=workflow?.route??readRoute(),origin=returnDestination(route.query.get('return_to'))
  const requestedView=route.query.get('view')??'environment'
  const view=['environment','sources','source','business'].includes(requestedView)?requestedView:'environment'
  const state=useRead(selected&&(view==='environment'||view==='source')?'application-environments:'+selected.project_id:null,signal=>selected?workbenchApi.environments(selected.project_id,signal):Promise.resolve(null))
  const pendingKey='jiejian.application.create'
  const [pending,setPending]=useState(()=>readPending<{operation:string;name:string}>(pendingKey))
  const [name,setName]=useState(''),[environmentName,setEnvironmentName]=useState('测试环境'),[address,setAddress]=useState(''),[deployment,setDeployment]=useState('')
  const [sourceDirectory,setSourceDirectory]=useState('')
  const [maxRequests,setMaxRequests]=useState(64),[environmentTarget,setEnvironmentTarget]=useState<TargetScope>()
  const [environmentEditing,setEnvironmentEditing]=useState(false)
  const [environmentRevision,setEnvironmentRevision]=useState(0)
  const [environmentId,setEnvironmentId]=useState(()=> 'env_'+operationId())
  const [busy,setBusy]=useState(false),[errors,setErrors]=useState<Record<string,unknown>>({})
  const errorScope=(selected?.project_id??'create')+':'+view
  const error=errors[errorScope]
  // 迟到的失败仍归发起它的工作面，不覆盖其他页签的当前任务。
  const setError=useCallback((value:unknown)=>setErrors(current=>({...current,[errorScope]:value})),[errorScope])
  const guard=useRef(false)
  const act=async(task:()=>Promise<void>)=>{if(guard.current)return;guard.current=true;setBusy(true);setError(undefined);try{await task()}catch(value){setError(value)}finally{guard.current=false;setBusy(false)}}
  const current=state.data
  const source=useRead(selected&&current?.source_available&&view==='environment'?'application-source-summary:'+selected.project_id+':'+current.revision:null,async()=>{
    const value=await projectsApi.understanding(selected!.project_id);assertProject(value.project_id,selected!.project_id);return value
  })
  // 当前采用的修订可能早于列表里的最新配置，仍保留其独立的使用事实。
  const environments=current?[...(current.active_environment&&!current.environments.some(item=>item.configuration.environment_id===current.active_environment!.environment_id&&item.configuration.revision===current.active_environment!.revision)?[current.active_environment]:[]),...current.environments.map(item=>item.configuration)]:[]
  const create=()=>void act(async()=>{
    const input=pending??{operation:operationId(),name:name.trim()}
    savePending(pendingKey,input);setPending(input)
    const existing=pending?(await projectsApi.projects()).find(item=>item.project_id==='app_'+input.operation):undefined
    if(existing&&existing.name!==input.name)throw new Error('原操作已对应其他应用名称，请查看已有工作区。')
    const project=existing??await workbenchApi.create(input.operation,input.name)
    savePending(pendingKey,undefined);setPending(undefined);onChanged(project.project_id)
  })
  if(!selected){
    const body=<><p>保存应用名称后，继续填写访问地址。需要从代码整理业务或启动程序时，再补充源码。</p><Field label="应用名称"><input value={pending?.name??name} disabled={Boolean(pending)} onChange={event=>setName(event.target.value)} placeholder="例如：订单与结算系统"/></Field>{pending&&<p>上次添加尚未确认。继续后会先核对原请求对应的应用。</p>}{Boolean(error)&&<ErrorNote error={error}/>}</>;
    const action=<Button kind="primary" busy={busy} disabled={!pending&&!name.trim()} onClick={create}>{pending?'继续上次添加':'添加并配置连接'}</Button>;
    const close=()=>go('/workspace',existingProjectId);
    return existingProjectId?<><Heading title="应用与来源"/><Dialog title="添加要检查的应用" onClose={close} closeDisabled={busy} actions={<><Button disabled={busy} onClick={close}>取消</Button>{action}</>}>{body}</Dialog></>:<TaskSurface title="添加要检查的应用" onBack={close} backLabel="返回开始页" actions={action}>{body}</TaskSurface>;
  }
  const navigateView=(value:string)=>{const path='/application?'+new URLSearchParams({view:value,...(route.query.has('runtime_method')?{runtime_method:route.query.get('runtime_method')!}:{})});(workflow?.open??go)(origin?withReturnDestination(path,origin):path,selected.project_id)}
  const attachment=<section className="jj-source-attachment" aria-labelledby="source-attachment-title">
    <header><h2 id="source-attachment-title">为当前应用补充源码</h2>{view==='source'&&<p>“{selected.name??'当前应用'}”已建立{(current?.active_environment?.target.base_url??current?.confirmed_endpoint)&&<>，检查地址为 <span className="jj-mono">{current?.active_environment?.target.base_url??current?.confirmed_endpoint}</span></>}。</p>}<p>需要从代码整理业务线索，或由界鉴启动应用时，可以补充源码。已运行的应用可直接通过检查地址连接。</p></header>
    <DirectoryField label="这个应用的源码目录" value={sourceDirectory} busy={busy} onValueChange={setSourceDirectory} onBrowse={()=>void act(async()=>{const path=await selectFolderPath();if(path)setSourceDirectory(path)})} hint="选择本机项目根目录，也可以粘贴完整路径。选择本身不会读取或启动源码。"/>
    <footer><p>补充后，再确认源码读取范围与运行方式。</p><Button kind="primary" busy={busy} disabled={!sourceDirectory.trim()} onClick={()=>void act(async()=>{await workbenchApi.attachSource(selected.project_id,sourceDirectory,current!.revision);await state.reload();onChanged(selected.project_id)})}>补充源码目录</Button></footer>
  </section>
  return <>{origin&&<div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(origin,selected.project_id)} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}{origin.startsWith('/preparation?')&&new URLSearchParams(origin.split('?')[1]).has('configure')?'返回结果判断草稿':returnDestinationLabel(origin)}</ActionLink></div>}<Heading title="应用与来源"/>
    <section className="jj-application-browser" data-view={view}>
      <Tabs label="应用资料" value={view==='source'?'environment':view} panelId="application-panel" idPrefix="application" className="jj-application-tabs" items={[{value:'environment',label:'应用连接'},{value:'sources',label:'接口来源'},{value:'business',label:'业务角色与操作'}]} onValueChange={navigateView}/>
      {Boolean(error)&&<ErrorNote error={error}/>}
      <div id="application-panel" role="tabpanel" aria-labelledby={'application-'+(view==='source'?'environment':view)} className="jj-application-content" key={view}>
    {view==='sources'?<SourceLibrary projectId={selected.project_id}/>:view==='business'?<Understanding embedded projectId={selected.project_id}/>:state.loading&&!current?<Loading/>:!current?<ErrorNote error={state.error}/>:view==='source'?<><div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={()=>navigateView('environment')}>返回应用连接</Button></div>{current.source_available?<Connect embedded selected={selected} onChanged={onChanged} onError={setError}/>:attachment}</>:<>
      <div className="jj-application-connections"><section className="jj-environments" aria-labelledby="connection-address-title"><div className="jj-connection-introduction"><h2 id="connection-address-title">检查地址</h2><p>填写应用的本机访问地址，作为登录、录制和检查的目标。保存后，选择要使用的连接，再核对本次账号和材料。</p></div>
        {current.environments.length>0&&!environmentEditing&&<>
          <header className="jj-environment-toolbar"><p>{current.environments.length} 个已保存连接</p>{!environmentEditing&&<Button onClick={()=>{setEnvironmentId('env_'+operationId());setEnvironmentRevision(0);setEnvironmentName('测试环境');setAddress('');setDeployment('');setMaxRequests(64);setEnvironmentTarget(undefined);setEnvironmentEditing(true)}}>添加连接</Button>}</header>
          {!environmentEditing&&!current.active_environment&&current.confirmed_endpoint&&<div className="jj-environment-context"><span>当前运行地址</span><code>{current.confirmed_endpoint}</code><span className="jj-small jj-muted">尚未选择检查连接</span></div>}
          <div className="jj-environment-catalog" aria-label="已保存的连接">{environments.map(environment=>{
            const active=current.active_environment?.environment_id===environment.environment_id&&current.active_environment.revision===environment.revision
            return <section className="jj-environment-card" key={environment.environment_id+':'+environment.revision}>
              <header><div className="jj-object-line"><h3>{environment.name}</h3>{active&&<Badge tone="accent">当前使用</Badge>}</div>{active&&<div className="jj-environment-reachability"><span>地址状态</span><Badge tone={current.endpoint_reachable===false?'caution':current.endpoint_reachable?'positive':'neutral'}>{current.endpoint_reachable===false?'未连通':current.endpoint_reachable?'最近核验可达':'尚未核验'}</Badge></div>}</header>
              <div className="jj-environment-details"><p className="jj-environment-address jj-mono">{environment.target.base_url}</p>{environment.deployment_label&&<dl className="jj-facts jj-environment-facts"><div><dt>部署说明</dt><dd>{environment.deployment_label}</dd></div></dl>}</div>
              <footer><Button kind="quiet" disabled={busy} onClick={()=>{setEnvironmentId(environment.environment_id);setEnvironmentRevision(environment.revision);setEnvironmentName(environment.name);setAddress(environment.target.base_url);setDeployment(environment.deployment_label??'');setMaxRequests(environment.target.max_requests??64);setEnvironmentTarget(environment.target);setEnvironmentEditing(true)}}>编辑</Button>{active?<Button busy={busy} onClick={()=>void act(async()=>{await projectsApi.confirmEndpoint(selected.project_id,environment.target.base_url,current.revision);state.reload();onChanged(selected.project_id)})}>检查地址是否可访问</Button>:<Button kind="primary" busy={busy} onClick={()=>void act(async()=>{await workbenchApi.activateEnvironment(selected.project_id,environment.environment_id,environment.revision,current.revision);state.reload();onChanged(selected.project_id)})}>使用此连接</Button>}</footer>
            </section>
          })}</div>
        </>}
        {(environmentEditing||!current.environments.length)&&<section className="jj-environment-form" aria-label={environmentRevision?'修改检查连接':'添加连接'}>
          <header><h2>{environmentRevision?'修改检查连接':'添加连接'}</h2><p>保存应用地址和本次请求上限，便于在不同连接之间切换。</p></header>
          {!current.active_environment&&current.confirmed_endpoint&&<dl className="jj-facts jj-environment-current"><dt>当前运行地址</dt><dd><code>{current.confirmed_endpoint}</code><span>尚未选择检查连接</span></dd></dl>}
          <div className="jj-environment-fields">
            <Field label="连接名称"><input value={environmentName} onChange={event=>setEnvironmentName(event.target.value)}/></Field>
            <Field label="应用地址" hint="仅填写本机 IPv4 的 HTTP/HTTPS 地址，不含路径、参数或凭据。"><input value={address} onChange={event=>setAddress(event.target.value)} placeholder="http://127.0.0.1:8080"/></Field>
            <Field label="部署说明（可选）" hint="用于区分分支或构建，不代表已核对部署版本。"><input value={deployment} onChange={event=>setDeployment(event.target.value)} placeholder="例如：测试分支 · 本周构建"/></Field>
            <Field label="每次检查请求上限" hint="计算对应用的身份核验、业务操作和恢复请求；范围为 1～500，保存并使用此连接后生效。"><input type="number" min={1} max={500} step={1} value={Number.isFinite(maxRequests)?maxRequests:''} onChange={event=>setMaxRequests(event.target.valueAsNumber)}/></Field>
          </div>
          <footer><p>保存后可选择使用此连接；切换连接时，需要重新核对账号和材料。保存本身不会访问应用。</p><div>{current.environments.length>0&&<Button disabled={busy} onClick={()=>setEnvironmentEditing(false)}>取消编辑</Button>}<Button kind="primary" busy={busy} disabled={!environmentName.trim()||!address.trim()||!Number.isInteger(maxRequests)||maxRequests<1||maxRequests>500} onClick={()=>void act(async()=>{
            const url=new URL(address.trim());if(url.pathname!=='/'||url.search||url.hash||url.username||url.password)throw new Error('请填写不含路径、参数或凭据的应用地址。')
            const origin=url.origin,port=Number(url.port||(url.protocol==='https:'?443:80))
            const configuration:ApplicationEnvironment={environment_id:environmentId,revision:environmentRevision+1,name:environmentName.trim(),target:{...environmentTarget,base_url:origin,allowed_origins:[origin],allowed_hosts:[url.hostname],allowed_ports:[port],allow_private_network:true,max_requests:maxRequests},deployment_label:deployment.trim()||null,deployment_verification:'UNVERIFIED'}
            await workbenchApi.saveEnvironment(selected.project_id,configuration,environmentRevision);state.reload();setEnvironmentId('env_'+operationId());setEnvironmentRevision(0);setAddress('');setDeployment('');setEnvironmentEditing(false)
          })}>保存连接</Button></div></footer>
        </section>}
        {state.error&&<ErrorNote error={state.error}/>}
      </section>
      <div className="jj-application-source-summary">{current.source_available?<section className="jj-source-summary" aria-labelledby="connection-source-title"><header><h2 id="connection-source-title">本地源码</h2><p>检查地址用于访问运行中的应用。关联源码后，可以整理业务线索，或配置由界鉴启动测试实例。</p></header>{source.loading?<Loading/>:source.data?<><p className="jj-path">{source.data.source_root}</p><dl className="jj-facts"><div><dt>源码读取</dt><dd>{source.data.source_analysis_authorized?'已授权':'尚未授权'}</dd></div><div><dt>业务线索</dt><dd>{source.data.analysis_completed_at_us?'已识别，可到业务角色与操作核对':'尚未读取源码'}</dd></div></dl></>:<ErrorNote error={source.error}/>}<footer><Button onClick={()=>navigateView('source')}>源码与运行设置</Button></footer></section>:attachment}</div>
      </div>
    </>}
      </div>
    </section>
  </>
}
