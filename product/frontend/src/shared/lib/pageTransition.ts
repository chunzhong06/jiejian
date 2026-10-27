import {flushSync} from 'react-dom'

let active:ViewTransition|null=null
let mode:'page'|'theme'|null=null

export function pageTransitionActive(){return active!==null&&mode==='page'}

function commit(update:()=>void,kind:'page'|'theme',direction='forward'){
  active?.skipTransition()
  if(!document.startViewTransition||matchMedia('(prefers-reduced-motion: reduce)').matches){
    active=null
    mode=null
    delete document.documentElement.dataset.visualTransition
    delete document.documentElement.dataset.pageDirection
    update()
    return
  }
  document.documentElement.dataset.visualTransition=kind
  document.documentElement.dataset.pageDirection=direction
  const next=document.startViewTransition(()=>flushSync(update))
  active=next
  mode=kind
  void next.ready.catch(()=>{})
  void next.finished.catch(()=>{}).finally(()=>{if(active===next){
    active=null;mode=null
    delete document.documentElement.dataset.visualTransition
    delete document.documentElement.dataset.pageDirection
  }})
}
export const commitPageTransition=(update:()=>void,direction='forward')=>commit(update,'page',direction)
export const commitThemeTransition=(update:()=>void)=>commit(update,'theme')
