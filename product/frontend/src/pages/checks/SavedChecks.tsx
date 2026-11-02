import {useRef,useState} from 'react'
import DeleteOutlined from '@ant-design/icons/DeleteOutlined'
import type {PermissionReference} from '../../entities/preparation/api/preparation'
import {request} from '../../shared/api/http'
import {useRead} from '../../shared/lib/useRead'
import {readPending,savePending} from '../../shared/lib/operations'
import {Button} from '../../shared/ui/actions'
import {Choice} from '../../shared/ui/Choice'
import {ErrorNote,Notice} from '../../shared/ui/feedback'

type Routine={routine_id:string;name:string;selected_permissions:PermissionReference[]|null;current:boolean;stale_intents:string[]}
type Saving={operation_id:string;name:string;selected_permissions:PermissionReference[]|null}

export function SavedChecks({projectId,selected,disabled,onChange,name}:{projectId:string;selected:PermissionReference[]|null;disabled:boolean;onChange:(value:PermissionReference[]|null)=>void;name?:string}){
  const base='/api/projects/'+encodeURIComponent(projectId)+'/check-routines'
  const pendingKey='jiejian.studio.saved-scope:'+projectId
  const saved=useRead('check-routines:'+projectId,()=>request<Routine[]>(base))
  const [choice,setChoice]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),[message,setMessage]=useState('')
  const selectedRoutine=saved.data?.find(item=>item.routine_id===choice)
  const shownChoice=selectedRoutine?.current&&JSON.stringify(selectedRoutine.selected_permissions)!==JSON.stringify(selected)?'':choice
  const alreadySaved=saved.data?.some(item=>item.current&&JSON.stringify(item.selected_permissions)===JSON.stringify(selected))
  // 保存结果未知时沿用同一内容和请求，不因重复点击形成另一份方案。
  const pending=useRef<Saving|undefined>(readPending<Saving>(pendingKey))
  const apply=(id:string)=>{
    setChoice(id);setMessage('')
    const value=saved.data?.find(item=>item.routine_id===id)
    if(!value)return
    if(!value.current){setMessage('这份方案中的部分规则已变化。请重新选择规则，再保存新的范围。');return}
    onChange(value.selected_permissions)
  }
  const remember=async()=>{
    setBusy(true);setError(undefined);setMessage('')
    const snapshot=JSON.stringify(selected)
    if(!pending.current){pending.current={operation_id:crypto.randomUUID().replaceAll('-',''),name:selected===null?'全部已批准规则':name||`${selected.length} 条权限规则`,selected_permissions:selected};savePending(pendingKey,pending.current)}
    const original=JSON.stringify(pending.current.selected_permissions)!==snapshot
    try{await request(base,{method:'POST',body:JSON.stringify(pending.current)});pending.current=undefined;savePending(pendingKey,undefined);saved.reload();setMessage(original?'上次的选择已保存，本次选择保持不变。':'已保存。下次检查可直接沿用这份范围。')}
    catch(value){setError(value)}finally{setBusy(false)}
  }
  const remove=async()=>{
    setBusy(true);setError(undefined)
    try{await request(base+'/'+encodeURIComponent(choice),{method:'DELETE'});setChoice('');saved.reload();setMessage('已移除保存项，本次选择保持不变。')}
    catch(value){setError(value)}finally{setBusy(false)}
  }
  return <div className="jj-saved-checks">
    <div className="jj-saved-checks-bar">{Boolean(saved.data?.length)&&<Choice aria-label="沿用检查范围" value={shownChoice} disabled={disabled||busy} onValueChange={apply}><option value="">沿用保存的检查范围</option>{(saved.data??[]).map(item=><option key={item.routine_id} value={item.routine_id}>{item.name+(item.current?'':'（需要重新选择）')}</option>)}</Choice>}
      {shownChoice&&<Button kind="quiet" icon={<DeleteOutlined/>} aria-label="移除此检查方案" disabled={disabled||busy} onClick={()=>void remove()}/>}
      <Button kind="quiet" disabled={disabled||busy||!pending.current&&(selected?.length===0||alreadySaved)} busy={busy} onClick={()=>void remember()}>{pending.current?'核对上次保存':alreadySaved?'已记住当前选择':'记住当前选择'}</Button>
    </div>
    {message&&<Notice>{message}</Notice>}{Boolean(error||saved.error)&&<ErrorNote error={error??saved.error} onRetry={saved.reload}/>}
  </div>
}
