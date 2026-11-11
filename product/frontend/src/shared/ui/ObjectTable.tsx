import {useRef,type RefObject,type TableHTMLAttributes} from 'react'
import {useSelectionIndicator} from '../lib/selectionIndicator'
import './IndexSelection.css'
import './ObjectTable.css'

/** 原生表格保留行列与按钮语义；contained 为独立比较组保留共用表框，选择行为仍共用连续移动。 */
export function ObjectTable({selection,containerRef,children,className='',appearance='context',...tableProps}:TableHTMLAttributes<HTMLTableElement>&{selection:string;containerRef?:RefObject<HTMLDivElement|null>;appearance?:'context'|'contained'}) {
  const local=useRef<HTMLDivElement>(null),root=containerRef??local
  const indicator=useSelectionIndicator(root,'tbody tr[data-selected=true]',selection,'surface')
  return <div ref={root} data-appearance={appearance==='contained'?appearance:undefined} className="jj-scroll-table jj-index-selection jj-table-selection">
    {indicator&&<span className="jj-index-surface" data-selection-indicator aria-hidden="true" style={indicator}/>}
    <table {...tableProps} className={'jj-content-table jj-object-table '+className}>{children}</table>
  </div>
}
