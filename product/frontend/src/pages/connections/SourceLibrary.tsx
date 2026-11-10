import {useWorkflow} from '../../shared/lib/workflow'
import {IndexSelection} from '../../shared/ui/IndexSelection'
import {useRef,useState} from 'react'
import './workbench.css'
import './sources.css'
import {workbenchApi as api,type ApiSource,type ImportPreview} from '../../entities/application/api/workbench'
import {useRead} from '../../shared/lib/useRead'
import {operationId,readPending,savePending,useCommand} from '../../shared/lib/operations'
import {go,readRoute} from '../../shared/lib/navigation'
import {Button} from '../../shared/ui/actions'
import {Field} from '../../shared/ui/layout'
import {FilePicker} from '../../shared/ui/FilePicker'
import {Choice} from '../../shared/ui/Choice'
import {Dialog} from '../../shared/ui/Dialog'
import {Empty,ErrorNote,Loading,Notice} from '../../shared/ui/feedback'
import {SearchField} from '../../shared/ui/SearchField'
import {SourceRequestDetails,type SourceDraft} from './SourceRequestDetails'
import {businessBoundariesApi} from '../../entities/permission/api/businessBoundaries'
import {useDirectoryState} from '../../shared/lib/directoryState'
import {editorDraft,rememberEditorDraft,editorDraftGeneration,clearSubmittedDraft,useDraftProtection} from '../../entities/runtime/model/handoff'

type PendingImport={sourceId:string;name:string;preview:ImportPreview}
const pendingImportKey=(project:string)=>'jiejian.source-import:'+project
function pendingImport(project:string){
  return readPending<PendingImport>(pendingImportKey(project),(value):value is PendingImport=>{
    if(!value||typeof value!=='object')return false
    const saved=value as Partial<PendingImport>,preview=saved.preview
    return typeof saved.sourceId==='string'&&typeof saved.name==='string'&&Boolean(preview)&&
      typeof preview!.fingerprint==='string'&&Number.isInteger(preview!.previous_revision)&&
      ['requests','warnings','added','removed','changed'].every(key=>Array.isArray(preview![key as keyof ImportPreview]))&&
      [preview!.warnings,preview!.added,preview!.removed,preview!.changed].every(items=>items.every(item=>typeof item==='string'))&&
      preview!.requests.every(item=>item&&typeof item.item_id==='string'&&typeof item.path==='string'&&typeof item.method==='string')
  })
}

