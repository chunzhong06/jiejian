import {useLayoutEffect,useRef,useState,type RefObject} from 'react'
import {motionMilliseconds} from './motionTiming'

type Bounds={x:number;y:number;width:number;height:number}
const axes=['x','y','width','height'] as const
const zero:Bounds={x:0,y:0,width:0,height:0}
type Motion={from:Bounds;target:Bounds;velocity:Bounds;rate:number;animation:Animation}

// 临界阻尼保留改向瞬间的位置和速度；只采样关键帧，不逐帧更新 React 或常驻 RAF。
function sample(motion:Omit<Motion,'animation'>,seconds:number){
  const position={...zero},velocity={...zero},decay=Math.exp(-motion.rate*seconds)
  for(const axis of axes){
    const distance=motion.from[axis]-motion.target[axis],impulse=motion.velocity[axis]+motion.rate*distance
    position[axis]=motion.target[axis]+(distance+impulse*seconds)*decay
    velocity[axis]=(impulse-motion.rate*(distance+impulse*seconds))*decay
  }
  return {position,velocity}
}
const frame=(bounds:Bounds)=>({width:Math.max(0,bounds.width)+'px',height:Math.max(0,bounds.height)+'px',transform:`translate3d(${bounds.x}px,${bounds.y}px,0)`})

/** 共享选择标记保持原节奏；快速改向接续当前速度，布局和焦点立即接受新选择。 */
export function useSelectionIndicator(root:RefObject<HTMLElement|null>,selector:string,identity:string,kind:'underline'|'surface'='underline'){
  const [bounds,setBounds]=useState<Bounds>(),previous=useRef<Bounds|undefined>(undefined),motion=useRef<Motion|undefined>(undefined)
  useLayoutEffect(()=>{
    const node=root.current
    if(!node)return
    const place=()=>{
      const item=node.querySelector<HTMLElement>(selector)
      if(!item){setBounds(undefined);return}
      // 分组索引和原生表格的 offsetParent 不一定是标记容器，统一换算到容器的滚动坐标。
      const area=node.getBoundingClientRect(),target=item.getBoundingClientRect()
      const next={x:target.left-area.left-node.clientLeft+node.scrollLeft,y:target.top-area.top-node.clientTop+node.scrollTop+(kind==='underline'?target.height-2:0),width:target.width,height:kind==='underline'?2:target.height}
      setBounds(previous=>previous&&previous.x===next.x&&previous.y===next.y&&previous.width===next.width&&previous.height===next.height?previous:next)
    }
    place()
    const observer='ResizeObserver' in window?new ResizeObserver(place):undefined
    observer?.observe(node)
    node.querySelectorAll<HTMLElement>('button,a').forEach(item=>observer?.observe(item))
    return()=>observer?.disconnect()
  },[root,selector,identity,kind])
  useLayoutEffect(()=>{
    const marker=root.current?.querySelector<HTMLElement>('[data-selection-indicator]'),active=motion.current
    const current=active?sample(active,Number(active.animation.currentTime??0)/1000):{position:previous.current,velocity:zero}
    active?.animation.cancel();motion.current=undefined
    previous.current=bounds
    if(!marker?.animate||!bounds||!current.position||matchMedia('(prefers-reduced-motion: reduce)').matches)return
    const duration=motionMilliseconds(getComputedStyle(marker).getPropertyValue('--motion-indicator'))
    if(!Number.isFinite(duration)||duration<=0)return
    const spring={from:current.position,target:bounds,velocity:current.velocity,rate:8/(duration/1000)}
    const length=duration*1.5
    const frames=Array.from({length:61},(_,index)=>({...frame(sample(spring,length*index/60/1000).position),offset:index/60}))
    frames[frames.length-1]={...frame(bounds),offset:1}
    const next:Motion={...spring,animation:marker.animate(frames,{duration:length,easing:'linear'})}
    motion.current=next
    next.animation.onfinish=()=>{if(motion.current===next)motion.current=undefined}
  },[bounds,root])
  useLayoutEffect(()=>{
    const preference=matchMedia('(prefers-reduced-motion: reduce)')
    const stop=()=>{if(preference.matches){motion.current?.animation.cancel();motion.current=undefined}}
    preference.addEventListener('change',stop)
    return()=>{preference.removeEventListener('change',stop);motion.current?.animation.cancel()}
  },[])
  return bounds?{width:bounds.width,height:bounds.height,transform:`translate3d(${bounds.x}px,${bounds.y}px,0)`}:undefined
}
