import {markMilestone,useMilestone} from '../../shared/lib/milestone'
import {PendingRecovery} from '../../shared/ui/PendingRecovery'
import {Dialog} from '../../shared/ui/Dialog'
import {TaskSurface} from '../../shared/ui/TaskSurface'
import {editorDraft,rememberEditorDraft,editorDraftGeneration,clearSubmittedDraft,useDraftProtection} from '../../entities/runtime/model/handoff'
import {useWorkflow} from '../../shared/lib/workflow'
import {useCallback,useEffect,useRef,useState} from 'react'
import {workbenchApi,type ApplicationEnvironment,type EnvironmentImpact,type TargetScope} from '../../entities/application/api/workbench'
import {projectsApi,type ProjectDto} from '../../entities/application/api/projects'
import {selectFolderPath} from '../../entities/application/api/onboarding'
import {DirectoryField} from '../../shared/ui/DirectoryField'
import {useRead} from '../../shared/lib/useRead'
import {operationId,readPending,savePending,notAccepted,isOperationId} from '../../shared/lib/operations'
import {go,readRoute,returnDestination,returnDestinationLabel,withReturnDestination,scopedPath} from '../../shared/lib/navigation'
import {Button,ActionLink} from '../../shared/ui/actions'
import {date} from '../../shared/lib/format'
import {Heading,Field} from '../../shared/ui/layout'
import {Badge,ErrorNote,Loading} from '../../shared/ui/feedback'
import {routePage} from '../../shared/lib/routePage'
import {assertProject} from '../../shared/model/page'
import {Tabs} from '../../shared/ui/Tabs'
import {applicationSections} from '../../shared/ui/SectionNavigation'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import './workbench.css'

// 外层已经拥有应用分类；内部模块失败只替换内容，不再复制同一组导航。
const SourceLibrary=routePage(()=>import('./SourceLibrary').then(module=>({default:module.SourceLibrary})),'/application',{embedded:true})
const Connect=routePage(()=>import('./Connect').then(module=>({default:module.Connect})),'/application',{embedded:true})
const Understanding=routePage(()=>import('./Understanding').then(module=>({default:module.Understanding})),'/application',{embedded:true})

