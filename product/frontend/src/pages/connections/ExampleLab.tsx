import {useRef,useState} from 'react'
import {experienceApi} from '../../entities/application/api/experience'
import {repairsApi,repairReference} from '../../entities/check/api/repairs'
import {issueDestination} from '../../entities/check/issueDestination'
import {useRead} from '../../shared/lib/useRead'
import {ApiError} from '../../shared/api/http'
import {assertProject} from '../../shared/model/page'
import {go,scopedPath,readRoute} from '../../shared/lib/navigation'
import {ActionLink,Button} from '../../shared/ui/actions'
import {Badge,ErrorNote,Loading,Notice} from '../../shared/ui/feedback'
import {ObjectIdentity,ObjectHeading,TaskActions} from '../../shared/ui/layout'
import {Dialog} from '../../shared/ui/Dialog'
import {TaskSurface} from '../../shared/ui/TaskSurface'
import './example-change.css'

const changes={
  VULNERABLE:{title:'移除内部包下载限制',change:'内部包下载入口不再核对账号与资料所有者。',question:'评审是否真的取得了内部完整包，内部资料访问权是否被开放？'},
  EXPOSE_REVOKE:{title:'处理中开放后再撤回',change:'先独立提交开放访问，再拒绝请求并撤回开放。',question:'即使响应拒绝、最终恢复，处理中是否已经开放了内部资料访问权？'},
  FIXED:{title:'恢复内部包访问限制',change:'加载预置修复源码；沿原问题的要求重新验收。',question:'原违规后果是否消失，负责人正常访问是否仍然可用？'},
  PREVIEW_CHANGED:{title:'调整公开预览内容',change:'只改变公开预览的展示内容，保留原有权限要求。',question:'这次修改后，原有资料访问要求是否仍然成立？'},
} as const
type Change=keyof typeof changes
export function ExampleLab({projectId,onError,onChanged,focused=false}:{projectId:string;onError:(error:unknown)=>void;onChanged:()=>void;focused?:boolean}){
  const read=async(signal?:AbortSignal)=>{
    const [current,journey,repair]=await Promise.all([experienceApi.status(undefined,true,signal),experienceApi.development(signal),repairsApi.project(projectId)])
    assertProject(current.project_id??'',projectId);assertProject(journey.project_id,projectId)
    return {current,journey,repair}
  }
  const state=useRead('example-change:'+projectId,read)
  const [confirmation,setConfirmation]=useState<{version:Change;basis:string}>(),[busy,setBusy]=useState(false),[uncertain,setUncertain]=useState<Change>(),[message,setMessage]=useState(''),lock=useRef(false)
  const data=state.data,deeper=readRoute().query.get('experiment')==='expose'||data?.journey.implementation==='EXPOSE_REVOKE',contract=data?.repair.tasks.find(item=>['REPAIR_REQUIRED','CHANGE_SUBMITTED','READY_TO_VERIFY'].includes(item.status))?.contract
  const href=(path:string)=>'#'+scopedPath(path,projectId)
  const request=async()=>{
    if(lock.current||!confirmation)return
    lock.current=true;setBusy(true)
    try{
      const result=await experienceApi.switchVersion(confirmation.version,confirmation.version==='FIXED'&&contract?repairReference(contract):undefined,{project_id:projectId,expected_basis:confirmation.basis})
      assertProject(result.project_id??'',projectId)
      if(result.scenario_version!==confirmation.version)throw new Error('当前实现已变化，请读取本次加载结果。')
      setConfirmation(undefined);onChanged()
      go(scopedPath('/preparation'+(result.current_change_id?'?change_id='+encodeURIComponent(result.current_change_id):''),projectId))
    }catch(error){
      if(!(error instanceof ApiError))setUncertain(confirmation.version)
      else {setConfirmation(undefined);state.reload()}
      onError(error)
    }finally{lock.current=false;setBusy(false)}
  }
  const recover=async()=>{
    if(lock.current)return
    lock.current=true;setBusy(true)
    try{
      const actual=await read()
      // 只回读原交付，网络失败后不自动重新加载源码或重放目标操作。
      if(actual.current.scenario_version===uncertain&&actual.journey.current_change_id){setUncertain(undefined);setConfirmation(undefined);setMessage('已确认这份修改加载完成，可以继续准备检查。');onChanged()}
      else setMessage('这次加载仍未确认。已保留当前项目，请稍后重新读取。')
      state.reload()
    }catch(error){onError(error)}finally{lock.current=false;setBusy(false)}
  }
  function change(version:Change,primary=false){
    const content=changes[version],loaded=data?.current.scenario_version===version&&Boolean(data.journey.current_change_id)
    const available=version==='FIXED'?Boolean(contract)&&!data?.journey.has_active_tasks:version==='PREVIEW_CHANGED'?Boolean(data?.journey.repair_verified)&&!data?.journey.has_active_tasks:data?.journey.change_options?.find(item=>item.version===version)?.available
    const reason=version==='FIXED'&&!contract?'先从具体问题发起原题修复。':version==='PREVIEW_CHANGED'&&!data?.journey.repair_verified?'先完成原题复验。':data?.journey.change_options?.find(item=>item.version===version)?.reason
    return <section className="jj-example-change" data-primary={primary||undefined} aria-label={content.title}>
      <ObjectHeading title={content.title} level={primary?2:3} status={loaded?<Badge tone="accent">{data?.journey.run_id?'已检查':'已加载，待检查'}</Badge>:undefined} description={content.change}/>
      <div className="jj-example-change-reading"><section className="jj-example-change-question"><h3>这次检查要回答</h3><p>{content.question}</p></section><section className="jj-example-change-requirement"><h3>保持的访问要求</h3><ul><li>评审不得取得负责人的内部完整包。</li><li>负责人仍可访问自己的资料。</li></ul></section></div>
      <TaskActions note={loaded?(data?.journey.run_id?'这份修改已有真实检查结果，可直接阅读本次业务后果。':'源码已加载，权限结论由下一次真实检查给出。'):reason||'加载后保留规则和历史报告，重新核对受影响材料。'}>
        {loaded?<ActionLink navigationScope="page" kind="primary" href={href(data!.journey.run_id?'/reports?run_id='+data!.journey.run_id:'/preparation?change_id='+data!.journey.current_change_id)}>{data?.journey.run_id?'阅读这份修改的结果':'准备这份修改的检查'}</ActionLink>:<Button kind={primary?'primary':'default'} disabled={!available||busy||Boolean(uncertain)||Boolean(state.error)} onClick={()=>setConfirmation({version,basis:data!.journey.transition_basis})}>{version==='VULNERABLE'?'加载这次错误修改':version==='EXPOSE_REVOKE'?'加载开放后撤回的修改':'加载'+content.title}</Button>}
      </TaskActions>
    </section>
  }
  const body=state.loading?<Loading>正在读取示例修改与检查依据</Loading>:state.error?<ErrorNote error={state.error} actions={<Button onClick={state.reload}>重新读取</Button>}/>:data?<>
    <ObjectIdentity name={<span>当前实现：{data.journey.implementation==='CUSTOM'?'本地自定义修改':changes[data.current.scenario_version as Change]?.title??'正常访问限制'}</span>} status={<Badge>{data.current.active?'运行中':'已停止'}</Badge>}/>
    {uncertain&&<Notice tone="caution" title="加载结果尚未确认" actions={<Button busy={busy} onClick={()=>void recover()}>查询本次加载结果</Button>}>先读取当前实现和原交付记录，暂不提交另一份修改。{message&&<p>{message}</p>}</Notice>}
    {!uncertain&&message&&<Notice tone="positive">{message}</Notice>}
    {data.journey.implementation==='CUSTOM'?<Notice tone="caution">当前源码已由外部修改，请在原开发任务中继续；预设修改不会覆盖它。</Notice>:change(deeper?'EXPOSE_REVOKE':'VULNERABLE',true)}
    {!deeper&&<details className="jj-example-deeper"><summary>深入体验：响应拒绝，业务后果是否仍然发生</summary>{change('EXPOSE_REVOKE')}</details>}
    {contract&&<TaskActions note="修复从具体问题接续，原请求、账号与正常功能一并保留。"><ActionLink navigationScope="page" href={href(issueDestination(contract,undefined,{section:'repair'}))}>处理内部包访问问题</ActionLink></TaskActions>}
    <details><summary>其他示例维护</summary>{change('PREVIEW_CHANGED')}</details>
  </>:null
  return <>{focused?<TaskSurface width="wide" title="检查一次错误修改" context="官方示例 · 数字展馆" description="保持已经确认的资料访问要求，只改变实现，再观察实际业务后果。" onBack={()=>go(scopedPath('/workspace',projectId))} backLabel="返回当前任务">{body}</TaskSurface>:<details className="jj-example-lab"><summary>查看示例修改与深入体验</summary><div className="jj-example-change-body">{body}</div></details>}
    {confirmation&&!uncertain&&<Dialog title={changes[confirmation.version].title} onClose={()=>setConfirmation(undefined)} actions={dismiss=><><Button disabled={busy} onClick={dismiss}>取消</Button><Button kind="primary" busy={busy} onClick={()=>void request()}>确认加载这份修改</Button></>}><p>{changes[confirmation.version].change}</p><p>这会替换隔离示例的运行源码。原访问要求和报告保留；加载后还需准备材料并执行真实检查。</p></Dialog>}
  </>
}
