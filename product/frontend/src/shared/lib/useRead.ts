import {useCallback,useEffect,useRef,useState} from 'react'

/** 按读取键持有数据；刷新保留已有内容，换键或离开后丢弃旧响应。 */
export function useRead<T>(key:string|null, read:(signal:AbortSignal)=>Promise<T>, interval:number|((data?:T)=>number)=0) {
  // key 须包含会改变结果的项目和查询条件；替换 read 回调只更新后续读取，不自动重取同键数据。
  const source=useRef(read);source.current=read
  // 自适应回调可随渲染重建；引用保存最新策略，避免因此不断重启读取。
  const timing=useRef(interval);timing.current=interval
  const [epoch,setEpoch]=useState(0)
  const [state,setState]=useState<{key:string|null;data?:T;error?:Error;loading:boolean}>({key,loading:key!==null})
  useEffect(()=>{
    if(key===null)return
    let valid=true,pending=false,timer:ReturnType<typeof setTimeout>|undefined,last:T|undefined
    const controller=new AbortController()
    setState(previous=>previous.key===key?{...previous,error:undefined,loading:previous.data===undefined}:{key,loading:true})
    const refresh=async()=>{
      if(pending||document.visibilityState==='hidden')return
      pending=true
      try{const data=await source.current(controller.signal);last=data;if(valid)setState({key,data,loading:false})}
      catch(error){if(valid)setState(previous=>({key,data:previous.key===key?previous.data:undefined,error:error instanceof Error?error:new Error('暂时无法读取，请重试。'),loading:false}))}
      finally{pending=false;const delay=typeof timing.current==='function'?timing.current(last):timing.current;if(valid&&delay)timer=setTimeout(()=>void refresh(),delay)}
    }
    // 隐藏期间不启动新读取；恢复焦点或网络后复用串行入口，避免轮询和恢复同时发请求。
    const resume=()=>{clearTimeout(timer);if(document.visibilityState!=='hidden')void refresh()}
    void refresh();document.addEventListener('visibilitychange',resume);window.addEventListener('online',resume);window.addEventListener('focus',resume)
    // 取消由读取函数执行，valid 仍拦截忽略取消信号的迟到结果。
    return()=>{valid=false;controller.abort();clearTimeout(timer);document.removeEventListener('visibilitychange',resume);window.removeEventListener('online',resume);window.removeEventListener('focus',resume)}
  },[key,epoch,typeof interval==='number'?interval:'adaptive'])
  const reload=useCallback(()=>setEpoch(value=>value+1),[])
  return {...(state.key===key?state:{key,loading:key!==null}),reload}
}
