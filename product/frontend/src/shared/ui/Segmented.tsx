import {useRef,type ReactNode} from 'react'
import {useSelectionIndicator} from '../lib/selectionIndicator'

export function Segmented<T extends string>({label,value,items,onValueChange,disabled=false,className=''}:{label:string;value:T;items:Array<{value:T;label:ReactNode;tone?:string}>;onValueChange:(value:T)=>void;disabled?:boolean;className?:string}){
  const root=useRef<HTMLDivElement>(null)
  const indicator=useSelectionIndicator(root,'[aria-pressed=true]',value,'surface')
  return <div ref={root} className={'jj-toggle-group '+className} role="group" aria-label={label}>
    {indicator&&<span className="jj-segment-indicator" aria-hidden="true" style={indicator}/>}
    {items.map((item,index)=><button type="button" key={item.value} disabled={disabled} data-tone={item.tone} aria-pressed={value===item.value} tabIndex={value===item.value?0:-1} onClick={()=>onValueChange(item.value)} onKeyDown={event=>{
      const next=event.key==='ArrowRight'?(index+1)%items.length:event.key==='ArrowLeft'?(index+items.length-1)%items.length:event.key==='Home'?0:event.key==='End'?items.length-1:undefined
      if(next!==undefined){event.preventDefault();root.current?.querySelectorAll<HTMLButtonElement>('button')[next]?.focus();onValueChange(items[next].value)}
    }}>{item.label}</button>)}
  </div>
}
