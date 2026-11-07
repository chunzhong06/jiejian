import {useRef} from 'react'
import SearchOutlined from '@ant-design/icons/SearchOutlined'
import CloseOutlined from '@ant-design/icons/CloseOutlined'
import {Button} from './actions'
import './SearchField.css'

/** 只维护输入与清除；即时筛选或提交查询仍由所属工作面决定。 */
export function SearchField({label,value,onValueChange,placeholder,id,embedded=false}:{label:string;value:string;onValueChange:(value:string)=>void;placeholder:string;id?:string;embedded?:boolean}){
  const input=useRef<HTMLInputElement>(null)
  return <div className="jj-search-field" data-embedded={embedded||undefined}>
    <SearchOutlined aria-hidden="true"/>
    <input ref={input} id={id} type="search" aria-label={label} placeholder={placeholder} value={value} onChange={event=>onValueChange(event.target.value)}/>
    <span className="jj-search-clear">{value&&<Button kind="quiet" aria-label={'清除'+label} icon={<CloseOutlined aria-hidden="true"/>} onClick={()=>{onValueChange('');input.current?.focus()}}/>}</span>
  </div>
}
