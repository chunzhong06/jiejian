import {Children,isValidElement,useEffect,useState,type ReactNode} from 'react'
import {Select} from 'antd'
import CheckOutlined from '@ant-design/icons/CheckOutlined';
import DownOutlined from '@ant-design/icons/DownOutlined';
import {popupParent} from './overlay'

type Option={value:string;label:ReactNode;disabled?:boolean;title:string}

export function Choice({children,value,onValueChange,disabled,id,className,placeholder='请选择',searchable,align='start',...labels}:{children:ReactNode;value?:string|number;onValueChange:(value:string)=>void;disabled?:boolean;id?:string;className?:string;placeholder?:string;searchable?:boolean;align?:'start'|'center';'aria-label'?:string;'aria-labelledby'?:string;'aria-describedby'?:string;'aria-invalid'?:boolean|'true'|'false'}){
  const [open,setOpen]=useState(false)
  useEffect(()=>{if(disabled)setOpen(false)},[disabled])
  const options:Option[]=[]
  const collect=(nodes:ReactNode)=>Children.forEach(nodes,node=>{if(!isValidElement<{value?:string|number;children?:ReactNode;disabled?:boolean}>(node))return;if(node.type==='option')options.push({value:String(node.props.value??node.props.children??''),label:node.props.children,disabled:node.props.disabled,title:''});else collect(node.props.children)})
  collect(children)
  const selected=value===undefined||value===''&&!options.some(option=>option.value==='')?undefined:String(value)
  // 候选已失效时保留原值，避免渲染过程悄悄改选另一个业务对象。
  const unavailable=selected!==undefined&&!options.some(option=>option.value===selected)
  if(unavailable)options.unshift({value:selected!,label:'原选项已不可用',disabled:true,title:''})
  // 原生对话框持有浮层；退场时仍在DOM中的菜单也须随容器缩窄，不能仅按视口限制宽度。
  return <Select {...labels} data-align={align} id={id} className={'jj-choice '+(className??'')} data-value={String(value??'')} data-unavailable={unavailable||undefined} aria-invalid={unavailable||labels['aria-invalid']||undefined} status={labels['aria-invalid']===true||labels['aria-invalid']==='true'?'error':undefined} value={selected} placeholder={placeholder} notFoundContent="暂无可选项" disabled={disabled} open={open&&!disabled} onOpenChange={setOpen} onInputKeyDown={event=>{if(open&&event.key==='Escape'){event.preventDefault();event.stopPropagation();setOpen(false)}}} onChange={onValueChange} options={options} virtual={false} showSearch={searchable??(options.length>8||options.some(option=>typeof option.label==='string'&&option.label.length>24))} optionFilterProp="label" suffixIcon={<DownOutlined aria-hidden="true"/>} menuItemSelectedIcon={<CheckOutlined aria-hidden="true"/>} classNames={{popup:{root:'jj-choice-menu'}}} popupMatchSelectWidth styles={{popup:{root:{minWidth:220,maxWidth:'min(calc(100vw - 32px), calc(100% - 48px))'}}}} listHeight={280} getPopupContainer={popupParent}/>
}
