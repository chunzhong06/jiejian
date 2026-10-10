// 新应用接入先释放旧页面上下文；官方实例停止只提交一次，未知结果通过状态回读恢复。
import {useEffect, useRef, useState} from 'react'
import {experienceApi, type OfficialExperienceDto} from '../../api/applications/experience'
import type {ApiError} from '../../api/http'

type AccessState = 'IDLE' | 'CHECKING' | 'STOPPING' | 'UNCONFIRMED' | 'READY'
const stopped = (value:OfficialExperienceDto) => !value.active && (value.recovery_state==='EXITED' || (
  !['STARTING','STOPPING','UNKNOWN'].includes(value.lifecycle??'') &&
  !['PENDING','UNKNOWN'].includes(value.operation_state??'') && value.recovery_state!=='OWNERSHIP_UNCONFIRMED'))

export function useNewApplication({onEnter,onEnvironment,onError}:{
  onEnter:()=>void;onEnvironment:(value:OfficialExperienceDto)=>void;onError:(error:ApiError)=>void
}) {
  const [state,setState]=useState<AccessState>('IDLE')
  const pendingStop=useRef<string|null>(null),inFlight=useRef(false),epoch=useRef(0),alive=useRef(true)
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;epoch.current+=1}},[])
  const read = async (stopIfRunning:boolean) => {
    if(inFlight.current)return
    inFlight.current=true
    const current=++epoch.current, valid=()=>alive.current&&epoch.current===current
    setState('CHECKING')
    const accept=(value:OfficialExperienceDto)=>{
      if(!valid())return
      onEnvironment(value)
      if(stopped(value)){pendingStop.current=null;setState('READY')}
      else setState('UNCONFIRMED')
    }
    try {
      const value=await experienceApi.status()
      if(!valid())return
      if(stopped(value)){accept(value);return}
      if(stopIfRunning && !pendingStop.current && value.active && value.lifecycle==='RUNNING' && !['PENDING','UNKNOWN'].includes(value.operation_state??'')){
        pendingStop.current=crypto.randomUUID()
        setState('STOPPING')
        accept(await experienceApi.stop(pendingStop.current))
      }else accept(value)
    }catch(error){
      if(!valid())return
      setState('UNCONFIRMED');onError(error as ApiError)
      // 停止可能已经生效；这里只读取原状态，不能通过再次停止来探测结果。
      if(pendingStop.current){try{accept(await experienceApi.status())}catch{/* 保留未知状态，交给明确回读入口。 */}}
    }finally{inFlight.current=false}
  }
  const begin=()=>{if(inFlight.current)return;onEnter();void read(!pendingStop.current)}
  const abandon=()=>{epoch.current+=1;setState('IDLE')}
  return {state,begin,reread:()=>read(false),abandon}
}
