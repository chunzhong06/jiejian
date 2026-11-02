import {Children,isValidElement,useState,type ReactNode} from 'react'
import {Select} from 'antd'
import CheckOutlined from '@ant-design/icons/CheckOutlined';
import DownOutlined from '@ant-design/icons/DownOutlined';
import {popupParent} from './overlay'

type Option={value:string;label:ReactNode;disabled?:boolean;title:string}

export function Choice({children,value,onValueChange,disabled,id,className,placeholder='请选择',...labels}:{children:ReactNode;value?:string|number;onValueChange:(value:string)=>void;disabled?:boolean;id?:string;className?:string;placeholder?:string;'aria-label'?:string;'aria-labelledby'?:string}){
  const [open,setOpen]=useState(false)
  const options:Option[]=[]
  const collect=(nodes:ReactNode)=>Children.forEach(nodes,node=>{if(!isValidElement<{value?:string|number;children?:ReactNode;disabled?:boolean}>(node))return;if(node.type==='option')options.push({value:String(node.props.value??node.props.children??''),label:node.props.children,disabled:node.props.disabled,title:''});else collect(node.props.children)})
  collect(children)
  const selected=value===undefined||value===''&&!options.some(option=>option.value==='')?undefined:String(value)
  // 候选已失效时保留原值，避免渲染过程悄悄改选另一个业务对象。
  const unavailable=selected!==undefined&&!options.some(option=>option.value===selected)
  if(unavailable)options.unshift({value:selected!,label:'原选项已不可用',disabled:true,title:''})
  return <Select {...labels} id={id} className={'jj-choice '+(className??'')} data-value={String(value??'')} data-unavailable={unavailable||undefined} aria-invalid={unavailable||undefined} value={selected} placeholder={placeholder} notFoundContent="暂无可选项" disabled={disabled} open={open} onOpenChange={setOpen} onInputKeyDown={event=>{if(open&&event.key==='Escape'){event.preventDefault();event.stopPropagation();setOpen(false)}}} onChange={onValueChange} options={options} virtual={false} showSearch={options.length>8} optionFilterProp="label" suffixIcon={<DownOutlined aria-hidden="true"/>} menuItemSelectedIcon={<CheckOutlined aria-hidden="true"/>} classNames={{popup:{root:'jj-choice-menu'}}} popupMatchSelectWidth styles={{popup:{root:{minWidth:220,maxWidth:'calc(100vw - 32px)'}}}} listHeight={280} getPopupContainer={popupParent}/>
}
