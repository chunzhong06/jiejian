import {useId,useLayoutEffect,useRef,useState} from 'react'

export function Tabs({label,value,items,onValueChange,className,panelId,idPrefix}:{label:string;value:string;items:Array<{value:string;label:string}>;onValueChange:(value:string)=>void;className?:string;panelId?:string;idPrefix?:string}){
  const root=useRef<HTMLDivElement>(null),generated=useId(),prefix=idPrefix??generated
  const [indicator,setIndicator]=useState<{left:number;top:number;width:number}>()
  useLayoutEffect(()=>{
    const node=root.current
    if(!node)return
    const place=()=>{const selected=node.querySelector<HTMLButtonElement>('[aria-selected=true]');if(!selected)return;const next={left:selected.offsetLeft,top:selected.offsetTop+selected.offsetHeight-2,width:selected.offsetWidth};setIndicator(previous=>previous&&previous.left===next.left&&previous.top===next.top&&previous.width===next.width?previous:next)}
    place()
    const observer='ResizeObserver' in window?new ResizeObserver(place):undefined
    observer?.observe(node)
    return()=>observer?.disconnect()
  },[value,items.map(item=>item.label).join('|')])
  return <div ref={root} role="tablist" aria-label={label} className={'jj-tabs '+(className??'')}>{items.map((item,index)=><button role="tab" id={prefix+'-'+item.value} aria-controls={panelId} key={item.value} aria-selected={value===item.value} tabIndex={value===item.value?0:-1} onClick={()=>onValueChange(item.value)} onKeyDown={event=>{const next=event.key==='ArrowRight'?(index+1)%items.length:event.key==='ArrowLeft'?(index+items.length-1)%items.length:event.key==='Home'?0:event.key==='End'?items.length-1:undefined;if(next!==undefined){event.preventDefault();root.current?.querySelectorAll<HTMLButtonElement>('[role=tab]')[next]?.focus();onValueChange(items[next].value)}}}>{item.label}</button>)}{indicator&&<span className="jj-tab-indicator" aria-hidden="true" style={{width:indicator.width,transform:`translate3d(${indicator.left}px,${indicator.top}px,0)`}}/>}</div>
}
