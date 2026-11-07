import {useId,useRef} from 'react'
import {useSelectionIndicator} from '../lib/selectionIndicator'
import './Tabs.css'

type TabLayout={className?:string;density?:'regular'|'compact';divider?:boolean}

/** 默认包含完整外观；业务只选择密度及分隔线归属，不再补写按钮样式。 */
export function Tabs({label,value,items,onValueChange,className='',density='regular',divider=true,panelId,idPrefix}:TabLayout&{label:string;value:string;items:Array<{value:string;label:string}>;onValueChange:(value:string)=>void;panelId?:string;idPrefix?:string}){
  const root=useRef<HTMLDivElement>(null),generated=useId(),prefix=idPrefix??generated
  const indicator=useSelectionIndicator(root,'[aria-selected=true]',value+'|'+items.map(item=>item.label).join('|'))
  return <div ref={root} role="tablist" aria-label={label} className={'jj-tabs '+className} data-density={density} data-divider={divider}>{items.map((item,index)=><button type="button" role="tab" id={prefix+'-'+item.value} aria-controls={panelId} key={item.value} aria-selected={value===item.value} tabIndex={value===item.value?0:-1} onClick={()=>onValueChange(item.value)} onKeyDown={event=>{const next=event.key==='ArrowRight'?(index+1)%items.length:event.key==='ArrowLeft'?(index+items.length-1)%items.length:event.key==='Home'?0:event.key==='End'?items.length-1:undefined;if(next!==undefined){event.preventDefault();root.current?.querySelectorAll<HTMLButtonElement>('[role=tab]')[next]?.focus();onValueChange(items[next].value)}}}>{item.label}</button>)}{indicator&&<span data-selection-indicator className="jj-tab-indicator" aria-hidden="true" style={indicator}/>}</div>
}

/** 路由分类复用同一视觉所有者，仍保留链接和当前位置语义。 */
export function LinkTabs({label,value,items,onIntent,className='',density='regular',divider=true}:TabLayout&{label:string;value:string;items:Array<{value:string;label:string;href:string}>;onIntent?:(value:string)=>void}){
  const root=useRef<HTMLElement>(null)
  const indicator=useSelectionIndicator(root,'[aria-current=page]',value+'|'+items.map(item=>item.label).join('|'))
  return <nav ref={root} aria-label={label} className={'jj-tabs '+className} data-density={density} data-divider={divider}>{items.map(item=><a key={item.value} href={item.href} aria-current={value===item.value?'page':undefined} onPointerEnter={()=>onIntent?.(item.value)} onFocus={()=>onIntent?.(item.value)}>{item.label}</a>)}{indicator&&<span data-selection-indicator className="jj-tab-indicator" aria-hidden="true" style={indicator}/>}</nav>
}
