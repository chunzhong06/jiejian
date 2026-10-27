import {useEffect,useId,useRef,useState,type ReactNode} from 'react'
import {CloseOutlined} from '@ant-design/icons'
import {Button} from './actions'

export function Dialog({title,children,onClose,actions}:{title:string;children:ReactNode;onClose:()=>void;actions?:ReactNode|((dismiss:()=>void)=>ReactNode)}){
  const ref=useRef<HTMLDialogElement>(null),heading=useRef<HTMLHeadingElement>(null),id=useId(),close=useRef(onClose),closing=useRef(false),[exiting,setExiting]=useState(false);close.current=onClose
  useEffect(()=>{const node=ref.current,trigger=document.activeElement as HTMLElement|null;heading.current?.setAttribute('autofocus','');node?.showModal();heading.current?.focus({preventScroll:true});return()=>{node?.close();if(trigger?.isConnected)trigger.focus({preventScroll:true})}},[])
  useEffect(()=>{
    if(!exiting)return
    const node=ref.current
    if(node)node.inert=true
    const token=getComputedStyle(document.documentElement).getPropertyValue('--motion-exit').trim(),duration=parseFloat(token)*(token.endsWith('ms')?1:1000)
    const timer=setTimeout(()=>close.current(),(Number.isFinite(duration)?duration:100)+32)
    return()=>clearTimeout(timer)
  },[exiting])
  const dismiss=()=>{if(closing.current)return;closing.current=true;if(matchMedia('(prefers-reduced-motion: reduce)').matches)close.current();else setExiting(true)}
  return <dialog className="jj-dialog" data-closing={exiting||undefined} ref={ref} aria-labelledby={id} onCancel={event=>{event.preventDefault();dismiss()}}><header><h2 id={id} ref={heading} tabIndex={-1} autoFocus>{title}</h2><Button kind="quiet" aria-label="关闭" onClick={dismiss} icon={<CloseOutlined aria-hidden="true"/>}/></header><div className="jj-dialog-body">{children}</div>{actions&&<footer>{typeof actions==='function'?actions(dismiss):actions}</footer>}</dialog>
}
