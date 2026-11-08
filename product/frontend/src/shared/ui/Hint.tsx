import {cloneElement,useEffect,useState,type ReactElement} from 'react'
import {Tooltip} from 'antd'
import {popupParent} from './overlay'

let viewportLayer:HTMLElement|undefined
function hintParent(trigger:HTMLElement){
  const parent=popupParent(trigger)
  // 收起中的提示可能暂留缩窗前的坐标；独立视口层防止它撑宽正文，Dialog 仍使用原顶层。
  if(parent!==document.body)return parent
  if(!viewportLayer?.isConnected){viewportLayer=document.createElement('div');viewportLayer.className='jj-hint-layer';document.body.append(viewportLayer)}
  return viewportLayer
}

export function Hint({label,children,disabled=false}:{label:string;children:ReactElement;disabled?:boolean}){
  const [open,setOpen]=useState(false)
  useEffect(()=>{if(disabled)setOpen(false)},[disabled])
  useEffect(()=>{if(!open)return;const close=(event:KeyboardEvent)=>{if(event.key==='Escape')setOpen(false)};document.addEventListener('keydown',close);return()=>document.removeEventListener('keydown',close)},[open])
  const trigger=children as ReactElement<{onClick?:(event:React.MouseEvent<HTMLElement>)=>void}>
  return <Tooltip title={label} open={!disabled&&open} onOpenChange={value=>setOpen(!disabled&&value)} trigger={disabled?[]:['hover','focus']} mouseEnterDelay={.35} mouseLeaveDelay={.08} classNames={{root:'jj-hint'}} getPopupContainer={hintParent}>{cloneElement(trigger,{onClick:event=>{setOpen(false);trigger.props.onClick?.(event)}})}</Tooltip>
}
