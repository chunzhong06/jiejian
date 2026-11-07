import {useEffect,useRef,useState} from 'react'

export const operationId = () => crypto.randomUUID().replaceAll('-', '')

// 仅保存非秘密的恢复输入和操作标识，服务端回执才决定是否完成；T 不会校验读回的 JSON。
export function readPending<T>(key: string, accepts?: (value:unknown)=>value is T): T | undefined {
  try {
    const text = sessionStorage.getItem(key)
    if (!text) return undefined
    const value:unknown = JSON.parse(text)
    if (accepts && !accepts(value)) {sessionStorage.removeItem(key);return undefined}
    return value as T
  }
  catch { try { sessionStorage.removeItem(key) } catch {} return undefined }
}

type CommandPhase='idle'|'submitting'|'unknown'|'confirmed'|'rejected'

/** 只复用本实例的命令互斥和反馈；回执查询、重试和采用仍由业务所有者决定。 */
export function useCommand(scope:string,onError?:(error:unknown)=>void,rejected?:(error:unknown)=>boolean) {
  const owner=useRef({scope,alive:true,busy:false})
  if(owner.current.scope!==scope)owner.current={scope,alive:true,busy:false}
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
      if(active())setState({scope,phase:'confirmed'})
      return value
    }catch(error){
      if(active()){
        setState({scope,phase:kind==='write'&&!rejected?.(error)?'unknown':'rejected',error})
        onError?.(error)
      }
    }finally{token.busy=false}
  }
  const visible:{scope:string;phase:CommandPhase;error?:unknown}=state.scope===scope?state:{scope,phase:'idle'}
  return {busy:visible.phase==='submitting',phase:visible.phase,error:visible.error,run,report}
}

export function savePending(key: string, value: unknown) {
  if (value === undefined) sessionStorage.removeItem(key)
  else sessionStorage.setItem(key, JSON.stringify(value))
}
