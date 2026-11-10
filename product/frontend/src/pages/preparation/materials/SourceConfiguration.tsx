import {useWorkflow} from '../../../shared/lib/workflow'
import {editorDraft,rememberEditorDraft,editorDraftGeneration,clearSubmittedDraft,useDraftProtection,requestCollaboration,useHandoffContext} from '../../../entities/runtime/model/handoff'
import {useEffect,useRef,useState} from 'react'
import {Choice} from '../../../shared/ui/Choice'
import {proofSourcesApi as api,type ProofContext,type ProofConfig,type RelationshipSourceMapping} from '../../../entities/preparation/api/proofSources'
import {RelationshipMapping,emptyRelationshipMapping,relationshipMappingReady} from '../../../entities/preparation/ui/RelationshipMapping'
import {AsyncExportFields,emptyAsyncExport,asyncExportReady} from '../../../entities/preparation/ui/AsyncExportFields'
import type {AsyncExportMapping} from '../../../entities/preparation/api/proofSources'
import {TaskSurface} from '../../../shared/ui/TaskSurface'
import {Button} from '../../../shared/ui/actions'
import {go,readRoute,withReturnDestination} from '../../../shared/lib/navigation'
import {useRead} from '../../../shared/lib/useRead'
import {projectsApi} from '../../../entities/application/api/projects'
import {Field} from '../../../shared/ui/layout'
import {ErrorNote,Empty,Loading} from '../../../shared/ui/feedback'

