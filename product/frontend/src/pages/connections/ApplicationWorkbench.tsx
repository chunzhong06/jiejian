import {useCallback,useRef,useState} from 'react'
import {workbenchApi,type ApplicationEnvironment} from '../../entities/application/api/workbench'
import {projectsApi,type ProjectDto} from '../../entities/application/api/projects'
import {useRead} from '../../shared/lib/useRead'
import {operationId,readPending,savePending} from '../../shared/lib/operations'
import {go,readRoute} from '../../shared/lib/navigation'
import {Button} from '../../shared/ui/actions'
import {Heading,Field} from '../../shared/ui/layout'
import {Badge,ErrorNote,Loading} from '../../shared/ui/feedback'
import {routePage} from '../../shared/lib/routePage'
import {Tabs} from '../../shared/ui/Tabs'
import './workbench.css'

const SourceLibrary=routePage(()=>import('./SourceLibrary').then(module=>({default:module.SourceLibrary})),'/application')
const Connect=routePage(()=>import('./Connect').then(module=>({default:module.Connect})),'/application')
const Understanding=routePage(()=>import('./Understanding').then(module=>({default:module.Understanding})),'/application')

export function ApplicationWorkbench({selected,onChanged}:{selected?:ProjectDto;onChanged:(id:string)=>void}) {
  const requestedView=readRoute().query.get('view')??'environment'
  const view=['environment','sources','source','business'].includes(requestedView)?requestedView:'environment'
  const state=useRead(selected&&(view==='environment'||view==='source')?'application-environments:'+selected.project_id:null,signal=>selected?workbenchApi.environments(selected.project_id,signal):Promise.resolve(null))
  const pendingKey='jiejian.application.create'
  const [pending,setPending]=useState(()=>readPending<{operation:string;name:string}>(pendingKey))
  const [name,setName]=useState(''),[environmentName,setEnvironmentName]=useState('测试环境'),[address,setAddress]=useState(''),[deployment,setDeployment]=useState('')
  const [sourceDirectory,setSourceDirectory]=useState('')
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
  if(!selected)return <><Heading eyebrow="界鉴 · 应用与来源" title="建立应用工作区">保存应用、身份、权限要求和可反复使用的测试场景。</Heading><section className="jj-application-create"><div><h2>从正在使用的应用开始</h2><p>接入后可以添加环境、接口资料和请求；源码可单独补充。</p><Field label="应用名称"><input value={pending?.name??name} disabled={Boolean(pending)} onChange={event=>setName(event.target.value)} placeholder="例如：订单与结算系统"/></Field><div className="jj-confirmation-actions"><Button kind="primary" busy={busy} disabled={!pending&&!name.trim()} onClick={create}>{pending?'核对并继续原创建':'建立工作区'}</Button></div>{Boolean(error)&&<ErrorNote error={error}/>}</div><aside aria-label="其他开始方式"><section><h2>从本地源码开始</h2><p>选择源码目录，继续配置应用与运行方式。</p><footer><Button onClick={()=>go('/application?view=source')}>从源码接入</Button></footer></section><section><h2>先体验完整检查</h2><p>在独立示例中了解权限检查、问题处理与修复复验。</p><footer><Button kind="quiet" onClick={()=>go('/environment')}>打开独立示例</Button></footer></section></aside></section></>
  return <><Heading title="应用与来源"/>
    <section className="jj-application-browser" data-view={view}>
      <Tabs label="应用资料" value={view} panelId="application-panel" idPrefix="application" className="jj-application-tabs" items={[{value:'environment',label:'环境'},{value:'sources',label:'接口来源'},{value:'business',label:'业务角色与操作'},{value:'source',label:'源码与受控运行'}]} onValueChange={value=>go('/application?view='+value)}/>
      {Boolean(error)&&<ErrorNote error={error}/>}
      <div id="application-panel" role="tabpanel" aria-labelledby={'application-'+view} className="jj-application-content" key={view}>
    {view==='sources'?<SourceLibrary projectId={selected.project_id}/>:view==='business'?<Understanding embedded projectId={selected.project_id}/>:state.loading&&!current?<Loading/>:!current?<ErrorNote error={state.error}/>:view==='source'?current.source_available?<Connect embedded selected={selected} onChanged={onChanged} onError={setError}/>:<section className="jj-environment-editor"><h2>关联本地源码（可选）</h2><p>保留当前应用的环境、规则、身份、场景和报告。关联目录后，再单独确认读取授权。</p><Field label="源码目录的绝对路径"><input value={sourceDirectory} onChange={event=>setSourceDirectory(event.target.value)}/></Field><div className="jj-confirmation-actions"><Button kind="primary" busy={busy} disabled={!sourceDirectory.trim()} onClick={()=>void act(async()=>{await workbenchApi.attachSource(selected.project_id,sourceDirectory,current.revision);await state.reload();onChanged(selected.project_id)})}>关联到当前应用</Button></div></section>:<>
      <div className="jj-environments">
        {current.environments.length>0&&!environmentEditing&&<>
          <header className="jj-environment-toolbar"><p>{current.environments.length} 个已保存环境</p>{!environmentEditing&&<Button onClick={()=>{setEnvironmentId('env_'+operationId());setEnvironmentRevision(0);setEnvironmentName('测试环境');setAddress('');setDeployment('');setEnvironmentEditing(true)}}>添加环境</Button>}</header>
          {!environmentEditing&&!current.active_environment&&current.confirmed_endpoint&&<div className="jj-environment-context"><span>当前运行地址</span><code>{current.confirmed_endpoint}</code><span className="jj-small jj-muted">未选择环境配置</span></div>}
          <div className="jj-environment-catalog" aria-label="已保存的环境">{environments.map(environment=>{
            const active=current.active_environment?.environment_id===environment.environment_id&&current.active_environment.revision===environment.revision
            return <section className="jj-environment-card" key={environment.environment_id+':'+environment.revision}>
              <header><h2>{environment.name}</h2>{active&&<Badge tone="accent">当前使用</Badge>}</header>
              <p className="jj-environment-address jj-mono">{environment.target.base_url}</p>
              <dl className="jj-environment-facts"><div><dt>部署说明</dt><dd>{environment.deployment_label??'未填写'}</dd></div><div><dt>部署版本</dt><dd>未核对</dd></div></dl>
              {active&&<div className="jj-environment-reachability"><div><span>地址连通性</span><Badge tone={current.endpoint_reachable?'positive':'caution'}>{current.endpoint_reachable?'地址已核验':current.endpoint_reachable===false?'本次未能连通':'地址待核验'}</Badge></div><Button kind="quiet" busy={busy} onClick={()=>void act(async()=>{await projectsApi.confirmEndpoint(selected.project_id,environment.target.base_url,current.revision);state.reload();onChanged(selected.project_id)})}>核验当前地址</Button></div>}
              <footer>{!active&&<Button busy={busy} onClick={()=>void act(async()=>{await workbenchApi.activateEnvironment(selected.project_id,environment.environment_id,environment.revision,current.revision);state.reload();onChanged(selected.project_id)})}>切换到此环境</Button>}<Button kind="quiet" disabled={busy} onClick={()=>{setEnvironmentId(environment.environment_id);setEnvironmentRevision(environment.revision);setEnvironmentName(environment.name);setAddress(environment.target.base_url);setDeployment(environment.deployment_label??'');setEnvironmentEditing(true)}}>编辑</Button></footer>
            </section>
          })}</div>
        </>}
        {(environmentEditing||!current.environments.length)&&<section className="jj-environment-form" aria-label={environmentRevision?'修改环境配置':'添加环境'}>
          <header><h2>{environmentRevision?'修改环境配置':'添加环境'}</h2><p>为当前应用保存可切换的运行地址。</p></header>
          {!current.active_environment&&current.confirmed_endpoint&&<dl className="jj-environment-current"><dt>当前运行地址</dt><dd><code>{current.confirmed_endpoint}</code><span>未选择环境配置</span></dd></dl>}
          <div className="jj-environment-fields">
            <Field label="环境名称"><input value={environmentName} onChange={event=>setEnvironmentName(event.target.value)}/></Field>
            <Field label="应用地址" hint="仅填写本机 IPv4 的 HTTP/HTTPS 地址，不含路径、参数或凭据。"><input value={address} onChange={event=>setAddress(event.target.value)} placeholder="http://127.0.0.1:8080"/></Field>
            <Field label="部署说明（可选）" hint="用于区分分支或构建，不代表已核对部署版本。"><input value={deployment} onChange={event=>setDeployment(event.target.value)} placeholder="例如：测试分支 · 本周构建"/></Field>
          </div>
          <footer><p>保存后不会切换环境或发送请求；切换后需重新核对检查材料。</p><div>{current.environments.length>0&&<Button disabled={busy} onClick={()=>setEnvironmentEditing(false)}>取消编辑</Button>}<Button kind="primary" busy={busy} disabled={!environmentName.trim()||!address.trim()} onClick={()=>void act(async()=>{
            const url=new URL(address.trim());if(url.pathname!=='/'||url.search||url.hash||url.username||url.password)throw new Error('请填写不含路径、参数或凭据的应用地址。')
            const origin=url.origin,port=Number(url.port||(url.protocol==='https:'?443:80))
            const configuration:ApplicationEnvironment={environment_id:environmentId,revision:environmentRevision+1,name:environmentName.trim(),target:{base_url:origin,allowed_origins:[origin],allowed_hosts:[url.hostname],allowed_ports:[port],allow_private_network:true},deployment_label:deployment.trim()||null,deployment_verification:'UNVERIFIED'}
            await workbenchApi.saveEnvironment(selected.project_id,configuration,environmentRevision);state.reload();setEnvironmentId('env_'+operationId());setEnvironmentRevision(0);setAddress('');setDeployment('');setEnvironmentEditing(false)
          })}>保存环境</Button></div></footer>
        </section>}
        {state.error&&<ErrorNote error={state.error}/>}
      </div>
    </>}
      </div>
    </section>
  </>
}
