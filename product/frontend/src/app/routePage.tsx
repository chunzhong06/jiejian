import {createElement,useEffect,useSyncExternalStore,type ComponentType,type ComponentProps} from 'react'
import {PageSkeleton} from '../shared/ui/PageSkeleton'

// 模块就绪立即挂载，不把数据等待叠加到 Suspense 回退周期。
export function routePage<C extends ComponentType<any>>(read:()=>Promise<{default:C}>,view:string){
  let state:{Component?:C;error?:Error}={}
  let pending:Promise<void>|undefined
  const listeners=new Set<()=>void>()
  const subscribe=(listener:()=>void)=>{listeners.add(listener);return()=>{listeners.delete(listener)}}
  const snapshot=()=>state
  const preload=()=>{
    if(!pending)pending=read().then(
      module=>{state={Component:module.default};listeners.forEach(listener=>listener())},
      error=>{state={error:error instanceof Error?error:new Error('页面暂时无法打开，请重新加载。')};listeners.forEach(listener=>listener())}
    )
    return pending
  }
  function Page(props:ComponentProps<C>){
    const {Component,error}=useSyncExternalStore(subscribe,snapshot)
    useEffect(()=>{void preload()},[])
    if(error)throw error
    return Component?createElement(Component,props):<PageSkeleton view={view}/>
  }
  return Object.assign(Page,{preload})
}
