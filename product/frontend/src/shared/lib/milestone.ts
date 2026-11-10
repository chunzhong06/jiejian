import {useEffect,useRef} from 'react'
import {animateMotion,reducedMotion,stopMotion} from './motion'

export type MilestoneKind='connection'|'rules'|'materials'|'revision'|'report'|'repair'|'collaboration'|'cleanup'
const pending=new Map<string,number>()
const eventName='jj-milestone-receipt'

/** 只接纳调用方已经回读确认的回执身份；不持久化、不代替业务完成判断。 */
export function markMilestone(identity:string){
  const now=Date.now()
  for(const [key,time] of pending)if(now-time>30000)pending.delete(key)
  pending.set(identity,now)
  if(pending.size>32)pending.delete(pending.keys().next().value!)
  window.dispatchEvent(new CustomEvent(eventName,{detail:identity}))
}

/** 一次真实交接只编排一次；回访、轮询和旧回执不会重复播放。 */
export function useMilestone<T extends HTMLElement=HTMLDivElement>(identity:string,ready:boolean,kind:MilestoneKind){
  const root=useRef<T>(null)
  useEffect(()=>{
    const node=root.current
    if(!node||!ready)return
    const animated=new Set<HTMLElement>()
    const play=()=>{
      if(!pending.delete(identity)||reducedMotion()||document.visibilityState==='hidden')return
      node.dataset.milestoneActive=kind
      const parts=Array.from(node.querySelectorAll<HTMLElement>('[data-milestone-part]'))
      const heading=node.querySelector<HTMLElement>(':scope > .jj-heading')
      if(heading&&!parts.some(part=>part===heading||part.contains(heading)))parts.unshift(heading)
      const groups=parts.length?parts.filter(part=>!parts.some(child=>child!==part&&part.contains(child))):[node]
      const expressive=kind==='repair'||kind==='report'
      let last:Animation|undefined
      for(const [index,part] of groups.entries()){
        animated.add(part)
        const role=part.dataset.milestonePart
        const delay=role==='actions'?(expressive?400:220):Math.min(index*90,270)
        const duration=expressive?560:420
        animateMotion(part,'appearance',[{opacity:.38},{opacity:1}],{duration,delay,easing:'cubic-bezier(.16,1,.3,1)',fill:'backwards'})
        last=animateMotion(part,'position',[{translate:`0 ${role==='actions'?8:expressive?12:6}px`},{translate:'0 0'}],{duration,delay,easing:'cubic-bezier(.16,1,.3,1)',fill:'backwards'})
      }
      const symbol=node.querySelector<HTMLElement>('.jj-report-symbol,.jj-result-summary > .anticon')
      if(symbol){animated.add(symbol);animateMotion(symbol,'appearance',[{scale:.72,opacity:.35},{scale:1.06,opacity:1,offset:.65},{scale:1,opacity:1}],{duration:expressive?680:460,delay:100,easing:'cubic-bezier(.16,1,.3,1)'})}
      const accent=node.querySelector<HTMLElement>('[data-milestone-accent]')
      if(accent){animated.add(accent);animateMotion(accent,'appearance',[{scale:'0 1',opacity:.4},{scale:'1 1',opacity:1}],{duration:expressive?620:460,easing:'cubic-bezier(.22,1,.36,1)'})}
      if(last)void last.finished.catch(()=>{}).finally(()=>{delete node.dataset.milestoneActive})
      else delete node.dataset.milestoneActive
    }
    play()
    const receive=(event:Event)=>{if((event as CustomEvent<string>).detail===identity)play()}
    window.addEventListener(eventName,receive)
    return()=>{window.removeEventListener(eventName,receive);delete node.dataset.milestoneActive;for(const part of animated){stopMotion(part,'appearance');stopMotion(part,'position')}}
  },[identity,ready,kind])
  return root
}

/** 同一对象先观察到未完成，再接到明确完成事实才编排；初次读取终态保持安静。 */
export function useMilestoneTransition<T extends HTMLElement=HTMLDivElement>(identity:string,complete:boolean|undefined,kind:MilestoneKind){
  const root=useMilestone<T>(identity,complete===true,kind)
  const previous=useRef<{identity:string;complete:boolean}|undefined>(undefined)
  useEffect(()=>{
    if(complete===undefined)return
    const before=previous.current
    previous.current={identity,complete}
    if(before?.identity===identity&&!before.complete&&complete)markMilestone(identity)
  },[identity,complete])
  return root
}