export function SourceLibrary({projectId}:{projectId:string}) {
  const state=useRead('api-sources:'+projectId,signal=>api.sources(projectId,signal))
  const business=useRead('source-business:'+projectId,()=>businessBoundariesApi.current(projectId))
  const actions=business.data?.actions.filter(item=>item.effective_state==='ACTIVE')??[]
  const root=useRef<HTMLElement>(null)
  const directory=useDirectoryState('jiejian.directory:'+projectId+':source-requests',{query:'',selectedId:''},Boolean(state.data),root)
  const search=directory.value.query,setSearch=(query:string)=>directory.update({query})
  const [importing,setImporting]=useState(false),[,refreshDraft]=useState(0)
  const {busy,error,run:act}=useCommand('sources:'+projectId)
  const [importSource,setImportSource]=useState<string>()
  const lastSelected=directory.value.selectedId
  const [recovery,setRecovery]=useState(()=>pendingImport(projectId))
  // 保存回执独立于随后目录刷新；读取失败时仍能定位已经保存的来源修订。
  const [accepted,setAccepted]=useState<ApiSource>()
  const [linkedReceipt,setLinkedReceipt]=useState<{sourceId:string;requestId:string;label:string;revision:number}>()
  const workflow=useWorkflow(),query=(workflow?.route??readRoute()).query
  const selectedSource=query.get('source_id'),selectedItem=query.get('request_id')
  const sources=state.data?.sources??[]
  const rows=sources.flatMap(source=>source.requests.map(request=>({source,request,annotation:state.data?.annotations.find(item=>item.source_id===source.source_id&&item.item_id===request.item_id)})))
  const visible=rows.filter(({source,request,annotation})=>(source.name+' '+request.method+' '+request.path+' '+(annotation?.label??request.label)).toLocaleLowerCase().includes(search.toLocaleLowerCase()))
  const explicit=Boolean(selectedSource&&selectedItem),requested=rows.find(item=>item.source.source_id===selectedSource&&item.request.item_id===selectedItem)
  // 明确链接的对象优先于筛选；失效链接不能静默展示另一条请求。
  const selected=explicit?requested:selectedSource?visible.find(item=>item.source.source_id===selectedSource):visible.find(item=>item.source.source_id+':'+item.request.item_id===lastSelected)??visible[0]
  const selectedKey=selected?selected.source.source_id+':'+selected.request.item_id:''
  const hiddenSelection=Boolean(requested&&!visible.includes(requested))
  const draftKey=(key:string)=>'source-request:'+projectId+':'+key
  useDraftProtection(rows.some(item=>{const draft=editorDraft<SourceDraft>(draftKey(item.source.source_id+':'+item.request.item_id),projectId);return Boolean(draft&&(draft.label!==(item.annotation?.label??item.request.label)||draft.action!==(item.annotation?.action_id??'')))}))
  const requestOpen=selected?.source.source_id===selectedSource&&selected?.request.item_id===selectedItem
  const saveAssociation=async(draft:SourceDraft)=>{
    if(!selected)throw new Error('请先定位需要保存的请求。')
    const sourceId=selected.source.source_id,requestId=selected.request.item_id
    const key=draftKey(selectedKey),generation=editorDraftGeneration(key,projectId)
    const saved=await api.annotate(projectId,sourceId,requestId,draft.label,draft.action||null,draft.revision)
    // 迟到回执只收束提交时的草稿；其他请求与之后的输入仍由各自代次持有。
    clearSubmittedDraft(key,projectId,generation);refreshDraft(value=>value+1)
    setLinkedReceipt({sourceId,requestId,label:saved.label,revision:saved.revision});state.reload()
  }
  const openImport=(source?:string)=>{setImportSource(source);setImporting(true)}
  return <section ref={root} className="jj-source-library" aria-label="接口来源工作面" data-page-pending={state.loading&&!state.data||business.loading&&!business.data||undefined}>
    <header className="jj-source-toolbar"><div><h2>接口请求</h2>{rows.length>0&&<p><strong>{rows.length}</strong> 个请求 · {sources.length} 份来源</p>}</div>{rows.length>0&&!recovery&&<Button kind="primary" onClick={()=>openImport()}>导入资料</Button>}</header>
    {recovery&&!importing&&<Notice tone="caution">有一份来源修订的保存结果需要核对。<Button onClick={()=>openImport()}>查看上次保存结果</Button></Notice>}
    {accepted&&<Notice tone="positive">已保存“{accepted.name}”第 {accepted.revision} 修订。{state.error?'来源目录尚未更新，可重试读取。':'可继续关联其中的请求。'}<Button kind="quiet" onClick={()=>{state.reload();(workflow?.open??go)('/application?view=sources&source_id='+accepted.source_id+(accepted.requests[0]?'&request_id='+accepted.requests[0].item_id:''))}}>查看已保存的来源</Button></Notice>}
    {linkedReceipt&&<Notice tone="positive">已保存“{linkedReceipt.label}”的业务关联。{state.error?'请求目录尚未更新，保存回执已保留。':''}<Button kind="quiet" onClick={()=>{state.reload();(workflow?.open??go)('/application?view=sources&source_id='+linkedReceipt.sourceId+'&request_id='+linkedReceipt.requestId)}}>查看此请求</Button></Notice>}
    {hiddenSelection&&<Notice>当前请求被筛选条件隐藏，仍保留其详情。<Button kind="quiet" onClick={()=>setSearch('')}>清除筛选</Button></Notice>}
    {explicit&&!requested&&state.data&&<Notice tone="caution">这条链接对应的请求已不可用，请返回来源目录重新选择。</Notice>}
    {business.error&&<ErrorNote error={business.error}/>}
    {state.error&&state.data&&<ErrorNote error={state.error}/>}
    {Boolean(error)&&<ErrorNote error={error}/>}
    {state.loading&&!state.data?<Loading/>:state.error&&!state.data?<ErrorNote error={state.error}/>:rows.length?
      <div className="jj-source-workspace" data-request-open={requestOpen}>
        <aside className="jj-request-index" aria-label="请求索引">
          <div className="jj-request-search"><SearchField embedded label="查找请求" value={search} onValueChange={setSearch} placeholder="搜索名称、方法或路径"/></div>
          <IndexSelection className="jj-source-requests" label="请求列表" identity={selectedKey+search}>
            {visible.length?sources.map(source=>{const items=visible.filter(item=>item.source.source_id===source.source_id);return items.length>0&&<section className="jj-source-group" key={source.source_id}>
              <header><strong>{source.name}</strong><span>{sources.length>1?items.length+' 项 · ':''}修订 {source.revision}</span></header>
              {items.map(({source,request,annotation})=><button type="button" className="jj-request-item jj-index-item" key={request.item_id} data-directory-id={source.source_id+':'+request.item_id} aria-label={'查看请求：'+(annotation?.label??request.label)} aria-current={selectedKey===source.source_id+':'+request.item_id?'true':undefined} onClick={()=>{directory.update({selectedId:source.source_id+':'+request.item_id});directory.remember(source.source_id+':'+request.item_id);(workflow?.open??go)('/application?view=sources&source_id='+source.source_id+'&request_id='+request.item_id)}}>
                <span className="jj-request-item-line"><span className="jj-request-method">{request.method}</span><strong title={annotation?.label??request.label}>{annotation?.label??request.label}</strong></span>
                <code title={request.path}>{request.path}</code>
              </button>)}
            </section>}):<Empty title="没有匹配的请求" action={<Button onClick={()=>setSearch('')}>清除筛选</Button>}/>}
          </IndexSelection>
        </aside>
        {selected?<SourceRequestDetails key={selectedKey} projectId={projectId} {...selected} actions={actions} businessReady={Boolean(business.data)&&!business.error&&!state.error} draft={editorDraft<SourceDraft>(draftKey(selectedKey),projectId)} onDraft={value=>{rememberEditorDraft(draftKey(selectedKey),value,projectId);refreshDraft(value=>value+1)}} onSave={saveAssociation} onUpdate={()=>openImport(selected.source.source_id)} act={act} busy={busy}/>:<div className="jj-source-no-selection"><p>调整搜索条件，查看已有请求。</p></div>}
      </div>:<Empty layout="section" title="尚未导入接口资料" action={!recovery&&<Button kind="primary" onClick={()=>openImport()}>导入接口资料或请求</Button>}>导入接口文档或浏览器请求记录，选取要整理为业务操作的请求。</Empty>}
    {importing&&<SourceImport projectId={projectId} sources={sources} initialSource={importSource} onClose={()=>{setRecovery(pendingImport(projectId));setImporting(false)}} onAccepted={source=>{setAccepted(source);setRecovery(undefined);setImporting(false);state.reload()}}/>}
  </section>
}

