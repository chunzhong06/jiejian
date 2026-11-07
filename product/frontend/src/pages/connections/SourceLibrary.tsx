import {IndexSelection} from '../../shared/ui/IndexSelection'
import {useState} from 'react'
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
  const [search,setSearch]=useState(''),[importing,setImporting]=useState(false)
  const {busy,error,run:act}=useCommand('sources:'+projectId)
  const [importSource,setImportSource]=useState<string>(),[drafts,setDrafts]=useState<Record<string,SourceDraft>>({})
  const [lastSelected,setLastSelected]=useState('')
  const [recovery,setRecovery]=useState(()=>pendingImport(projectId))
  const query=readRoute().query
  const selectedSource=query.get('source_id'),selectedItem=query.get('request_id')
  const sources=state.data?.sources??[]
  const rows=sources.flatMap(source=>source.requests.map(request=>({source,request,annotation:state.data?.annotations.find(item=>item.source_id===source.source_id&&item.item_id===request.item_id)})))
  const visible=rows.filter(({source,request,annotation})=>(source.name+' '+request.method+' '+request.path+' '+(annotation?.label??request.label)).toLocaleLowerCase().includes(search.toLocaleLowerCase()))
  const selected=visible.find(item=>item.source.source_id===selectedSource&&item.request.item_id===selectedItem)??visible.find(item=>item.source.source_id+':'+item.request.item_id===lastSelected)??visible[0]
  const selectedKey=selected?selected.source.source_id+':'+selected.request.item_id:''
  const requestOpen=selected?.source.source_id===selectedSource&&selected?.request.item_id===selectedItem
  const openImport=(source?:string)=>{setImportSource(source);setImporting(true)}
  return <section className="jj-source-library" aria-label="接口来源工作面" data-page-pending={state.loading&&!state.data||business.loading&&!business.data||undefined}>
    <header className="jj-source-toolbar"><p><strong>{rows.length}</strong> 个请求 <span>来自 {sources.length} 份来源</span></p>{rows.length>0&&!recovery&&<Button kind="primary" onClick={()=>openImport()}>导入资料</Button>}</header>
    {recovery&&!importing&&<Notice tone="caution">有一份来源修订的保存结果需要核对。<Button onClick={()=>openImport()}>核对原保存</Button></Notice>}
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
              {items.map(({source,request,annotation})=><button type="button" className="jj-request-item jj-index-item" key={request.item_id} aria-label={'查看请求：'+(annotation?.label??request.label)} aria-current={selectedKey===source.source_id+':'+request.item_id?'true':undefined} onClick={()=>{setLastSelected(source.source_id+':'+request.item_id);go('/application?view=sources&source_id='+source.source_id+'&request_id='+request.item_id)}}>
                <span className="jj-request-item-line"><span className="jj-request-method">{request.method}</span><strong title={annotation?.label??request.label}>{annotation?.label??request.label}</strong></span>
                <code title={request.path}>{request.path}</code>
              </button>)}
            </section>}):<Empty title="没有匹配的请求" action={<Button onClick={()=>setSearch('')}>清除筛选</Button>}/>}
          </IndexSelection>
        </aside>
        {selected?<SourceRequestDetails key={selectedKey} projectId={projectId} {...selected} actions={actions} businessReady={Boolean(business.data)&&!business.error} draft={drafts[selectedKey]} onDraft={value=>setDrafts(current=>{const next={...current};if(value)next[selectedKey]=value;else delete next[selectedKey];return next})} onSaved={()=>state.reload()} onUpdate={()=>openImport(selected.source.source_id)} act={act} busy={busy}/>:<div className="jj-source-no-selection"><p>调整搜索条件，查看已有请求。</p></div>}
      </div>:<Empty title="从已有资料继续调查" action={!recovery&&<Button kind="primary" onClick={()=>openImport()}>导入接口资料或请求</Button>}>接受 OpenAPI 3.0/3.1、HAR 和 Postman Collection 2.1 JSON；可以随时补充和更新。</Empty>}
    {importing&&<SourceImport projectId={projectId} sources={sources} initialSource={importSource} onClose={()=>{setRecovery(pendingImport(projectId));setImporting(false)}} onAccepted={()=>{setRecovery(undefined);setImporting(false);state.reload()}}/>}
  </section>
}

