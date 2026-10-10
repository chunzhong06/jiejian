// 历史列表的规则筛选与有界整理；只有一张检查列表，规则目录不承担另一份历史展示。
import {Alert,Button,Checkbox,Select} from 'antd'
import {useCallback,useContext,useEffect,useRef,useState,type ReactNode} from 'react'
import {currentChecksApi,type RuleHistoryItem,type RuleHistoryReference,type HistoryCoverage} from '../../api/checks/currentChecks'
import {ApiError} from '../../api/http'
import {WorkPageVisible} from '../../shared/runtime/visibility'
import {useLiveRead} from '../../shared/runtime/useLiveRead'

export function RuleHistoryFilters({projectId,onError,onSelect,value,active=true,onMaintained,children}: {
  projectId:string;onError:(error:ApiError)=>void;onSelect:(ref?:RuleHistoryReference)=>void;value?:RuleHistoryReference;active?:boolean;onMaintained?:()=>void
  children?:ReactNode
}) {
  const pageVisible=useContext(WorkPageVisible),visible=pageVisible&&active,[items,setItems]=useState<RuleHistoryItem[]>([]),[cursor,setCursor]=useState<string|null>(null)
  const [archived,setArchived]=useState(false),[coverage,setCoverage]=useState<HistoryCoverage>(),[loading,setLoading]=useState(false),[failed,setFailed]=useState(false)
  const [busy,setBusy]=useState(false),[issue,setIssue]=useState<string>(),[pending,setPending]=useState<{operation_id:string;expected_checkpoint:number;limit:number}>(),[missingReceipt,setMissingReceipt]=useState(false)
  const epoch=useRef(0),live=useRef(projectId);live.current=projectId
  const loadedKey=useRef('')
  const storageKey=`jiejian-history-maintenance:${projectId}`
  const load=useCallback(async(after?:string|null)=>{
    const request=++epoch.current;setLoading(true);setFailed(false)
    try{const page=await currentChecksApi.historyRules(projectId,after,archived)
      if(request!==epoch.current)return
      if(page.project_id!==projectId||page.coverage.project_id!==projectId||after&&page.next_cursor===after)throw new ApiError('STATE_PRECONDITION','规则历史位置不一致，请重新读取。')
      setItems(previous=>after?[...previous,...page.items.filter(item=>!previous.some(old=>old.intent_id===item.intent_id&&old.revision===item.revision))]:page.items)
      setCursor(page.next_cursor);setCoverage(page.coverage)
      loadedKey.current=`${projectId}:${archived}`
    }catch(error){if(request===epoch.current){setFailed(true);onError(error as ApiError)}}finally{if(request===epoch.current)setLoading(false)}
  },[projectId,archived,onError])
  useEffect(()=>{
    if(!visible)return
    if(loadedKey.current!==`${projectId}:${archived}`){setItems([]);setCursor(null);void load()}
    return()=>{epoch.current++}
  },[load,visible])
  useEffect(()=>{live.current=projectId;setPending(undefined);setIssue(undefined);setMissingReceipt(false)
    try{const raw=sessionStorage.getItem(storageKey);if(raw)setPending(JSON.parse(raw))}catch{setIssue('无法保存整理操作的位置，暂不能开始新的整理。')}
    return()=>{live.current=''}
  },[storageKey])
  useLiveRead(visible?`${projectId}:${archived}`:undefined,async()=>{
    if(loading||busy)return
    const request=epoch.current,page=await currentChecksApi.historyRules(projectId,null,archived)
    if(request!==epoch.current)return
    if(page.project_id!==projectId)throw new ApiError('STATE_PRECONDITION','历史所属应用不一致。')
    setCoverage(page.coverage)
    setItems(previous=>cursor?previous.map(old=>page.items.find(item=>item.intent_id===old.intent_id&&item.revision===old.revision)??old):page.items)
  },5000,false)
  const finish=async()=>{sessionStorage.removeItem(storageKey);setPending(undefined);setMissingReceipt(false);setIssue(undefined);await load();onMaintained?.()}
  const maintain=async(retry=false)=>{
    if(!coverage||busy||pending&&!retry)return
    const command=retry&&pending?pending:{operation_id:crypto.randomUUID().replaceAll('-',''),expected_checkpoint:coverage.checkpoint,limit:25}
    const project=projectId
    try{sessionStorage.setItem(storageKey,JSON.stringify(command))}catch{setIssue('无法保存整理操作的位置，尚未提交。');return}
    setPending(command);setBusy(true);setIssue(undefined)
    try{const result=await currentChecksApi.maintainHistory(projectId,command)
      if(live.current!==project)return
      if(result.project_id!==projectId||result.operation_id!==command.operation_id)throw new ApiError('STATE_PRECONDITION','整理回执与原操作不一致。')
      await finish()
    }catch(error){if(live.current===project){
      // 服务明确拒绝的事务没有提交；刷新checkpoint后允许用户重新发起。网络未知仍只回读原操作。
      if(error instanceof ApiError&&['STATE_PRECONDITION','INPUT_INVALID'].includes(error.code)){await finish();onError(error)}
      else setIssue('这批整理的结果尚未确认，请先查询原操作。')
    }}
    finally{if(live.current===project)setBusy(false)}
  }
  const recover=async()=>{
    if(!pending||busy)return
    const project=projectId;setBusy(true)
    try{const response=await currentChecksApi.historyReceipt(projectId,pending.operation_id)
      if(live.current!==project)return
      if(response.status==='FOUND'&&response.receipt?.project_id===project&&response.receipt.operation_id===pending.operation_id)await finish()
      else{setMissingReceipt(true);setIssue('尚未找到这次操作的回执，可使用原操作键继续这一批。')}
    }catch{if(live.current===project)setIssue('暂时无法查询原操作，请稍后再查。')}
    finally{if(live.current===project)setBusy(false)}
  }
  const key=(ref:RuleHistoryReference)=>`${ref.intent_id}:${ref.revision}:${ref.intent_hash}`
  const available=loadedKey.current===`${projectId}:${archived}`?items:[]
  const choices=available.map(item=>({value:key(item),label:`${item.subject_label}对${item.owner_label}拥有的资源，${item.expectation==='DENY'?'不得':'可以'}${item.action_label} · 修订 ${item.revision}${item.effective_state==='RETIRED'?' · 已停用':''}`}))
  // 刷新深链或选择旧修订时，即使其候选页尚未读到，也保留原精确引用。
  if(value&&!available.some(item=>key(item)===key(value)))choices.unshift({value:key(value),label:`指定权限规则 · 修订 ${value.revision}`})
  return <section className="history-rule-filter" aria-label="权限规则筛选">
    <div className="history-rule-toolbar">
      <Select aria-label="筛选权限规则" value={value?key(value):''} loading={loading} showSearch optionFilterProp="label"
        options={[{value:'',label:'全部权限规则'},...choices]} onChange={selected=>onSelect(available.find(item=>key(item)===selected))}
        popupRender={menu=><>{menu}{cursor&&<Button block disabled={loading} onMouseDown={event=>event.preventDefault()} onClick={()=>void load(cursor)}>更多规则</Button>}</>}/>
      {children}
      {failed&&<Button onClick={()=>void load()}>重试读取规则</Button>}
    </div>
    <div className="history-filter-options">
      <Checkbox checked={archived} onChange={event=>{setCursor(null);setArchived(event.target.checked)}}>包含旧修订与已停用规则</Checkbox>
      <details className="history-index-tools"><summary>历史整理情况</summary><div className="history-index-content">{coverage?<p>已处理 {coverage.processed} 条；当前有 {coverage.failed} 条不可读记录。每批最多核对25次检查，原文件和结论保持不变。</p>:<p>整理情况尚未读取。</p>}<Button disabled={!coverage||busy||Boolean(pending)||Boolean(issue)} onClick={()=>void maintain()}>{coverage?.status==='IN_PROGRESS'?'继续整理历史':'重新核对历史索引'}</Button></div></details>
    </div>
    {coverage&&coverage.status!=='COMPLETE'&&<Alert type="warning" showIcon message={coverage.status==='INCOMPLETE'?'部分旧记录暂时不可读取':'部分旧记录尚未支持按规则筛选'}
      description="尚未整理的记录仍保留在下方列表中。筛选规则时，列表可能暂不完整。"
      action={<Button disabled={busy||Boolean(pending)||Boolean(issue)} onClick={()=>void maintain()}>{coverage.status==='IN_PROGRESS'?'继续整理历史':'整理旧记录'}</Button>}/>}
    {issue&&<Alert type="warning" showIcon message={issue}/>}
    {pending&&<div role="status" className="history-maintenance-actions"><span>有一批整理等待确认</span><Button disabled={busy} onClick={()=>void recover()}>查询整理结果</Button>{missingReceipt&&<Button disabled={busy} onClick={()=>void maintain(true)}>继续原批次</Button>}</div>}
  </section>
}
