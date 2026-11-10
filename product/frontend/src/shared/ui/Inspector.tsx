import {ObjectHeading} from './layout'
import {useId,type ReactNode} from 'react'
import CloseOutlined from '@ant-design/icons/CloseOutlined'
import {useContentTransition} from '../lib/contentTransition'
import {Button} from './actions'

/** 目录旁的只读详情共用标题与收口；选择、返回焦点和业务事实由目录保有。 */
export function Inspector({identity,title,caption,status,onClose,children,actions}:{identity:string;title:string;caption:string;status:ReactNode;onClose:()=>void;children:ReactNode;actions?:ReactNode}){
  const id=useId(),content=useContentTransition<HTMLElement>(identity)
  const dismiss=()=>{
    const directory=content.current?.closest('.jj-collection')
    onClose()
    // 窄窗在详情期间隐藏目录；等原目录重新可见后归还原项焦点，不重建目录状态。
    requestAnimationFrame(()=>{if(!document.querySelector('dialog[open]'))directory?.querySelector<HTMLElement>('.jj-object-select[aria-pressed=true]')?.focus({preventScroll:true})})
  }
  return <aside className="jj-inspector" ref={content} aria-labelledby={id} aria-describedby={id+'-context'} onKeyDown={event=>{if(event.key==='Escape'&&!event.defaultPrevented){event.stopPropagation();dismiss()}}}>
    <header className="jj-inspector-heading">
      <p id={id+'-context'} className="jj-sr-only">{caption}</p>
      <ObjectHeading id={id} title={title} status={status}/>
      <Button kind="quiet" aria-label="收起详情" icon={<CloseOutlined aria-hidden="true"/>} onClick={dismiss}/>
    </header>
    {children}
    {actions&&<footer className="jj-inspector-actions">{actions}</footer>}
  </aside>
}
