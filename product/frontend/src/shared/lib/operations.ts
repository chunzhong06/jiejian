import {useEffect,useRef,useState} from 'react'
import {ApiError} from '../api/http'

export const operationId = () => crypto.randomUUID().replaceAll('-', '')

export const isOperationId=(value:unknown):value is string=>typeof value==='string'&&/^[A-Za-z0-9._:-]{1,128}$/.test(value)

/** 拒绝只说明这次尝试；同一操作更早的未知结果仍须查询，不能换键重做。 */
export const notAccepted=(error:unknown,previouslyUnknown=false)=>!previouslyUnknown&&error instanceof ApiError&&error.requestOutcome==='NOT_ACCEPTED'

const damaged=new Set<string>()
export const isRecord=(value:unknown):value is Record<string,unknown>=>Boolean(value)&&typeof value==='object'&&!Array.isArray(value)
export const isPublicId=(value:unknown):value is string=>typeof value==='string'&&value.length>0&&value.length<=128
export const isRevision=(value:unknown):value is number=>Number.isSafeInteger(value)&&Number(value)>0
export function pendingProblem(key:string){return damaged.has(key)?'本地恢复记录不完整。原请求可能已经执行，请先查看原任务或检查记录。':undefined}
// 损坏记录保留，禁止把一次读取失败当成未执行并覆盖原操作身份。

export function readPending<T>(key: string, accepts?: (value:unknown)=>value is T): T | undefined {
  try {
    const text = sessionStorage.getItem(key)
    if (!text){damaged.delete(key);return undefined}
    if(text.length>65536){damaged.add(key);return undefined}
    const value:unknown = JSON.parse(text)
    if (accepts && !accepts(value)){damaged.add(key);return undefined}
    damaged.delete(key)
    return value as T
  }
  catch {damaged.add(key);return undefined}
}

type CommandPhase='idle'|'submitting'|'unknown'|'confirmed'|'rejected'

/** 只复用本实例的命令互斥和反馈；回执查询、重试和采用仍由业务所有者决定。 */
export function useCommand(scope:string,onError?:(error:unknown)=>void,rejected?:(error:unknown)=>boolean) {
  const owner=useRef({scope,alive:true,busy:false,unknown:false})
  if(owner.current.scope!==scope)owner.current={scope,alive:true,busy:false,unknown:false}
  const [state,setState]=useState<{scope:string;phase:CommandPhase;error?:unknown}>({scope,phase:'idle'})
  useEffect(()=>{const current=owner.current;current.alive=true;return()=>{current.alive=false}},[scope])
  const current=()=>owner.current.scope===scope&&owner.current.alive
  const report=(error:unknown)=>{if(current())setState({scope,phase:'rejected',error})}
  const run=async<T,>(task:()=>Promise<T>,kind:'read'|'write'='read')=>{
    const token=owner.current
    if(!token.alive||token.busy)return
    token.busy=true
    setState({scope,phase:'submitting'})
    const active=()=>owner.current===token&&token.alive
    try{
      const value=await task()
      if(active()){if(kind==='write')token.unknown=false;setState({scope,phase:'confirmed'})}
      return value
    }catch(error){
      if(active()){
        const unknown=kind==='write'&&(token.unknown||!(rejected?.(error)??notAccepted(error)))
        if(kind==='write')token.unknown=unknown
        setState({scope,phase:unknown?'unknown':'rejected',error})
        onError?.(error)
      }
    }finally{token.busy=false}
  }
  const visible:{scope:string;phase:CommandPhase;error?:unknown}=state.scope===scope?state:{scope,phase:'idle'}
  return {busy:visible.phase==='submitting',phase:visible.phase,error:visible.error,run,report}
}

export function savePending(key: string, value: unknown) {
  // 成功后清理本地记录失败不能把已经取得的回执改成写入失败；新写入仍须先保存恢复身份。
  if (value === undefined) {try{sessionStorage.removeItem(key);damaged.delete(key)}catch{}}
  else {if(damaged.has(key))throw new Error(pendingProblem(key));sessionStorage.setItem(key, JSON.stringify(value))}
}
