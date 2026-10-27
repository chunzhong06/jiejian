import {useCallback,useEffect,useRef,useState} from 'react'

export function useRead<T>(key:string|null, read:(signal:AbortSignal)=>Promise<T>, interval:number|((data?:T)=>number)=0) {
  const source=useRef(read);source.current=read
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
    const resume=()=>{clearTimeout(timer);if(document.visibilityState!=='hidden')void refresh()}
    void refresh();document.addEventListener('visibilitychange',resume);window.addEventListener('online',resume)
    return()=>{valid=false;controller.abort();clearTimeout(timer);document.removeEventListener('visibilitychange',resume);window.removeEventListener('online',resume)}
  },[key,epoch,typeof interval==='number'?interval:'adaptive'])
  const reload=useCallback(()=>setEpoch(value=>value+1),[])
  return {...(state.key===key?state:{key,loading:key!==null}),reload}
}
