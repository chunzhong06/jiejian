import {Children,isValidElement,useState,type ReactNode} from 'react'
import {Select} from 'antd'
import {CheckOutlined,DownOutlined} from '@ant-design/icons'
import {popupParent} from './overlay'

type Option={value:string;label:ReactNode;disabled?:boolean;title:string}

export function Choice({children,value,onValueChange,disabled,id,className,...labels}:{children:ReactNode;value?:string|number;onValueChange:(value:string)=>void;disabled?:boolean;id?:string;className?:string;'aria-label'?:string;'aria-labelledby'?:string}){
  const [open,setOpen]=useState(false)
  const options:Option[]=[]
  const collect=(nodes:ReactNode)=>Children.forEach(nodes,node=>{if(!isValidElement<{value?:string|number;children?:ReactNode;disabled?:boolean}>(node))return;if(node.type==='option')options.push({value:String(node.props.value??node.props.children??''),label:node.props.children,disabled:node.props.disabled,title:''});else collect(node.props.children)})
  collect(children)
  return <Select {...labels} id={id} className={'jj-choice '+(className??'')} data-value={String(value??'')} value={String(value??'')} disabled={disabled} open={open} onOpenChange={setOpen} onInputKeyDown={event=>{if(open&&event.key==='Escape'){event.preventDefault();event.stopPropagation();setOpen(false)}}} onChange={onValueChange} options={options} virtual={false} showSearch={options.length>8} optionFilterProp="label" suffixIcon={<DownOutlined aria-hidden="true"/>} menuItemSelectedIcon={<CheckOutlined aria-hidden="true"/>} classNames={{popup:{root:'jj-choice-menu'}}} popupMatchSelectWidth={false} styles={{popup:{root:{minWidth:220,maxWidth:'calc(100vw - 32px)'}}}} listHeight={280} getPopupContainer={popupParent}/>
}
