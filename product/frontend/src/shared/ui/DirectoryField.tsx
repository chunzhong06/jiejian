import {useId} from 'react'
import {Button} from './actions'
import {Field} from './layout'
import './DirectoryField.css'

/** 目录选择和手工输入共用一份值；选择只填入路径，确认动作由所属任务提供。 */
export function DirectoryField({label,value,onValueChange,onBrowse,busy=false,disabled=false,hint}:{label:string;value:string;onValueChange:(value:string)=>void;onBrowse:()=>void;busy?:boolean;disabled?:boolean;hint?:string}){
 const id=useId()
 return <div className="jj-directory-picker"><Field label={label}><input value={value} onChange={event=>onValueChange(event.target.value)} disabled={busy||disabled} aria-describedby={hint?id:undefined} placeholder="选择文件夹，或粘贴完整路径"/></Field><Button busy={busy} disabled={disabled} onClick={onBrowse}>选择文件夹</Button>{hint&&<p id={id}>{hint}</p>}</div>
}
