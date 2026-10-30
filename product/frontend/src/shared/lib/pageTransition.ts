import {flushSync} from 'react-dom'

let active:ViewTransition|null=null
let appearanceAnimation:Animation|null=null

export function pageTransitionActive(){return active!==null}

function commit(update:()=>void,direction='forward'){
  // 新导航立即接管旧快照，不排队播放；完成回调也只能清理自己仍拥有的过渡状态。
  appearanceAnimation?.cancel();appearanceAnimation=null
  active?.skipTransition()
  if(!document.startViewTransition||matchMedia('(prefers-reduced-motion: reduce)').matches){
    active=null
    delete document.documentElement.dataset.visualTransition
    delete document.documentElement.dataset.pageDirection
    update()
    return
  }
  document.documentElement.dataset.visualTransition='page'
  document.documentElement.dataset.pageDirection=direction
  // 同步提交 React 路由后再取新快照；数据尚未就绪时的内容出现由 PageSurface 单独处理。
  const next=document.startViewTransition(()=>flushSync(update))
  active=next
  void next.ready.catch(()=>{})
  void next.finished.catch(()=>{}).finally(()=>{if(active===next){
    active=null
    delete document.documentElement.dataset.visualTransition
    delete document.documentElement.dataset.pageDirection
  }})
}
export const commitPageTransition=(update:()=>void,direction='forward')=>commit(update,direction)
export function commitThemeTransition(update:()=>void){
  active?.skipTransition();active=null
  appearanceAnimation?.cancel();appearanceAnimation=null
  delete document.documentElement.dataset.visualTransition
  delete document.documentElement.dataset.pageDirection
  flushSync(update)
  // 整页快照会暂停真实控件的命中；主题淡入保留导航与业务操作的点击能力。
  if(!matchMedia('(prefers-reduced-motion: reduce)').matches&&document.documentElement.animate)
    appearanceAnimation=document.documentElement.animate([{opacity:.96},{opacity:1}],{duration:100,easing:'ease-out'})
}
