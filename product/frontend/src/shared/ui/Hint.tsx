import {cloneElement,useEffect,useState,type ReactElement} from 'react'
import {Tooltip} from 'antd'
import {popupParent} from './overlay'

export function Hint({label,children,disabled=false}:{label:string;children:ReactElement;disabled?:boolean}){
  const [open,setOpen]=useState(false)
  useEffect(()=>{if(disabled)setOpen(false)},[disabled])
  useEffect(()=>{if(!open)return;const close=(event:KeyboardEvent)=>{if(event.key==='Escape')setOpen(false)};document.addEventListener('keydown',close);return()=>document.removeEventListener('keydown',close)},[open])
  const trigger=children as ReactElement<{onClick?:(event:React.MouseEvent<HTMLElement>)=>void}>
  return <Tooltip title={label} open={!disabled&&open} onOpenChange={value=>setOpen(!disabled&&value)} trigger={disabled?[]:['hover','focus']} mouseEnterDelay={.35} mouseLeaveDelay={.08} classNames={{root:'jj-hint'}} getPopupContainer={popupParent}>{cloneElement(trigger,{onClick:event=>{setOpen(false);trigger.props.onClick?.(event)}})}</Tooltip>
}
