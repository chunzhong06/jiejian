// 页面只订阅后台材料批次；未知写入保留原键，离开页面不取消已确认步骤。
import {useCallback,useEffect,useRef,useState} from 'react'
import {preparationBatchesApi as api,type PreparationBatch,type PreparationBatchPlan} from '../../../api/preparation/batches'
import type {ProofContext} from '../../../api/preparation/proofSources'
import {ApiError} from '../../../api/http'
import {useLiveRead} from '../../../shared/runtime/useLiveRead'

export function usePreparationBatch(project:string,onChanged:()=>Promise<unknown>){
  const [value,setValue]=useState<PreparationBatch|null>(null),[error,setError]=useState(''),[sending,setSending]=useState(false),[queryRequired,setQueryRequired]=useState(false)
  const alive=useRef(true),pending=useRef(false),observed=useRef<string|undefined>(undefined),activeOperation=useRef<string|undefined>(undefined),notify=useRef(onChanged)
  const currentProject=useRef(project)
  currentProject.current=project
  notify.current=onChanged
  const key=`jiejian-preparation-batch:${project}`
  useEffect(()=>{alive.current=true;setValue(null);setError('');setQueryRequired(false);activeOperation.current=undefined;observed.current=undefined;return()=>{alive.current=false}},[project])
  const accept=useCallback((next:PreparationBatch|null)=>{
    if(!alive.current||currentProject.current!==project)return
    if(next&&next.project_id!==project)throw new Error('材料批次不属于当前应用')
    const localOperation=sessionStorage.getItem(key)
    setValue(next);setError('');if(next?.operation_id===localOperation)setQueryRequired(false)
    if(next&&['RUNNING','CANCELLING'].includes(next.state))activeOperation.current=next.operation_id
    if(next&&!['RUNNING','CANCELLING'].includes(next.state)){
      sessionStorage.removeItem(key)
      if((activeOperation.current===next.operation_id||localOperation===next.operation_id)&&observed.current!==next.operation_id){observed.current=next.operation_id;void notify.current().catch(()=>{if(alive.current)setError('批次状态已保存，材料列表暂未同步。')})}
    }
  },[project,key])
  const read=useCallback(async()=>{
    const operation=sessionStorage.getItem(key)
    if(operation&&activeOperation.current!==operation&&observed.current!==operation)setQueryRequired(true)
    const next=operation?await api.status(project,operation):await api.latest(project)
    accept(next)
    return Boolean(next&&['RUNNING','CANCELLING'].includes(next.state))
  },[project,key,accept])
  const live=useLiveRead(`${project}:${value?.operation_id??'latest'}`,read,2000)
  const start=async(mode:PreparationBatchPlan['mode'],reviewed?:ProofContext)=>{
    if(pending.current)return
    pending.current=true;setSending(true);setError('')
    try{
      if(sessionStorage.getItem(key)){await read();return}
      const plan=await api.preview(project,mode)
      if(plan.project_id!==project)throw new Error('材料计划不属于当前应用')
      if(reviewed&&(reviewed.basis_id!==plan.basis_id||reviewed.runtime_origin!==plan.runtime_origin||
        reviewed.sources.length!==plan.sources.length||reviewed.sources.some(source=>!plan.sources.some(item=>item.source_id===source.source_id&&item.revision===source.revision))))
        throw new Error('确认期间材料已变化，请重新核对清单。')
      if(!alive.current||currentProject.current!==project)return
      const operation=crypto.randomUUID().replaceAll('-','')
      sessionStorage.setItem(key,operation);setQueryRequired(true)
      try{accept(await api.start(project,operation,plan))}
      catch(reason){if(reason instanceof ApiError&&['INPUT_INVALID','STATE_PRECONDITION','API_VALIDATION_ERROR'].includes(reason.code)){sessionStorage.removeItem(key);setQueryRequired(false)}throw reason}
    }catch(reason){if(alive.current)setError(reason instanceof Error?reason.message:'材料准备结果尚未确认，请查询原操作。')}
    finally{pending.current=false;if(alive.current)setSending(false)}
  }
  const cancel=async()=>{if(value)try{accept(await api.cancel(project,value.operation_id))}catch{setError('停止请求的结果尚未确认，请查询原操作。')}}
  return {value,error,sending,queryRequired,start,cancel,refresh:async()=>{try{await read()}catch{if(alive.current)setError('暂时无法查询原批次，请稍后重试。')}},busy:sending||Boolean(value&&['RUNNING','CANCELLING'].includes(value.state)),retrying:live.retrying}
}
