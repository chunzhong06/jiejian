import {createElement,useEffect,useRef,useSyncExternalStore,type ComponentType,type ComponentProps} from 'react'
import {PageSkeleton,pageTitle} from '../ui/PageSkeleton'
import {PageError,ErrorNote,Loading} from '../ui/feedback'
import {usePageRefresh} from './pageRefresh'
import {readRoute,type Route} from './navigation'
import {directoryNavigation} from '../ui/SectionNavigation'

// 模块就绪立即挂载，不把数据等待叠加到 Suspense 回退周期。
export function routePage<C extends ComponentType<any>>(read:()=>Promise<{default:C}>,view:string,{embedded=false}:{embedded?:boolean}={}){
  let state:{Component?:C;error?:Error}={}
  let pending:Promise<void>|undefined
  const listeners=new Set<()=>void>()
  const subscribe=(listener:()=>void)=>{listeners.add(listener);return()=>{listeners.delete(listener)}}
  const snapshot=()=>state
  const preload=(retry=false)=>{
    if(retry&&state.error){state={};pending=undefined}
    if(!pending)pending=read().then(
      module=>{state={Component:module.default};listeners.forEach(listener=>listener())},
      error=>{state={error:new Error('页面资源暂时未能加载，请使用右上角刷新重试。',{cause:error})};listeners.forEach(listener=>listener())}
    )
    return pending
  }
  function Page(props:ComponentProps<C>){
    const {Component,error}=useSyncExternalStore(subscribe,snapshot)
    const mounted=useRef(true)
    usePageRefresh(async()=>{
      if(!error)return
      await preload(true)
      // 浏览器可能缓存失败的模块依赖；用户主动重试仍失败时重载原地址，清除该文档的导入缓存。
      if(state.error&&mounted.current)window.location.reload()
    })
    useEffect(()=>{mounted.current=true;void preload();return()=>{mounted.current=false}},[])
    if(Component)return createElement(Component,props)
    // 内嵌模块只替换所属内容；父页面继续持有标题、分类与准确回程。
    if(embedded)return error?<ErrorNote error={error}/>:<Loading/>
    const context=props as {route?:Route;projectId?:string;selected?:{project_id:string}}
    const directory=directoryNavigation(view,context.route??readRoute(),context.projectId??context.selected?.project_id)
    if(error)return <PageError title={directory?.title??pageTitle(view)} navigation={directory?.navigation} error={error}/>
    return <PageSkeleton view={view} title={directory?.title} navigation={directory?.navigation}/>
  }
  return Object.assign(Page,{preload})
}