function SourceImport({projectId,sources,initialSource,onClose,onAccepted}:{projectId:string;sources:ApiSource[];initialSource?:string;onClose:()=>void;onAccepted:()=>void}) {
  const [pending,setPending]=useState(()=>pendingImport(projectId))
  const [sourceId,setSourceId]=useState(pending?.sourceId??initialSource??''),[newId]=useState(()=>'src_'+operationId())
  const [kind,setKind]=useState<ApiSource['kind']>(sources.find(item=>item.source_id===initialSource)?.kind??'OPENAPI')
  const [name,setName]=useState(pending?.name??sources.find(item=>item.source_id===initialSource)?.name??''),[raw,setRaw]=useState('')
  const [preview,setPreview]=useState<ImportPreview|undefined>(pending?.preview),[file,setFile]=useState<File>()
  const {busy,error,run:act}=useCommand('source-import:'+projectId)
  return <Dialog closeDisabled={busy} title="导入接口资料" onClose={onClose} actions={dismiss=><><Button disabled={busy} onClick={dismiss}>取消</Button>{preview?<Button kind="primary" busy={busy} disabled={!name.trim()} onClick={()=>void act(async()=>{const input=pending??{sourceId:sourceId||newId,name:name.trim(),preview};if(pending){const actual=await api.sourceRevision(projectId,input.sourceId,input.preview.previous_revision+1);if(actual){if(actual.name!==input.name||JSON.stringify(actual.requests)!==JSON.stringify(input.preview.requests))throw new Error('此修订已有其他内容，请查看来源历史后处理。');savePending(pendingImportKey(projectId),undefined);setPending(undefined);onAccepted();return}}savePending(pendingImportKey(projectId),input);setPending(input);await api.accept(projectId,input.sourceId,input.name,input.preview);savePending(pendingImportKey(projectId),undefined);setPending(undefined);onAccepted()},'write')}>{pending?'核对原保存':'接受本次修订'}</Button>:<Button kind="primary" busy={busy} disabled={!raw} onClick={()=>void act(async()=>setPreview(await api.preview(projectId,raw,kind,sourceId||undefined)))}>预览并净化</Button>}</>}>
    <Field label="资料类型"><Choice disabled={Boolean(pending)||busy} value={kind} onValueChange={value=>{setKind(value as ApiSource['kind']);setPreview(undefined)}}><option value="OPENAPI">OpenAPI 3.0 / 3.1</option><option value="HAR">HAR 网络请求</option><option value="POSTMAN">Postman Collection 2.1</option></Choice></Field><Field label="保存到"><Choice disabled={Boolean(pending)||busy} value={sourceId} onValueChange={value=>{setSourceId(value);const item=sources.find(item=>item.source_id===value);if(item){setName(item.name);setKind(item.kind)}setPreview(undefined)}}><option value="">新的来源</option>{sources.map(item=><option key={item.source_id} value={item.source_id}>更新 {item.name}</option>)}</Choice></Field><Field label="来源名称"><input disabled={Boolean(pending)||busy} value={name} onChange={event=>setName(event.target.value)}/></Field><Field label="JSON 文件" hint="原始内容只用于本次解析，不写入来源资产。"><FilePicker label="JSON 文件" file={file} disabled={Boolean(pending)||busy} accept=".json,.har,application/json" formats="JSON / HAR" maxBytes={4194304} onFileChange={next=>act(async()=>{const content=next?await next.text():'';setRaw(content);setFile(next);setPreview(undefined);if(next&&!name)setName(next.name.slice(0,128))})}/></Field>
    {preview&&<section className="jj-source-preview"><h3>本次变化</h3><p>新增 {preview.added.length} · 改变 {preview.changed.length} · 来源中缺失 {preview.removed.length}</p><p className="jj-small">已有人工说明和业务关联会保留；缺失项不会删除已确认的业务要求。</p>{preview.warnings.map(warning=><Notice tone="caution" key={warning}>{warning}</Notice>)}<details><summary>查看 {preview.requests.length} 个请求定义</summary>{preview.requests.map(item=><p className="jj-small jj-mono" key={item.item_id}>{item.method} {item.path}</p>)}</details></section>}
    {Boolean(error)&&<ErrorNote error={error}/>}
  </Dialog>
}
