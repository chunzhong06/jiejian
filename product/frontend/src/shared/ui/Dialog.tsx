import {useEffect,useId,useRef,useState,type ReactNode} from 'react'
import CloseOutlined from '@ant-design/icons/CloseOutlined';
import {Button} from './actions'
import {animateOverlay,stopMotion} from '../lib/motion'

/** 取消/返回动作使用actions提供的dismiss统一退场；业务成功及导航仍由原回执立即更新。 */
export function Dialog({title,children,onClose,actions,closeDisabled=false,size='default'}:{title:string;children:ReactNode;onClose:()=>void;actions?:ReactNode|((dismiss:()=>void)=>ReactNode);closeDisabled?:boolean;size?:'default'|'wide'}){
  const ref=useRef<HTMLDialogElement>(null),heading=useRef<HTMLHeadingElement>(null),id=useId(),close=useRef(onClose),closing=useRef(false),[exiting,setExiting]=useState(false);close.current=onClose
  // 首次焦点落在标题，避免自动聚焦关闭按钮并弹出提示；卸载后只恢复仍在文档中的触发元素。
  useEffect(()=>{
    const node=ref.current,trigger=document.activeElement as HTMLElement|null
    // 连续 Escape 可在退出动效中关闭原生窗口；同步所有者，避免短暂保留已关闭的组件。
    const nativeClose=()=>close.current()
    node?.addEventListener('close',nativeClose)
    heading.current?.setAttribute('autofocus','');node?.showModal();heading.current?.focus({preventScroll:true})
    if(node)animateOverlay(node)
    return()=>{if(node)stopMotion(node,'overlay');node?.removeEventListener('close',nativeClose);node?.close();if(trigger?.isConnected)trigger.focus({preventScroll:true})}
  },[])
  useEffect(()=>{
    if(!exiting)return
    // 退出动画结束前仍保留原生模态层，先禁用内部命中，防止重复提交或点击穿透到背景。
    const node=ref.current
    if(node)node.inert=true
    const animation=node?animateOverlay(node,true):undefined
    let valid=true
    if(animation)void animation.finished.then(()=>{if(valid)close.current()}).catch(()=>{if(valid)close.current()})
    else close.current()
    const preference=matchMedia('(prefers-reduced-motion: reduce)')
    const finish=()=>{if(preference.matches&&valid){valid=false;if(node)stopMotion(node,'overlay');close.current()}}
    preference.addEventListener('change',finish)
    return()=>{valid=false;preference.removeEventListener('change',finish)}
  },[exiting])
  const dismiss=()=>{if(closeDisabled||closing.current)return;closing.current=true;if(matchMedia('(prefers-reduced-motion: reduce)').matches)close.current();else setExiting(true)}
  return <dialog className="jj-dialog" data-size={size} data-closing={exiting||undefined} ref={ref} aria-labelledby={id} onCancel={event=>{event.preventDefault();dismiss()}}><header><h2 id={id} ref={heading} tabIndex={-1} autoFocus>{title}</h2><Button kind="quiet" disabled={closeDisabled} aria-label="关闭" onClick={dismiss} icon={<CloseOutlined aria-hidden="true"/>}/></header><div className="jj-dialog-body">{children}</div>{actions&&<footer>{typeof actions==='function'?actions(dismiss):actions}</footer>}</dialog>
}
