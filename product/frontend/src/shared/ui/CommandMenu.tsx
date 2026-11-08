import {cloneElement,useEffect,useId,useRef,useState,type ButtonHTMLAttributes,type ReactElement} from 'react'
import {Dropdown,type DropdownProps} from 'antd'
import {popupParent} from './overlay'
import {motionMilliseconds} from '../lib/motionTiming'

/** 短命令列表共用打开、取消和焦点归还；业务决定仍由菜单所属页面执行。 */
export function CommandMenu({children,menu,className='',placement='bottomRight'}:{
  children:ReactElement<ButtonHTMLAttributes<HTMLButtonElement>>;menu:NonNullable<DropdownProps['menu']>;className?:string;placement?:DropdownProps['placement']
}){
  const [phase,setPhase]=useState<'closed'|'opening'|'open'|'closing'>('closed'),trigger=useRef<HTMLButtonElement|null>(null),id=useId()
  const disabled=Boolean(children.props.disabled)
  const open=phase==='opening'||phase==='open',visible=useRef(false);visible.current=open&&!disabled
  useEffect(()=>{if(disabled)setPhase('closed')},[disabled])
  useEffect(()=>{
    if(phase!=='opening'||disabled)return
    let frame=0,attempts=0
    // 组件库的延迟自动聚焦不会在关闭时取消；由菜单所有者接管，避免退出后抢走焦点。
    const focus=()=>{
      if(!visible.current)return
      const node=document.getElementById(id)
      if(node?.getClientRects().length){
        const item=node.querySelector<HTMLElement>('.ant-dropdown-menu-item-selected:not([aria-disabled=true])')??node.querySelector<HTMLElement>('[role=menuitem]:not([aria-disabled=true])')
        const target=item??node;target.focus({preventScroll:true})
        setPhase('open')
      }else if(++attempts<4)frame=requestAnimationFrame(focus)
      else setPhase('open')
    }
    frame=requestAnimationFrame(focus)
    return()=>cancelAnimationFrame(frame)
  },[phase,disabled,id])
  useEffect(()=>{
    if(phase!=='closing')return
    // 同一所有者完成退场；快速反向不依赖组件库可能缺失的 transitionend。
    const duration=motionMilliseconds(getComputedStyle(document.documentElement).getPropertyValue('--motion-exit'),160)
    const timer=setTimeout(()=>setPhase('closed'),duration+32)
    return()=>clearTimeout(timer)
  },[phase])
  const dismiss=()=>{visible.current=false;setPhase(matchMedia('(prefers-reduced-motion: reduce)').matches?'closed':'closing')}
  // 后续命令可能立即打开对话框；先归还焦点，让新任务接管并记住正确的返回位置。
  const close=()=>{dismiss();if(trigger.current?.isConnected)trigger.current.focus({preventScroll:true})}
  return <Dropdown open={phase!=='closed'&&!disabled} disabled={disabled} onOpenChange={value=>{if(value)setPhase('opening');else dismiss()}} trigger={['click']} placement={placement} autoFocus={false} destroyOnHidden transitionName="" getPopupContainer={popupParent} overlayClassName={'jj-command-menu '+className} popupRender={content=><div className="jj-menu-surface" data-open={phase==='open'} inert={!open}>{content}</div>} overlayStyle={{opacity:phase==='open'?1:0,pointerEvents:phase==='closing'?'none':undefined,transitionDuration:phase==='closing'?'var(--motion-exit)':'var(--motion-popup)',transitionTimingFunction:phase==='closing'?'var(--ease-exit)':'var(--ease-enter)'}} menu={{...menu,id, onClick:event=>{close();menu.onClick?.(event)},onKeyDown:event=>{
    if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close()}
    else menu.onKeyDown?.(event)
  }}}>{cloneElement(children,{'aria-haspopup':'menu','aria-expanded':open&&!disabled,'aria-controls':open?id:undefined,onClick:event=>{trigger.current=event.currentTarget;children.props.onClick?.(event)},onKeyDown:event=>{
    children.props.onKeyDown?.(event)
    // 浮层自动焦点可能尚未完成；入口仍须立即响应 Escape，并阻止关闭外层对话框。
    if(!event.defaultPrevented&&event.key==='Escape'&&open){event.preventDefault();event.stopPropagation();close()}
    else if(!event.defaultPrevented&&event.key==='ArrowDown'&&!disabled){event.preventDefault();trigger.current=event.currentTarget;setPhase('opening')}
  }})}</Dropdown>
}
