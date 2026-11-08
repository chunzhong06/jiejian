import {forwardRef,useState,type InputHTMLAttributes} from 'react'
import EyeOutlined from '@ant-design/icons/EyeOutlined'
import EyeInvisibleOutlined from '@ant-design/icons/EyeInvisibleOutlined'
import {Button} from './actions'

/** 显示状态仅留在当前字段；离开字段组即隐藏，不复制或持久化内容。 */
export const PasswordInput=forwardRef<HTMLInputElement,Omit<InputHTMLAttributes<HTMLInputElement>,'type'>>(function PasswordInput(props,ref){
  const [shown,setShown]=useState(false)
  return <div className="jj-password-field" onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget))setShown(false)}}>
    <input {...props} ref={ref} type={shown&&!props.disabled?'text':'password'}/>
    <Button size="compact" kind="quiet" disabled={props.disabled} aria-label={shown?'隐藏密码':'显示密码'} aria-pressed={shown} icon={shown?<EyeInvisibleOutlined aria-hidden="true"/>:<EyeOutlined aria-hidden="true"/>} onMouseDown={event=>event.preventDefault()} onClick={()=>setShown(value=>!value)}/>
  </div>
})
