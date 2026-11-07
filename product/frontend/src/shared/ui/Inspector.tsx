import {useId,type ReactNode} from 'react'
import CloseOutlined from '@ant-design/icons/CloseOutlined'
import {useContentTransition} from '../lib/contentTransition'
import {Button} from './actions'

/** 目录旁的只读详情共用标题与收口；选择、返回焦点和业务事实由目录保有。 */
export function Inspector({identity,title,caption,status,onClose,children,actions}:{identity:string;title:string;caption:string;status:ReactNode;onClose:()=>void;children:ReactNode;actions?:ReactNode}){
  const id=useId(),content=useContentTransition<HTMLElement>(identity)
  return <aside className="jj-inspector" ref={content} aria-labelledby={id} onKeyDown={event=>{if(event.key==='Escape'&&!event.defaultPrevented){event.stopPropagation();onClose()}}}>
    <header className="jj-inspector-heading">
      <div className="jj-inspector-caption"><p className="jj-eyebrow">{caption}</p><Button kind="quiet" aria-label="收起详情" icon={<CloseOutlined aria-hidden="true"/>} onClick={onClose}/></div>
      <div className="jj-collection-title"><h2 id={id}>{title}</h2>{status}</div>
    </header>
    {children}
    {actions&&<footer className="jj-inspector-actions">{actions}</footer>}
  </aside>
}
