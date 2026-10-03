// 加载受控实例使用稳定回执；不把加载成功当作权限通过，也不重复启动未知操作。
import { Button } from 'antd'
import { useRef, useState } from 'react'
import { developmentApi, newOperationId, type DevelopmentView } from '../../../api/changes/development'
import { ApiError } from '../../../api/http'
import { clearPendingOperation, readPendingOperation, savePendingOperation } from '../pendingOperations'
export function ChangeRuntimeAction({projectId,value,onChanged,onError}:{projectId:string;value:DevelopmentView;onChanged:()=>Promise<void>;onError:(error:ApiError)=>void}){
 const pending=useRef(readPendingOperation(projectId,'runtime')),locked=useRef(false)
 const [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[uncertain,setUncertain]=useState(Boolean(pending.current)),[recover,setRecover]=useState(false)
 const run=async()=>{if(locked.current)return;const latest=value.deliveries[0];if(!latest)return;locked.current=true;setBusy(true)
 try{const wasPending=Boolean(pending.current)
   const operation=pending.current??{operation_id:newOperationId(),kind:'LOAD_RUNTIME',delivery_id:latest.delivery_id,expected_version:value.task.version}
   if(!savePendingOperation(projectId,'runtime',operation))throw new ApiError('BROWSER_STORAGE_UNAVAILABLE','无法保存加载操作定位。')
   pending.current=operation
   const receipt=wasPending&&!recover?await developmentApi.runtimeReceipt(projectId,operation.operation_id):await developmentApi.loadRuntime(projectId,operation.delivery_id!,{operation_id:operation.operation_id,expected_version:operation.expected_version!})
   if(!receipt){setUncertain(true);setRecover(Boolean(operation.delivery_id&&operation.expected_version));setMessage('尚未读到加载回执，可恢复原操作；继续沿用相同的操作定位。');return}
   if(receipt.project_id!==projectId||receipt.operation_id!==operation.operation_id||receipt.delivery_id!==operation.delivery_id)throw new ApiError('STATE_PRECONDITION','运行回执归属不一致。')
   if(receipt.status==='SUCCEEDED'||receipt.status==='FAILED'){clearPendingOperation(projectId,'runtime',operation.operation_id);pending.current=null;setUncertain(false);setMessage(receipt.status==='SUCCEEDED'?'代码已加载，接下来仍需独立检查。':'加载未完成，请核对应用环境。');await onChanged()}
   else{setUncertain(true);setRecover(receipt.status==='UNKNOWN');setMessage(receipt.status==='UNKNOWN'?'可恢复原加载，服务端会先核对已启动实例，避免重复启动。':'加载尚未确认，继续查询不会重新启动实例。')}
 }catch(error){setRecover(false);setUncertain(Boolean(pending.current));onError(error as ApiError)}finally{locked.current=false;setBusy(false)}}
 return <div><Button type="primary" loading={busy} onClick={()=>void run()}>{uncertain?recover?'恢复原加载':'查询加载回执':'加载这次修改'}</Button>{message&&<p role="status" className="light-meta">{message}</p>}</div>
}
