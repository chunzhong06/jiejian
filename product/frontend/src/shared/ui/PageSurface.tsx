import {useEffect,useLayoutEffect,useRef,type ReactNode} from 'react'
import {pageTransitionActive} from '../lib/pageTransition'

export function PageSurface({view,transitionKey=view,children}:{view:string;transitionKey?:string;children:ReactNode}) {
  const ref=useRef<HTMLDivElement>(null),running=useRef<Animation|null>(null),previous=useRef(transitionKey)
  useLayoutEffect(()=>{
    const node=ref.current,preference=window.matchMedia('(prefers-reduced-motion: reduce)')
    if(!node?.animate||preference.matches){running.current?.cancel();return}
    let observer:MutationObserver|undefined,played=false
    const changed=previous.current!==transitionKey
    previous.current=transitionKey
    const pending=()=>node.querySelector(':scope > .jj-loading,[data-page-pending="true"]')
    const wasPending=Boolean(pending())
    const play=()=>{
      if(played||pending())return
      played=true;observer?.disconnect()
      if(preference.matches||pageTransitionActive()||!changed&&!wasPending)return
      running.current?.cancel()
      running.current=node.animate(
        [{opacity:.9,transform:wasPending?'translateY(2px)':'translateY(6px)'},{opacity:1,transform:'none'}],
        {duration:wasPending?100:180,easing:'cubic-bezier(.2,0,0,1)'}
      )
    }
    if(pending()){
      running.current?.cancel()
      observer=new MutationObserver(play);observer.observe(node,{childList:true,subtree:true,attributes:true,attributeFilter:['data-page-pending']})
    }else play()
    const cancel=()=>running.current?.cancel()
    preference.addEventListener('change',cancel)
    return()=>{observer?.disconnect();running.current?.cancel();preference.removeEventListener('change',cancel)}
  },[transitionKey])
  useEffect(()=>()=>running.current?.cancel(),[])
  return <div ref={ref} className="jj-page" data-view={view}>{children}</div>
}