function SourceImport({projectId,sources,initialSource,onClose,onAccepted}:{projectId:string;sources:ApiSource[];initialSource?:string;onClose:()=>void;onAccepted:(source:ApiSource)=>void}) {
  const [pending,setPending]=useState(()=>pendingImport(projectId))
  const [sourceId,setSourceId]=useState(pending?.sourceId??initialSource??''),[newId]=useState(()=>'src_'+operationId())
  const [kind,setKind]=useState<ApiSource['kind']>(sources.find(item=>item.source_id===initialSource)?.kind??'OPENAPI')
  const [name,setName]=useState(pending?.name??sources.find(item=>item.source_id===initialSource)?.name??''),[raw,setRaw]=useState('')
  const [preview,setPreview]=useState<ImportPreview|undefined>(pending?.preview),[file,setFile]=useState<File>()
  const {busy,error,run:act}=useCommand('source-import:'+projectId)
  return <Dialog closeDisabled={busy} title="导入接口资料" onClose={onClose} actions={dismiss=><><Button disabled={busy} onClick={dismiss}>取消</Button>{preview?<Button kind="primary" busy={busy} disabled={!name.trim()} onClick={()=>void act(async()=>{const input=pending??{sourceId:sourceId||newId,name:name.trim(),preview};if(pending){const actual=await api.sourceRevision(projectId,input.sourceId,input.preview.previous_revision+1);if(actual){if(actual.name!==input.name||JSON.stringify(actual.requests)!==JSON.stringify(input.preview.requests))throw new Error('此修订已有其他内容，请查看来源历史后处理。');savePending(pendingImportKey(projectId),undefined);setPending(undefined);onAccepted(actual);return}}savePending(pendingImportKey(projectId),input);setPending(input);const accepted=await api.accept(projectId,input.sourceId,input.name,input.preview);savePending(pendingImportKey(projectId),undefined);setPending(undefined);onAccepted(accepted)},'write')}>{pending?'查看上次保存结果':'保存这次导入'}</Button>:<Button kind="primary" busy={busy} disabled={!raw} onClick={()=>void act(async()=>setPreview(await api.preview(projectId,raw,kind,sourceId||undefined)))}>预览导入内容</Button>}</>}>
    <div className="jj-form-grid"><Field label="资料类型"><Choice disabled={Boolean(pending)||busy} value={kind} onValueChange={value=>{setKind(value as ApiSource['kind']);setPreview(undefined)}}><option value="OPENAPI">OpenAPI 3.0 / 3.1</option><option value="HAR">HAR 网络请求</option><option value="POSTMAN">Postman Collection 2.1</option></Choice></Field><Field label="保存到"><Choice disabled={Boolean(pending)||busy} value={sourceId} onValueChange={value=>{setSourceId(value);const item=sources.find(item=>item.source_id===value);if(item){setName(item.name);setKind(item.kind)}setPreview(undefined)}}><option value="">新的来源</option>{sources.map(item=><option key={item.source_id} value={item.source_id}>更新 {item.name}</option>)}</Choice></Field></div><Field label="来源名称"><input disabled={Boolean(pending)||busy} value={name} onChange={event=>setName(event.target.value)}/></Field><Field label="JSON 文件" hint="原始内容只用于本次解析，不写入来源资产。"><FilePicker label="JSON 文件" file={file} disabled={Boolean(pending)||busy} accept=".json,.har,application/json" formats="JSON / HAR" maxBytes={4194304} onFileChange={next=>act(async()=>{const content=next?await next.text():'';setRaw(content);setFile(next);setPreview(undefined);if(next&&!name)setName(next.name.slice(0,128))})}/></Field>
    {preview&&<section className="jj-source-preview"><h3>本次变化</h3><p>新增 {preview.added.length} · 改变 {preview.changed.length} · 来源中缺失 {preview.removed.length}</p><p className="jj-small">导入会保留人工说明和业务关联。资料中缺失的项目不会删除已确认的业务要求。</p>{preview.warnings.map(warning=><Notice tone="caution" key={warning}>{warning}</Notice>)}<details><summary>查看 {preview.requests.length} 个请求定义</summary>{preview.requests.map(item=><p className="jj-small jj-mono" key={item.item_id}>{item.method} {item.path}</p>)}</details></section>}
    {Boolean(error)&&<ErrorNote error={error}/>}
  </Dialog>
}
