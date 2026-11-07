import {useEffect,useId,useRef,useState} from 'react'
import FileOutlined from '@ant-design/icons/FileOutlined'
import CloseOutlined from '@ant-design/icons/CloseOutlined'
import {Button} from './actions'
import './FilePicker.css'

function fileSize(bytes:number){return bytes<1024?bytes+' B':bytes<1048576?Number((bytes/1024).toFixed(1))+' KiB':Number((bytes/1048576).toFixed(1))+' MiB'}
function accepts(file:File,accept:string){return !accept||accept.split(',').some(value=>{
  const type=value.trim().toLowerCase()
  return type.startsWith('.')?file.name.toLowerCase().endsWith(type):type.endsWith('/*')?file.type.toLowerCase().startsWith(type.slice(0,-1)):file.type.toLowerCase()===type
})}

/** 只选择本地文件；解析、预览、上传及采用仍由所属任务发起。 */
export function FilePicker({label,file,onFileChange,accept='',formats='任意文件',maxBytes,disabled=false,id,'aria-labelledby':labelledBy}:{
  label:string;file?:File;onFileChange:(file:File|undefined)=>void|Promise<unknown>;accept?:string;formats?:string;maxBytes:number;disabled?:boolean;id?:string;'aria-labelledby'?:string
}){
  const input=useRef<HTMLInputElement>(null),choose=useRef<HTMLButtonElement>(null),locked=useRef(false),depth=useRef(0),restoreFocus=useRef(false)
  const [reading,setReading]=useState(false),[dragging,setDragging]=useState(false),[error,setError]=useState('')
  const identity=useId(),description=identity+'-description',errorId=identity+'-error'
  const unavailable=disabled||reading
  useEffect(()=>{if(!reading&&restoreFocus.current){restoreFocus.current=false;choose.current?.focus()}})
  const receive=async(files:File[])=>{
    // 取消和无效替换保留先前文件；同步锁覆盖业务回调触发 React 更新前的间隙。
    if(!files.length||disabled||locked.current)return
    const next=files[0]
    const invalid=files.length!==1?'请一次选择一个文件。':!next.size?'请选择非空文件。':next.size>maxBytes?'文件不能超过 '+fileSize(maxBytes)+'。':!accepts(next,accept)?'请选择 '+formats+' 文件。':''
    setError(invalid)
    if(invalid)return
    locked.current=true;setReading(true)
    try{await onFileChange(next)}catch{setError('未能读取这份文件，请重新选择。')}
    finally{locked.current=false;setReading(false)}
  }
  const clear=async()=>{
    if(disabled||locked.current)return
    locked.current=true;setReading(true)
    try{await onFileChange(undefined);setError('');restoreFocus.current=true}
    catch{setError('未能移除这份文件，请重试。')}
    finally{locked.current=false;setReading(false)}
  }
  const fileDrag=(types:readonly string[])=>types.includes('Files')
  return <div className="jj-file-picker-wrap" role="group" aria-labelledby={labelledBy} aria-label={labelledBy?undefined:label}>
    <div className="jj-file-picker" data-dragging={dragging||undefined} data-disabled={unavailable||undefined}
      onDragEnter={event=>{if(!unavailable&&fileDrag(event.dataTransfer.types)){event.preventDefault();depth.current++;setDragging(true)}}}
      onDragOver={event=>{if(fileDrag(event.dataTransfer.types)){event.preventDefault();event.dataTransfer.dropEffect=unavailable?'none':'copy'}}}
      onDragLeave={()=>{depth.current=Math.max(0,depth.current-1);if(!depth.current)setDragging(false)}}
      onDrop={event=>{event.preventDefault();depth.current=0;setDragging(false);if(!unavailable)void receive(Array.from(event.dataTransfer.files))}}>
      <FileOutlined className="jj-file-symbol" aria-hidden="true"/>
      <div className="jj-file-information"><span className="jj-file-name" role="status">{file?file.name:'拖放文件到这里'}</span><small id={description}>{file?fileSize(file.size)+' · ':''}{formats} · 最多 {fileSize(maxBytes)}</small></div>
      <div className="jj-file-actions">
        {file&&<Button kind="quiet" aria-label={'移除'+label} disabled={unavailable} icon={<CloseOutlined aria-hidden="true"/>} onClick={()=>void clear()}/>}
        <Button ref={choose} id={id} aria-label={(file?'更换':'选择')+label} aria-describedby={description+(error?' '+errorId:'')} aria-invalid={Boolean(error)||undefined} busy={reading} disabled={disabled} onClick={()=>input.current?.click()}>{file?'更换文件':'选择文件'}</Button>
      </div>
      <input ref={input} hidden type="file" accept={accept||undefined} disabled={unavailable} onChange={event=>{const files=Array.from(event.target.files??[]);event.target.value='';void receive(files)}}/>
    </div>
    {error&&<small id={errorId} className="jj-file-error" role="alert">{error}</small>}
  </div>
}
