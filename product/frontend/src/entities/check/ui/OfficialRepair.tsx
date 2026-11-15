import {useRef,useState,type ReactNode} from 'react'
import {experienceApi} from '../../application/api/experience'
import {sourceChangesApi} from '../../source-change/api/sourceChanges'
import {repairReference,type RepairContract} from '../api/repairs'
import {useRead} from '../../../shared/lib/useRead'
import {ApiError} from '../../../shared/api/http'
import {assertProject} from '../../../shared/model/page'
import {Button} from '../../../shared/ui/actions'
import {Dialog} from '../../../shared/ui/Dialog'
import {ErrorNote,Loading,Notice} from '../../../shared/ui/feedback'
import {ObjectHeading,TaskActions} from '../../../shared/ui/layout'

/** 预置修复只加载源码；准确原题继续交给正式复验，不在示例入口制造通过状态。 */
export function OfficialRepair({projectId,contract,onLoaded,onError,fallback,context}:{projectId:string;contract:RepairContract;onLoaded:(changeId:string)=>void;onError:(error:unknown)=>void;fallback:ReactNode;context?:ReactNode}){
  const state=useRead('official-repair:'+projectId,async()=>{
    const [current,journey]=await Promise.all([experienceApi.status(undefined,true),experienceApi.development()])
    return {current,journey}
  })
  const [confirm,setConfirm]=useState(false),[busy,setBusy]=useState(false),[uncertain,setUncertain]=useState(false),[manualOpen,setManualOpen]=useState(false),[message,setMessage]=useState(''),lock=useRef(false)
  const data=state.data
  const matches=data?.current.project_id===projectId&&data.journey.project_id===projectId
  const available=matches&&data.current.active&&['VULNERABLE','EXPOSE_REVOKE'].includes(data.journey.implementation)&&!data.journey.has_active_tasks
  const loaded=async(changeId:string)=>{
    const change=await sourceChangesApi.show(projectId,changeId)
    assertProject(change.manifest.project_id,projectId)
    const reference=change.manifest.repair_reference
    if(reference?.repair_fingerprint!==contract.repair_fingerprint||reference.source_run_id!==contract.source_run_id||reference.source_case_id!==contract.source_case_id)throw new Error('这份修改没有关联当前原问题，请核对原交付记录。')
    onLoaded(changeId)
  }
  const submit=async()=>{
    if(lock.current||!available||!data)return
    lock.current=true;setBusy(true)
    try{
      const result=await experienceApi.switchVersion('FIXED',repairReference(contract),{project_id:projectId,expected_basis:data.journey.transition_basis})
      assertProject(result.project_id??'',projectId)
      if(!result.current_change_id||result.scenario_version!=='FIXED')throw new Error('修复加载尚未确认，请查询本次加载结果。')
      await loaded(result.current_change_id)
      setConfirm(false)
    }catch(error){
      // 写入可能已完成；未知响应只开放原交付回读，不能让再次点击重复切换源码。
      if(error instanceof ApiError){setConfirm(false);state.reload()}else setUncertain(true)
      onError(error)
    }finally{lock.current=false;setBusy(false)}
  }
  const recover=async()=>{
    if(lock.current)return
    lock.current=true;setBusy(true)
    try{
      const current=await experienceApi.status(undefined,true)
      assertProject(current.project_id??'',projectId)
      if(current.scenario_version==='FIXED'&&current.current_change_id)await loaded(current.current_change_id)
      else setMessage('尚未找到这次修复的完成记录，请稍后继续查询。')
    }catch(error){onError(error)}finally{lock.current=false;setBusy(false)}
  }
  if(state.loading)return <Loading>正在核对示例修复方式</Loading>
  if(state.error)return <><ErrorNote error={state.error} onRetry={state.reload}/>{fallback}</>
  if(!matches)return <>{fallback}</>
  return <section className="jj-panel jj-official-repair">
    <ObjectHeading title="恢复内部包访问限制" level={3} description={manualOpen?'在开发工具中修改代码，再登记并按本题复验。':'使用预置修复，在交付内部包前核对账号与资料所有者。'}/>
    <div className="jj-official-repair-reading"><section><h4 className="jj-title-caption">修复后需要验证</h4><dl className="jj-facts is-stacked"><div><dt>原违规后果</dt><dd>评审不能取得负责人的内部完整包。</dd></div><div><dt>正常功能</dt><dd>负责人仍能访问自己的资料，评审仍能查看公开内容。</dd></div></dl></section>{context}</div>
    {!uncertain&&<details className="jj-official-repair-manual" open={manualOpen} onToggle={event=>setManualOpen(event.currentTarget.open)}><summary>自行修改代码</summary>{fallback}</details>}
    {uncertain?<Notice tone="caution" title="修复加载结果尚未确认" actions={<Button busy={busy} onClick={()=>void recover()}>查询本次修复加载</Button>}>{message||'先查询原交付记录，再继续准备和复验。'}</Notice>:!manualOpen&&<TaskActions separated note={available?'加载后核对材料，再按原问题真实复验。':data?.journey.has_active_tasks?'当前还有任务在执行，请结束后重新读取。':'当前实现已变化，请重新读取，或在开发工具中继续修改。'}>{available?<Button kind="primary" disabled={busy} onClick={()=>setConfirm(true)}>加载这份预置修复</Button>:<Button onClick={state.reload}>重新读取修复条件</Button>}</TaskActions>}
    {confirm&&!uncertain&&<Dialog title="加载预置修复源码" onClose={()=>setConfirm(false)} actions={dismiss=><><Button disabled={busy} onClick={dismiss}>取消</Button><Button kind="primary" busy={busy} onClick={()=>void submit()}>确认加载修复</Button></>}><p>这会替换隔离展馆的内部包交付实现，并将修改登记到当前原问题。</p><p>接下来核对材料、按原请求复验，再判断违规是否消失、正常功能是否保留。</p></Dialog>}
  </section>
}