export function SourceConfiguration({projectId,context,actionId,requestedEffect,initial,sourceId,onClose,onSave}:{projectId:string;context:ProofContext;actionId?:string;requestedEffect?:string|null;initial?:ProofConfig;sourceId?:string;onClose:()=>void;onSave:(config:ProofConfig)=>Promise<unknown>}) {
    const workflow=useWorkflow();
    const tables=[...(context.sqlite??[]).map(item=>({...item,connection_id:undefined as string|undefined})),...(context.databases??[]).map(item=>({...item,database_path:(item.engine==='POSTGRESQL'?'PostgreSQL':'MySQL')+' · '+item.database,connection_id:item.connection_id}))]
    const draftKey='proof:'+projectId+':'+(sourceId??(actionId? actionId+(requestedEffect?':'+requestedEffect:''):'new'))
    const [restored]=useState(()=>editorDraft<{action:string;effect:string;resource:string;database:string;column:string;tenantColumn:string;stateColumn:string;identityTenantPath:string;relationshipMapping?:RelationshipSourceMapping;collection?:string;deferred?:boolean;exportMapping?:AsyncExportMapping;basis:string}>(draftKey,projectId))
    // 候选为空时补读本地运行事实，用于恢复引导；不把“未取得候选”推断为配置不存在。
    const recover=()=>{
        const route=workflow?.route??readRoute()
        const query=new URLSearchParams(route.query)
        query.set('configure',initial?'edit':'new')
        if(action)query.set('action_id',action)
        if(sourceId)query.set('source_id',sourceId)
        onClose();
        (workflow?.open??go)(withReturnDestination('/application?view=source&runtime_method=managed',route.path+'?'+query),projectId)
    }
    const [action,setAction]=useState(restored?.action??initial?.action_id??actionId??(context.actions.length===1?context.actions[0].action_id:''))
    const [effect,setEffect]=useState(restored?.effect??initial?.effect_id??requestedEffect??''), [resource,setResource]=useState(restored?.resource??initial?.resource_binding_id??'')
    const [database,setDatabase]=useState(()=>{
        const index=tables.findIndex(item=>initial?.database_capture?item.connection_id===initial.database_capture.connection_id:item.table===initial?.table&&item.database_path===initial?.database_path)
        if(restored?.basis===context.basis_id)return restored.database
        return index>=0?String(index):tables.length===1?'0':''
    })
    const [column,setColumn]=useState(restored?.column??initial?.protected_column??'')
    const [tenantColumn,setTenantColumn]=useState(restored?.tenantColumn??initial?.mappings.tenant?.[1]??'')
    const [stateColumn,setStateColumn]=useState(restored?.stateColumn??initial?.mappings.condition_state?.[1]??'')
    const [identityTenantPath,setIdentityTenantPath]=useState(restored?.identityTenantPath??initial?.identity_claims[0]?.tenant_path?.join('.')??'')
    const [relationshipMapping,setRelationshipMapping]=useState<RelationshipSourceMapping>(restored?.relationshipMapping??initial?.relationship_mapping??emptyRelationshipMapping)
    const [collection,setCollection]=useState(restored?.collection??initial?.collection??''),[deferred,setDeferred]=useState(restored?.deferred??Boolean(initial?.async_export)),[exportMapping,setExportMapping]=useState<AsyncExportMapping>(restored?.exportMapping??initial?.async_export??emptyAsyncExport())
    const [busy,setBusy]=useState(false), [error,setError]=useState<unknown>()
    const chosen=context.actions.find(item=>item.action_id===action)
    const effects=chosen?.effects.filter(item=>['STATE_MUTATION','OBJECT_CREATION','FILE_CONTENT_DELIVERY'].includes(item.kind))??[]
    const effectId=effects.find(item=>item.effect_id===effect)?.effect_id??(effects.length===1?effects[0].effect_id:'')
    const resources=context.resources.filter(item=>item.action_id===action&&!item.case_specific)
    const selectedResource=resources.find(item=>item.resource_binding_id===resource)??(resources.length===1?resources[0]:undefined)
    const table=database===''?undefined:tables[Number(database)]
    const field=table?.fields.includes(column)?column:table?.fields.length===1?table.fields[0]:''
    const completed=useRef(false)
    const alive=useRef(true);useEffect(()=>{alive.current=true;return()=>{alive.current=false}},[])
    const initialValues=useRef(JSON.stringify({action,effect,resource,database,column,tenantColumn,stateColumn,identityTenantPath,relationshipMapping,collection,deferred,exportMapping})).current
    useDraftProtection(initialValues!==JSON.stringify({action,effect,resource,database,column,tenantColumn,stateColumn,identityTenantPath,relationshipMapping,collection,deferred,exportMapping}))
    useEffect(()=>{if(!completed.current)rememberEditorDraft(draftKey,{action,effect,resource,database,column,tenantColumn,stateColumn,identityTenantPath,relationshipMapping,collection,deferred,exportMapping,basis:context.basis_id},projectId)},[draftKey,projectId,action,effect,resource,database,column,tenantColumn,stateColumn,identityTenantPath,relationshipMapping,collection,deferred,exportMapping,context.basis_id])
    const resume='/preparation?proof_sources=1&configure='+(initial?'edit':'new')+'&action_id='+action+(sourceId?'&source_id='+sourceId:'')+(effectId?'&effect_id='+effectId:'');
    useHandoffContext({projectId,label:(chosen?.label??'当前操作')+' · 结果判断草稿',references:{...workflow?.references,action_id:action,return_to:workflow?.resume?.(resume)??resume},editor:{kind:'PROOF',basis_id:context.basis_id,action_id:action,effect_id:effectId,resource_binding_id:selectedResource?.resource_binding_id??null,table:table?.table??null,connection_id:table?.connection_id??null,collection:collection||null,...(deferred&&asyncExportReady(exportMapping)?{async_export:exportMapping}:{}),protected_column:field||null,tenant_column:tenantColumn||null,state_column:stateColumn||null,relationship_mapping:relationshipMapping.application_action?relationshipMapping:null}})
    const conditions=chosen?.condition_requirements
    const relationships=conditions?.relationships??[]
    const fileEffect=effects.find(item=>item.effect_id===effectId)?.kind==='FILE_CONTENT_DELIVERY'
    const runtime=useRead(tables.length||fileEffect?null:'proof-runtime:'+projectId+':'+context.basis_id,()=>projectsApi.runtime(projectId))
    const ready=fileEffect?Boolean(chosen&&selectedResource&&/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(collection)&&(!deferred||asyncExportReady(exportMapping))):Boolean(chosen&&effectId&&selectedResource&&table&&field&&(!table.connection_id||effects.find(item=>item.effect_id===effectId)?.kind==='STATE_MUTATION')&&relationshipMappingReady(relationships,relationshipMapping,table.fields)
        &&(!conditions?.tenant||(table.fields.includes(tenantColumn)&&identityTenantPath.trim()))
        &&(!conditions?.resource_state||table.fields.includes(stateColumn)))
    const result=effects.find(item=>item.effect_id===effectId)
    return <TaskSurface title="设置结果判断依据" onBack={onClose} backLabel="返回结果证明" actions={dismiss=><><Button disabled={busy} onClick={()=>requestCollaboration(projectId,'SETUP','请沿用当前结果判断草稿和已声明的数据来源，补齐对应关系并保存候选；不明确的业务字段请向我确认，读取与采用仍由我审阅。')}>请 Agent 补全</Button><Button disabled={busy} onClick={dismiss}>取消</Button>{(fileEffect||Boolean(tables.length))&&<Button kind="primary" busy={busy} disabled={!ready} onClick={async()=>{
        setBusy(true)
        const submitted=editorDraftGeneration(draftKey,projectId)
        try{
            const config=fileEffect?await api.fileCandidate(projectId,{basis_id:context.basis_id,action_id:action,effect_id:effectId,resource_binding_id:selectedResource!.resource_binding_id,collection,async_export:deferred?exportMapping:null}):await (table!.connection_id?api.databaseCandidate:api.sqliteCandidate)(projectId,{basis_id:context.basis_id,action_id:action,effect_id:effectId,resource_binding_id:selectedResource!.resource_binding_id,...(table!.connection_id?{connection_id:table!.connection_id}:{database_path:table!.database_path,table:table!.table}),protected_column:field,
                ...(conditions?.tenant?{tenant_column:tenantColumn,identity_tenant_path:identityTenantPath.trim()}:{}),
                ...(conditions?.resource_state?{condition_state_column:stateColumn}:{}),
                ...(relationships.length?{relationship_mapping:relationshipMapping}:{})})
            const saved=fileEffect&&initial?.reference_artifact&&initial.resource_binding_id===selectedResource?.resource_binding_id?{...config,reference_artifact:initial.reference_artifact,reference_origin:initial.reference_origin}:config
            if(await onSave(saved)){completed.current=true;clearSubmittedDraft(draftKey,projectId,submitted);if(alive.current)dismiss()}
        }catch(e){setError(e)}finally{setBusy(false)}
    }}>保存判断方式</Button>}</>}>
        <div className="jj-source-configuration">
            <section className="jj-source-target">
                <dl className="jj-facts is-stacked" data-layout="columns"><div><dt>业务操作</dt><dd>{chosen?.label??'尚未选择'}</dd></div><div><dt>判断结果</dt><dd>{result?.label??'尚未选择'}</dd></div>{selectedResource&&<div><dt>测试数据</dt><dd>{selectedResource.resource_id}，属于{context.identities.find(identity=>identity.identity_id===selectedResource.owner_identity_id)?.label}</dd></div>}</dl>
                {((!actionId&&!initial&&context.actions.length>1)||effects.length>1||resources.length>1)&&<div className="jj-form-grid">
                    {!actionId&&!initial&&context.actions.length>1&&<Field label="业务操作"><Choice value={action} onValueChange={value=>{setAction(value);setEffect('');setResource('')}}>{context.actions.map(item=><option key={item.action_id} value={item.action_id}>{item.label}</option>)}</Choice></Field>}
                    {effects.length>1&&<Field label="需要核对的结果"><Choice value={effectId} onValueChange={setEffect}>{effects.map(item=><option key={item.effect_id} value={item.effect_id}>{item.label}</option>)}</Choice></Field>}
                    {resources.length>1&&<Field label="测试资源"><Choice value={selectedResource?.resource_binding_id??''} onValueChange={setResource}>{resources.map(item=><option key={item.resource_binding_id} value={item.resource_binding_id}>{item.resource_id} / {context.identities.find(identity=>identity.identity_id===item.owner_identity_id)?.label}</option>)}</Choice></Field>}
                </div>}
            </section>
            {fileEffect?<section className="jj-source-mapping"><h3>如何判断文件是否完整交付</h3><p className="jj-small jj-muted">将实际收到的文件与同一测试资源的完整参照比对。下面的集合用于对应文件所属的资源。</p><div className="jj-form-grid"><Field label="资源所属记录集合" hint="使用当前应用中保存资源编号和所有者的集合，不是文件名。"><input value={collection} placeholder="填写应用已使用的记录集合名称" onChange={event=>setCollection(event.target.value)}/></Field><Field label="交付方式"><Choice value={deferred?'async':'direct'} onValueChange={value=>setDeferred(value==='async')}><option value="direct">本次操作直接返回文件</option><option value="async">先创建导出任务，再接收文件</option></Choice></Field></div>{deferred&&<AsyncExportFields value={exportMapping} onChange={setExportMapping} disabled={busy}/>}<p className="jj-small jj-muted">保存后准备所属资源的完整参照，再审阅读取范围。任务状态与实际文件分别核对。</p></section>:tables.length?<section className="jj-source-mapping"><h3>用哪项业务数据判断</h3>
                <div className="jj-form-grid">{tables.length>1?<Field label="数据表"><Choice value={database} onValueChange={value=>{setDatabase(value);setColumn('')}}>{tables.map((item,index)=><option key={index} value={index}>{item.database_path} / {item.table}</option>)}</Choice></Field>:<dl className="jj-facts is-stacked" data-layout="columns"><div><dt>业务记录</dt><dd>{table?.database_path} / {table?.table}</dd></div></dl>}
                <Field label="需要核对的业务字段"><Choice value={field} placeholder="选择实际结果对应的字段" disabled={!table} onValueChange={setColumn}>{table?.fields.map(name=><option key={name}>{name}</option>)}</Choice></Field></div>
                {(conditions?.tenant||conditions?.resource_state)&&<section className="jj-condition-source"><h3>核对规则的适用条件</h3><div className="jj-form-grid">
                    {conditions.tenant&&<><Field label="资源所属租户"><Choice value={tenantColumn} placeholder="选择租户字段" disabled={!table} onValueChange={setTenantColumn}>{table?.fields.map(name=><option key={name}>{name}</option>)}</Choice></Field>
                    <Field label="账号身份中的租户字段"><input value={identityTenantPath} placeholder="例如 tenant_id" onChange={event=>setIdentityTenantPath(event.target.value)}/></Field></>}
                    {conditions.resource_state&&<Field label="资源的当前状态"><Choice value={stateColumn} placeholder="选择状态字段" disabled={!table} onValueChange={setStateColumn}>{table?.fields.map(name=><option key={name}>{name}</option>)}</Choice></Field>}
                </div></section>}
                {relationships.length>0&&table&&<RelationshipMapping requirements={relationships} value={relationshipMapping} fields={table.fields} onChange={setRelationshipMapping}/>}
                {table&&<details><summary>查看编号与归属对应</summary><dl className="jj-facts is-stacked" data-layout="columns"><div><dt>资源编号</dt><dd>{table.resource_column}</dd></div><div><dt>资源所有者</dt><dd>{table.owner_column}</dd></div></dl></details>}
            </section>:runtime.error?<ErrorNote error={runtime.error}/>:!runtime.data?<Loading>正在读取已有运行设置</Loading>:<Empty title={
                !runtime.data.running?((runtime.data.configuration?.sqlite?.length||runtime.data.configuration?.databases?.length)?'先启动已配置的测试应用':'先准备应用的测试数据库'):
                !runtime.data.source_matches?'当前运行与源码尚未对应':
                !context.runtime_available?'先核对应用的运行记录':
                (runtime.data.configuration?.sqlite?.length||runtime.data.configuration?.databases?.length)?'当前运行尚未提供可读取的数据库':'当前运行未配置测试数据库'
            } action={<Button kind="primary" onClick={recover}>核对应用运行</Button>}>
                {(runtime.data.configuration?.sqlite?.length||runtime.data.configuration?.databases?.length)?'已有数据库设置保留。核对应用运行后，返回这里选择业务字段。':'在应用连接中设置测试数据库，再返回这里选择业务字段。'}
            </Empty>}
            {Boolean(tables.length)&&<p className="jj-small jj-muted">下一步核对允许读取的内容{table?.connection_id?'、审阅审计组件安装，再核验实际记录。':'，再检查能否取得判断依据。'}</p>}
            {Boolean(error)&&<ErrorNote error={error}/>}
        </div>
    </TaskSurface>
}

