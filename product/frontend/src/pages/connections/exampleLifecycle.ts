import { useEffect, useRef, useState } from 'react'
import { experienceApi, type OfficialExperienceDto } from '../../entities/application/api/experience'
import {useRead} from '../../shared/lib/useRead'

type Request={id:string;kind:'start'|'resume'|'stop'|'restart'|'reset';phase:'start'|'stop';nextId?:string}
const key='jiejian.studio.example-operation'
const phases:Record<string,string>={CHECKING_PREVIOUS:'核对上次实例',PREPARING_WORKSPACE:'准备示例源码',CREATING_PROJECT:'建立独立项目',INSTALLING:'准备运行依赖',LOADING_RUNTIME:'启动示例服务',LOADING_APPLICATION:'启动示例应用',WAITING_READY:'等待示例就绪',WAITING_APPLICATION:'等待示例就绪',STOPPING:'停止示例服务'}
function restore():Request|undefined{try{const value=JSON.parse(sessionStorage.getItem(key)??'null');return value&&typeof value.id==='string'&&['start','resume','stop','restart','reset'].includes(value.kind)&&['start','stop'].includes(value.phase)?value:undefined}catch{return undefined}}

export function useExampleLifecycle(environment:OfficialExperienceDto|undefined,onChanged:(id:string)=>void,onError:(error:unknown)=>void){
  const [pending,setPending]=useState<Request|undefined>(restore),[snapshot,setSnapshot]=useState<OfficialExperienceDto>(),[busy,setBusy]=useState(false),[unknown,setUnknown]=useState(false),[failure,setFailure]=useState('')
  const active=useRef(pending),lock=useRef(false),mounted=useRef(true),callbacks=useRef({onChanged,onError});callbacks.current={onChanged,onError}
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[])
  const lifecycle=useRead(pending?'official:'+pending.id:environment?null:'official-idle',signal=>experienceApi.status(pending?.id,true,signal),pending?700:0)
  const official=pending?(lifecycle.data??snapshot??environment):(snapshot??environment??lifecycle.data)
  useEffect(()=>{if(environment&&!active.current)setSnapshot(undefined)},[environment])
  function remember(value:Request|undefined){active.current=value;setPending(value);if(value)sessionStorage.setItem(key,JSON.stringify(value));else sessionStorage.removeItem(key)}
  function receive(value:OfficialExperienceDto,request:Request){
    if(!mounted.current||active.current?.id!==request.id)return
    if(value.operation_id!==request.id)return
    setSnapshot(value)
    if(value.operation_state==='FAILED'){
      remember(undefined);setUnknown(false);setFailure(value.recovery_state==='OWNERSHIP_UNCONFIRMED'?'旧实例是否退出尚未确认。请先读取运行状态。':'这次环境操作未完成。项目、权限与报告仍保留，请读取状态后重试。');return
    }
    if(value.operation_state!=='SUCCEEDED'){if(value.operation_state==='UNKNOWN')setUnknown(true);return}
    if(request.kind==='restart'&&request.phase==='stop'){
      const next={...request,id:request.nextId!,phase:'start' as const};remember(next);void send(next);return
    }
    remember(undefined);setUnknown(false);setFailure('');lifecycle.reload()
    if(request.kind!=='stop'&&value.project_id)callbacks.current.onChanged(value.project_id)
  }
  async function send(request:Request){
    setBusy(true)
    try{const value=await (request.phase==='stop'?experienceApi.stop(request.id):request.kind==='reset'?experienceApi.reset(request.id):request.kind==='start'?experienceApi.start(request.id):experienceApi.resume(request.id));receive(value,request)}
    catch(error){if(mounted.current&&active.current?.id===request.id){setUnknown(true);callbacks.current.onError(error)}}
    finally{if(mounted.current){setBusy(false);lifecycle.reload()};lock.current=false}
  }
  useEffect(()=>{if(pending&&lifecycle.data)receive(lifecycle.data,pending)},[pending?.id,lifecycle.data])
  const begin=(kind:Request['kind'])=>{
    if(lock.current||active.current)return
    lock.current=true;setFailure('');setUnknown(false)
    const request:Request={id:crypto.randomUUID(),kind,phase:kind==='stop'||kind==='restart'?'stop':'start',...(kind==='restart'?{nextId:crypto.randomUUID()}:{})}
    // 每一阶段先保存操作身份；断开或离页后只查询原回执。
    remember(request);void send(request)
  }
  return {official,pending,busy,unknown,failure,error:lifecycle.error,begin,reload:lifecycle.reload,phase:pending?.phase==='stop'?'正在停止示例':phases[official?.operation_phase??'']??'正在启动示例'}
}
