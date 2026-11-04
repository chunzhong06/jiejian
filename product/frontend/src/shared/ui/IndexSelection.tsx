import {useRef,type ReactNode} from 'react'
import {useSelectionIndicator} from '../lib/selectionIndicator'
import './IndexSelection.css'

/** 局部索引共用连续选择面，业务保留自身的名称、状态与行内排列。 */
export function IndexSelection({children,identity,className='',as='div',label}:{children:ReactNode;identity:string;className?:string;as?:'div'|'nav'|'ol';label?:string}) {
  const root=useRef<HTMLElement|null>(null)
  const indicator=useSelectionIndicator(root,'.jj-index-item:is([aria-current=true],[aria-current=page],[aria-current=step],[aria-pressed=true])',identity,'surface')
  const Root=as,Marker=as==='ol'?'li':'span'
  return <Root ref={(node:HTMLElement|null)=>{root.current=node}} className={'jj-index-selection '+className} aria-label={label}>{indicator&&<Marker className="jj-index-surface" aria-hidden="true" style={indicator}/>} {children}</Root>
}
