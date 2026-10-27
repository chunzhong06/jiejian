import {cloneElement,useEffect,useId,useRef,useState,type ReactElement,type ReactNode} from 'react'
import {Popover} from 'antd'
import {popupParent} from './overlay'

export function InfoPopover({label,children,trigger,actions}:{label:string;children:ReactNode;trigger:ReactElement;actions?:ReactNode}){
  const [open,setOpen]=useState(false),root=useRef<HTMLSpanElement>(null),id=useId()
  useEffect(()=>{if(!open)return;const close=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.stopPropagation();setOpen(false);root.current?.querySelector('button')?.focus()}};document.addEventListener('keydown',close,true);return()=>document.removeEventListener('keydown',close,true)},[open])
  useEffect(()=>{if(open){const frame=requestAnimationFrame(()=>document.getElementById(id)?.focus({preventScroll:true}));return()=>cancelAnimationFrame(frame)}},[open,id])
  return <span className="jj-popover-anchor" ref={root}><Popover open={open} onOpenChange={setOpen} trigger="click" placement="bottomRight" classNames={{root:'jj-info-popover'}} getPopupContainer={popupParent} content={<section role="dialog" aria-modal="false" aria-label={label} tabIndex={-1} id={id} onClick={event=>{if((event.target as HTMLElement).closest('a[href]'))setOpen(false)}}><header className="jj-info-heading"><h3>{label}</h3>{actions}</header>{children}</section>}>{cloneElement(trigger as ReactElement<{'aria-expanded'?:boolean;'aria-haspopup'?:'dialog'}>,{'aria-expanded':open,'aria-haspopup':'dialog'})}</Popover></span>
}