export function ApplicationWorkbench({selected,existingProjectId,onChanged}:{selected?:ProjectDto;existingProjectId?:string;onChanged:(id:string)=>void}) {
  const workflow=useWorkflow(),route=workflow?.route??readRoute(),origin=returnDestination(route.query.get('return_to'))
  const requestedView=route.query.get('view')??'environment'
  const view=['environment','sources','source','business'].includes(requestedView)?requestedView:'environment'
  const state=useRead(selected&&(view==='environment'||view==='source')?'application-environments:'+selected.project_id:null,signal=>selected?workbenchApi.environments(selected.project_id,signal):Promise.resolve(null))
  const pendingKey='jiejian.application.create'
  const [pending,setPending]=useState(()=>readPending<{operation:string;name:string}>(pendingKey,(value):value is {operation:string;name:string}=>Boolean(value)&&typeof value==='object'&&isOperationId((value as {operation?:unknown}).operation)&&typeof (value as {name?:unknown}).name==='string'&&Array.from((value as {name:string}).name).length<=128))
  const [nameError,setNameError]=useState<string>(),nameInput=useRef<HTMLInputElement>(null)
  const draftKey='environment-editor:'+(selected?.project_id??'new');
  const saved=useRef(editorDraft<{environmentName:string;address:string;deployment:string;sourceDirectory:string;maxRequests:number;environmentTarget?:TargetScope;environmentEditing:boolean;environmentRevision:number;environmentId:string;basis?:number}>(draftKey,selected?.project_id??'new')).current;
  const [draftBasis,setDraftBasis]=useState<number|undefined>(saved?.basis);
  const [name,setName]=useState(''),[environmentName,setEnvironmentName]=useState(saved?.environmentName??'测试环境'),[address,setAddress]=useState(saved?.address??''),[deployment,setDeployment]=useState(saved?.deployment??'')
  const [sourceDirectory,setSourceDirectory]=useState(saved?.sourceDirectory??'')
  const [maxRequests,setMaxRequests]=useState(saved?.maxRequests??64),[environmentTarget,setEnvironmentTarget]=useState<TargetScope|undefined>(saved?.environmentTarget)
  const [environmentEditing,setEnvironmentEditing]=useState(saved?.environmentEditing??false)
  const [environmentRevision,setEnvironmentRevision]=useState(saved?.environmentRevision??0)
  const [environmentId,setEnvironmentId]=useState(()=>saved?.environmentId??'env_'+operationId())
  const [busy,setBusy]=useState(false),[errors,setErrors]=useState<Record<string,unknown>>({})
  const errorScope=(selected?.project_id??'create')+':'+view
  const alive=useRef(true),liveScope=useRef(errorScope);liveScope.current=errorScope
  useEffect(()=>{alive.current=true;return()=>{alive.current=false}},[])
  const changed=(id:string)=>{if(alive.current&&liveScope.current===errorScope)onChanged(id)}
  const [impact,setImpact]=useState<EnvironmentImpact>()
  const [runtimeFocused,setRuntimeFocused]=useState(false)
  const dirty=Boolean(sourceDirectory||environmentEditing&&(address||deployment||environmentRevision))
  useDraftProtection(dirty)
  useEffect(()=>{if(state.data&&draftBasis===undefined)setDraftBasis(state.data.revision);if(dirty)rememberEditorDraft(draftKey,{environmentName,address,deployment,sourceDirectory,maxRequests,environmentTarget,environmentEditing,environmentRevision,environmentId,basis:draftBasis},selected?.project_id??'new')},[environmentName,address,deployment,sourceDirectory,maxRequests,environmentTarget,environmentEditing,environmentRevision,environmentId,state.data?.revision,draftBasis])
  const error=errors[errorScope]
  // 迟到的失败仍归发起它的工作面，不覆盖其他页签的当前任务。
  const setError=useCallback((value:unknown)=>setErrors(current=>({...current,[errorScope]:value})),[errorScope])
  const guard=useRef(false)
  const act=async(task:()=>Promise<void>)=>{if(guard.current)return;guard.current=true;setBusy(true);setError(undefined);try{await task()}catch(value){setError(value)}finally{guard.current=false;setBusy(false)}}
  const current=state.data
  const completion=useMilestone<HTMLDivElement>('connection:'+selected?.project_id+':'+(current?.active_environment?current.active_environment.environment_id+'@'+current.active_environment.revision:'new'),Boolean(current),'connection')
  const source=useRead(selected&&current?.source_available&&view==='environment'?'application-source-summary:'+selected.project_id+':'+current.revision:null,async()=>{
    const value=await projectsApi.understanding(selected!.project_id);assertProject(value.project_id,selected!.project_id);return value
  })
  // 当前采用的修订可能早于列表里的最新配置，仍保留其独立的使用事实。
  const environments=current?[...(current.active_environment&&!current.environments.some(item=>item.configuration.environment_id===current.active_environment!.environment_id&&item.configuration.revision===current.active_environment!.revision)?[current.active_environment]:[]),...current.environments.map(item=>item.configuration)]:[]
  const create=()=>void act(async()=>{
    if(!pending&&(!name.trim()||Array.from(name.trim()).length>128)){setNameError('应用名称需为 1—128 个字符。');nameInput.current?.focus();return}
    setNameError(undefined)
    const input=pending??{operation:operationId(),name:name.trim()}
    savePending(pendingKey,input);setPending(input)
    const existing=pending?(await projectsApi.projects()).find(item=>item.project_id==='app_'+input.operation):undefined
    if(existing&&existing.name!==input.name)throw new Error('原操作已对应其他应用名称，请查看已有工作区。')
    let project:ProjectDto
    try{project=existing??await workbenchApi.create(input.operation,input.name)}
    catch(error){if(notAccepted(error,Boolean(pending))){savePending(pendingKey,undefined);setPending(undefined);nameInput.current?.focus()}throw error}
    savePending(pendingKey,undefined);setPending(undefined);markMilestone('connection:'+project.project_id+':new');changed(project.project_id)
  })
  if(!selected){
    const body=<><PendingRecovery storageKey={pendingKey} destination="/application" label="查看已添加的应用"/><p>为应用命名，下一步设置检查地址。</p><Field label="应用名称" error={nameError}><input ref={nameInput} value={pending?.name??name} disabled={Boolean(pending)} onChange={event=>{setName(event.target.value);setNameError(undefined)}} placeholder="例如：订单与结算系统"/></Field>{pending&&<p>上次添加尚未确认。继续后会先核对原请求对应的应用。</p>}{Boolean(error)&&<ErrorNote error={error}/>}</>;
    const action=<Button kind="primary" busy={busy} disabled={!pending&&!name.trim()} onClick={create}>{pending?'继续上次添加':'添加并配置连接'}</Button>;
    const close=()=>go('/workspace',existingProjectId);
    return existingProjectId?<><Heading title="应用与来源"/><Dialog title="添加要检查的应用" onClose={close} closeDisabled={busy} actions={dismiss=><><Button disabled={busy} onClick={dismiss}>取消</Button>{action}</>}>{body}</Dialog></>:<TaskSurface title="添加要检查的应用" onBack={close} backLabel="返回开始页" actions={action}>{body}</TaskSurface>;
  }
  const navigateView=(value:string)=>{const path='/application?'+new URLSearchParams({view:value,...(route.query.has('runtime_method')?{runtime_method:route.query.get('runtime_method')!}:{})});(workflow?.open??go)(origin?withReturnDestination(path,origin):path,selected.project_id)}
  const attachment=<section className="jj-source-attachment" aria-labelledby="source-attachment-title">
    <header><h2 id="source-attachment-title">为当前应用补充源码</h2>{view==='source'&&<p>“{selected.name??'当前应用'}”已建立{(current?.active_environment?.target.base_url??current?.confirmed_endpoint)&&<>，检查地址为 <span className="jj-mono">{current?.active_environment?.target.base_url??current?.confirmed_endpoint}</span></>}。</p>}<p>关联源码后，可整理业务线索，或由界鉴启动本地测试实例。</p></header>
    <DirectoryField label="这个应用的源码目录" value={sourceDirectory} busy={busy} onValueChange={setSourceDirectory} onBrowse={()=>void act(async()=>{const path=await selectFolderPath();if(path)setSourceDirectory(path)})} hint="选择本机项目根目录，也可以粘贴完整路径。选择本身不会读取或启动源码。"/>
    <footer><Button kind="primary" busy={busy} disabled={!sourceDirectory.trim()} onClick={()=>void act(async()=>{await workbenchApi.attachSource(selected.project_id,sourceDirectory,current!.revision);await state.reload();changed(selected.project_id)})}>补充源码目录</Button></footer>
  </section>
  const saveEnvironment=()=>void act(async()=>{
    if(draftBasis!==undefined&&draftBasis!==current?.revision)throw new Error('应用连接已变化，编辑内容保留。请核对当前连接后重新整理。')
    const submitted=editorDraftGeneration(draftKey,selected.project_id)
    const url=new URL(address.trim());if(url.pathname!=='/'||url.search||url.hash||url.username||url.password)throw new Error('请填写不含路径、参数或凭据的应用地址。')
    const origin=url.origin,port=Number(url.port||(url.protocol==='https:'?443:80))
    const configuration:ApplicationEnvironment={environment_id:environmentId,revision:environmentRevision+1,name:environmentName.trim(),target:{...environmentTarget,base_url:origin,allowed_origins:[origin],allowed_hosts:[url.hostname],allowed_ports:[port],allow_private_network:true,max_requests:maxRequests},deployment_label:deployment.trim()||null,deployment_verification:'UNVERIFIED'}
    await workbenchApi.saveEnvironment(selected.project_id,configuration,environmentRevision);clearSubmittedDraft(draftKey,selected.project_id,submitted);if(!alive.current||liveScope.current!==errorScope)return;state.reload();setEnvironmentId('env_'+operationId());setEnvironmentRevision(0);setAddress('');setDeployment('');setEnvironmentEditing(false)
  })
  const environmentForm=current&&<section className="jj-environment-form">
    {!environments.length&&<header><h3>新增检查连接</h3><p>保存这次检查使用的地址配置，保存后再选择使用。</p></header>}
    {dirty&&draftBasis!==current.revision&&<p role="status">应用连接已有变化。请对照当前连接和下方编辑值，核对后再继续。<Button kind="quiet" onClick={()=>{setDraftBasis(current.revision);rememberEditorDraft(draftKey,{environmentName,address,deployment,sourceDirectory,maxRequests,environmentTarget,environmentEditing,environmentRevision,environmentId,basis:current.revision},selected.project_id)}}>已核对当前连接</Button></p>}<div className="jj-environment-fields"><Field label="连接名称"><input value={environmentName} onChange={event=>setEnvironmentName(event.target.value)}/></Field><Field label="应用地址" hint="仅填写本机 IPv4 的 HTTP/HTTPS 地址，不含路径、参数或凭据。"><input value={address} onChange={event=>setAddress(event.target.value)} placeholder="http://127.0.0.1:8080"/></Field></div>
    <details className="jj-environment-options"><summary>部署说明与请求限制</summary><div className="jj-environment-fields"><Field label="部署说明（可选）" hint="用于区分分支或构建，不代表已核对部署版本。"><input value={deployment} onChange={event=>setDeployment(event.target.value)} placeholder="例如：测试分支 · 本周构建"/></Field><Field label="每次检查请求上限" hint="包含身份核验、业务操作和恢复请求；保存并使用此连接后生效。"><input type="number" min={1} max={500} step={1} value={Number.isFinite(maxRequests)?maxRequests:''} onChange={event=>setMaxRequests(event.target.valueAsNumber)}/></Field></div></details>
    <footer><p>保存后再选择使用。切换连接时需重新核对账号和材料。</p><div>{environments.length>0&&<Button disabled={busy} onClick={()=>setEnvironmentEditing(false)}>取消编辑</Button>}<Button kind="primary" busy={busy} disabled={!environmentName.trim()||!address.trim()||!Number.isInteger(maxRequests)||maxRequests<1||maxRequests>500} onClick={saveEnvironment}>保存连接</Button></div></footer>
  </section>
  return <div className="jj-application-page">{origin&&!runtimeFocused&&<div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(origin,selected.project_id)} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}{origin.startsWith('/preparation?')&&new URLSearchParams(origin.split('?')[1]).has('configure')?'返回结果判断草稿':returnDestinationLabel(origin)}</ActionLink></div>}<div hidden={runtimeFocused}><Heading title="应用与来源"/></div>
    <section className="jj-application-browser" data-view={view}>
      <Tabs label="应用资料" value={view==='source'?'environment':view} panelId="application-panel" idPrefix="application" className="jj-application-tabs" items={applicationSections} onValueChange={navigateView}/>
      {!runtimeFocused&&Boolean(error)&&<ErrorNote error={error}/>}
      <div id="application-panel" role="tabpanel" aria-labelledby={'application-'+(view==='source'?'environment':view)} className="jj-application-content" key={view}>
    {view==='sources'?<SourceLibrary projectId={selected.project_id}/>:view==='business'?<Understanding embedded projectId={selected.project_id}/>:state.loading&&!current?<Loading/>:!current?<ErrorNote error={state.error}/>:view==='source'?<>{current.source_available?<Connect embedded selected={selected} onRuntimeFocus={setRuntimeFocused} onSourceBack={()=>navigateView('environment')} onChanged={onChanged} onError={setError}/>:<><div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={()=>navigateView('environment')}>返回应用连接</Button></div>{attachment}</>}</>:<>
      <div ref={completion} className="jj-application-connections"><section className="jj-environments" aria-labelledby="connection-address-title"><div data-milestone-part="heading" className="jj-connection-introduction"><div className="jj-object-line"><h2 id="connection-address-title">检查连接</h2>{!current.active_environment&&<Badge>尚未选择</Badge>}</div></div>
        {environments.length>0&&<>
          <header className="jj-environment-toolbar"><p>{environments.length} 个已保存连接</p><Button onClick={()=>{setEnvironmentId('env_'+operationId());setEnvironmentRevision(0);setEnvironmentName('测试环境');setAddress('');setDeployment('');setMaxRequests(64);setEnvironmentTarget(undefined);setEnvironmentEditing(true)}}>添加连接</Button></header>
          {!environmentEditing&&!current.active_environment&&current.confirmed_endpoint&&<div className="jj-environment-context"><span>当前运行地址</span><code>{current.confirmed_endpoint}</code><span className="jj-small jj-muted">尚未选择检查连接</span></div>}
          <div className="jj-environment-catalog" aria-label="已保存的连接">{environments.map(environment=>{
            const active=current.active_environment?.environment_id===environment.environment_id&&current.active_environment.revision===environment.revision
            return <section className="jj-environment-card" key={environment.environment_id+':'+environment.revision}>
              <header><div className="jj-object-line"><h3>{environment.name}</h3>{active&&<Badge tone="accent">当前使用</Badge>}</div></header>
              <div className="jj-environment-details"><p className="jj-environment-address jj-mono">{environment.target.base_url}</p>{active&&<div className="jj-environment-reachability"><span>地址状态</span><Badge tone={current.endpoint_reachable===false?'caution':current.endpoint_reachable?'positive':'neutral'}>{current.endpoint_reachable===false?'未连通':current.endpoint_reachable?'上次核验可达':'尚未核验'}</Badge>{current.endpoint_checked_at_us&&<time dateTime={new Date(current.endpoint_checked_at_us/1000).toISOString()}>{date(current.endpoint_checked_at_us)}</time>}</div>}{environment.deployment_label&&<dl className="jj-facts jj-environment-facts"><div><dt>部署说明</dt><dd>{environment.deployment_label}</dd></div></dl>}</div>
              <footer><Button kind="quiet" disabled={busy} onClick={()=>{setEnvironmentId(environment.environment_id);setEnvironmentRevision(environment.revision);setEnvironmentName(environment.name);setAddress(environment.target.base_url);setDeployment(environment.deployment_label??'');setMaxRequests(environment.target.max_requests??64);setEnvironmentTarget(environment.target);setEnvironmentEditing(true)}}>编辑</Button>{active?<Button busy={busy} onClick={()=>void act(async()=>{await projectsApi.confirmEndpoint(selected.project_id,environment.target.base_url,current.revision);state.reload();changed(selected.project_id)})}>检查地址是否可访问</Button>:<Button kind="default" busy={busy} onClick={()=>void act(async()=>{const reviewed=await workbenchApi.previewActivation(selected.project_id,environment.environment_id,environment.revision);assertProject(reviewed.project_id,selected.project_id);if(alive.current&&liveScope.current===errorScope)setImpact(reviewed)})}>使用此连接</Button>}</footer>
            </section>
          })}</div>
        </>}
        {impact&&<Dialog title="使用这份检查连接" size="wide" closeDisabled={busy} onClose={()=>setImpact(undefined)} actions={dismiss=><><Button disabled={busy} onClick={dismiss}>保留当前连接</Button><Button kind="primary" busy={busy} disabled={!impact.can_activate} onClick={()=>void act(async()=>{try{await workbenchApi.activateEnvironment(selected.project_id,impact.chosen.environment_id,impact.chosen.revision,impact.expected_revision,impact.impact_fingerprint)}catch(error){if(alive.current)setImpact(undefined);throw error}if(!alive.current||liveScope.current!==errorScope)return;markMilestone('connection:'+selected.project_id+':'+impact.chosen.environment_id+'@'+impact.chosen.revision);setImpact(undefined);state.reload();changed(selected.project_id)})}>确认切换连接</Button></>}>
          <div className="jj-connection-impact"><section><h3>{impact.previous?.name??'当前检查地址'} → {impact.chosen.name}</h3><dl className="jj-facts"><div><dt>原地址</dt><dd>{impact.previous?.target.base_url??impact.previous_endpoint??'尚未设置'}</dd></div><div><dt>新地址</dt><dd>{impact.chosen.target.base_url}</dd></div></dl><p>{impact.previous?.target.base_url===impact.chosen.target.base_url?'地址相同，但连接身份或修订已改变。账号与材料仍需核对是否适用于这份连接。':'将使用新的应用地址。先核对相应账号，再确认原材料是否适用。'}</p></section>
          <section><h3>需要重新核对</h3>{impact.materials.items===null?<p>当前未能取得材料影响范围，请到检查准备中核对。</p>:impact.materials.items.length?<ul>{[...new Set(impact.materials.items.map(item=>item.action_id))].map(id=><li key={id}><strong>{impact.materials.items!.find(item=>item.action_id===id)!.action_label}</strong><p>{[...new Set(impact.materials.items!.filter(item=>item.action_id===id).map(item=>({identity:'测试账号',execution:'执行操作',resource:'测试数据',evidence:'结果判断依据',recovery:'恢复方式'} as Record<string,string>)[item.kind]??item.kind))].join('、')}</p></li>)}</ul>:<p>当前尚未准备检查材料。</p>}</section>
          <section><h3>继续保留</h3><p>{impact.retained.join('、')}。</p></section>{!impact.can_activate&&<p>应用仍有活动任务，请等待原任务结束后再切换。</p>}</div>
        </Dialog>}
        {!environments.length&&<>{current.confirmed_endpoint&&<dl className="jj-facts"><div><dt>当前运行地址</dt><dd className="jj-mono">{current.confirmed_endpoint}</dd></div></dl>}{environmentForm}</>}
        {environmentEditing&&environments.length>0&&<Dialog title={environmentRevision?'修改检查连接':'添加连接'} onClose={()=>setEnvironmentEditing(false)} closeDisabled={busy}>{environmentForm}</Dialog>}
        {state.error&&<ErrorNote error={state.error}/>}
      </section>
      <div data-milestone-part="facts" className="jj-application-source-summary">{current.source_available?<section className="jj-source-summary" aria-labelledby="connection-source-title"><header><h2 id="connection-source-title">本地源码</h2></header>{source.loading?<Loading/>:source.data?<><dl className="jj-facts"><div><dt>源码读取</dt><dd>{source.data.source_analysis_authorized?'已授权':'尚未授权'}</dd></div><div><dt>业务线索</dt><dd>{source.data.analysis_completed_at_us?'已识别角色和操作，待核对业务名称':'尚未读取源码'}</dd></div></dl><details><summary>查看源码位置</summary><p className="jj-path">{source.data.source_root}</p></details></>:<ErrorNote error={source.error}/>}<footer>{source.data?.analysis_completed_at_us&&<Button kind="quiet" onClick={()=>navigateView('business')}>核对业务名称</Button>}<Button onClick={()=>navigateView('source')}>源码与运行设置</Button></footer></section>:<section className="jj-source-summary"><h2>本地源码</h2><p className="jj-muted">需要整理业务线索或启动本地测试实例时，可以补充当前应用的源码。</p><footer><Button onClick={()=>navigateView('source')}>补充本地源码</Button></footer></section>}</div>
      </div>
    </>}
      </div>
    </section>
  </div>
}
