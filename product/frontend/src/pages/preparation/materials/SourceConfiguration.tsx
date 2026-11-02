import {useState} from 'react'
import {Choice} from '../../../shared/ui/Choice'
import {proofSourcesApi as api,type ProofContext,type ProofConfig} from '../../../entities/preparation/api/proofSources'
import {Dialog} from '../../../shared/ui/Dialog'
import {Button} from '../../../shared/ui/actions'
import {go,readRoute} from '../../../shared/lib/navigation'
import {useRead} from '../../../shared/lib/useRead'
import {projectsApi} from '../../../entities/application/api/projects'
import {Field} from '../../../shared/ui/layout'
import {ErrorNote,Empty,Loading} from '../../../shared/ui/feedback'

export function SourceConfiguration({projectId,context,actionId,initial,onClose,onSave}:{projectId:string;context:ProofContext;actionId?:string;initial?:ProofConfig;onClose:()=>void;onSave:(config:ProofConfig)=>Promise<unknown>}) {
    // 候选为空时补读本地运行事实，用于恢复引导；不把“未取得候选”推断为配置不存在。
    const runtime=useRead(context.sqlite?.length?null:'proof-runtime:'+projectId+':'+context.basis_id,()=>projectsApi.runtime(projectId))
    const recover=()=>{
        const route=readRoute()
        onClose()
        go('/application?runtime_method=managed&return_to='+encodeURIComponent(route.path+'?'+route.query),projectId)
    }
    const [action,setAction]=useState(initial?.action_id??actionId??(context.actions.length===1?context.actions[0].action_id:''))
    const [effect,setEffect]=useState(initial?.effect_id??''), [resource,setResource]=useState(initial?.resource_binding_id??'')
    const [database,setDatabase]=useState(()=>{
        const index=context.sqlite?.findIndex(item=>item.table===initial?.table&&item.database_path===initial?.database_path)??-1
        return index>=0?String(index):context.sqlite?.length===1?'0':''
    })
    const [column,setColumn]=useState(initial?.protected_column??'')
    const [tenantColumn,setTenantColumn]=useState(initial?.mappings.tenant?.[1]??'')
    const [stateColumn,setStateColumn]=useState(initial?.mappings.condition_state?.[1]??'')
    const [identityTenantPath,setIdentityTenantPath]=useState(initial?.identity_claims[0]?.tenant_path?.join('.')??'')
    const [busy,setBusy]=useState(false), [error,setError]=useState<unknown>()
    const chosen=context.actions.find(item=>item.action_id===action)
    const effects=chosen?.effects.filter(item=>['STATE_MUTATION','OBJECT_CREATION'].includes(item.kind))??[]
    const effectId=effects.find(item=>item.effect_id===effect)?.effect_id??(effects.length===1?effects[0].effect_id:'')
    const resources=context.resources.filter(item=>item.action_id===action&&!item.case_specific)
    const selectedResource=resources.find(item=>item.resource_binding_id===resource)??(resources.length===1?resources[0]:undefined)
    const table=database===''?undefined:context.sqlite?.[Number(database)]
    const field=table?.fields.includes(column)?column:table?.fields.length===1?table.fields[0]:''
    const conditions=chosen?.condition_requirements
    const ready=Boolean(chosen&&effectId&&selectedResource&&table&&field
        &&(!conditions?.tenant||(table.fields.includes(tenantColumn)&&identityTenantPath.trim()))
        &&(!conditions?.resource_state||table.fields.includes(stateColumn)))
    const result=effects.find(item=>item.effect_id===effectId)
    return <Dialog title="设置结果判断依据" onClose={onClose} actions={dismiss=><><Button disabled={busy} onClick={dismiss}>取消</Button>{Boolean(context.sqlite?.length)&&<Button kind="primary" busy={busy} disabled={!ready} onClick={async()=>{
        setBusy(true)
        try{
            const config=await api.sqliteCandidate(projectId,{basis_id:context.basis_id,action_id:action,effect_id:effectId,resource_binding_id:selectedResource!.resource_binding_id,database_path:table!.database_path,table:table!.table,protected_column:field,
                ...(conditions?.tenant?{tenant_column:tenantColumn,identity_tenant_path:identityTenantPath.trim()}:{}),
                ...(conditions?.resource_state?{condition_state_column:stateColumn}:{})})
            if(await onSave(config))dismiss()
        }catch(e){setError(e)}finally{setBusy(false)}
    }}>保存判断方式</Button>}</>}>
        <div className="jj-source-configuration">
            <section className="jj-source-target">
                <dl className="jj-facts is-stacked"><div><dt>业务操作</dt><dd>{chosen?.label??'尚未选择'}</dd></div><div><dt>判断结果</dt><dd>{result?.label??'尚未选择'}</dd></div>{selectedResource&&<div><dt>测试数据</dt><dd>{selectedResource.resource_id}，属于{context.identities.find(identity=>identity.identity_id===selectedResource.owner_identity_id)?.label}</dd></div>}</dl>
                {((!actionId&&!initial&&context.actions.length>1)||effects.length>1||resources.length>1)&&<div className="jj-form-grid">
                    {!actionId&&!initial&&context.actions.length>1&&<Field label="业务操作"><Choice value={action} onValueChange={value=>{setAction(value);setEffect('');setResource('')}}>{context.actions.map(item=><option key={item.action_id} value={item.action_id}>{item.label}</option>)}</Choice></Field>}
                    {effects.length>1&&<Field label="需要核对的结果"><Choice value={effectId} onValueChange={setEffect}>{effects.map(item=><option key={item.effect_id} value={item.effect_id}>{item.label}</option>)}</Choice></Field>}
                    {resources.length>1&&<Field label="测试资源"><Choice value={selectedResource?.resource_binding_id??''} onValueChange={setResource}>{resources.map(item=><option key={item.resource_binding_id} value={item.resource_binding_id}>{item.resource_id} / {context.identities.find(identity=>identity.identity_id===item.owner_identity_id)?.label}</option>)}</Choice></Field>}
                </div>}
            </section>
            {context.sqlite?.length?<section className="jj-source-mapping"><h3>用哪项业务数据判断</h3>
                <div className="jj-form-grid">{context.sqlite.length>1?<Field label="数据表"><Choice value={database} onValueChange={value=>{setDatabase(value);setColumn('')}}>{context.sqlite.map((item,index)=><option key={index} value={index}>{item.database_path} / {item.table}</option>)}</Choice></Field>:<dl className="jj-facts is-stacked"><div><dt>业务记录</dt><dd>{table?.database_path} / {table?.table}</dd></div></dl>}
                <Field label="需要核对的业务字段"><Choice value={field} placeholder="选择实际结果对应的字段" disabled={!table} onValueChange={setColumn}>{table?.fields.map(name=><option key={name}>{name}</option>)}</Choice></Field></div>
                {(conditions?.tenant||conditions?.resource_state)&&<section className="jj-condition-source"><h3>核对规则的适用条件</h3><div className="jj-form-grid">
                    {conditions.tenant&&<><Field label="资源所属租户"><Choice value={tenantColumn} placeholder="选择租户字段" disabled={!table} onValueChange={setTenantColumn}>{table?.fields.map(name=><option key={name}>{name}</option>)}</Choice></Field>
                    <Field label="账号身份中的租户字段"><input value={identityTenantPath} placeholder="例如 tenant_id" onChange={event=>setIdentityTenantPath(event.target.value)}/></Field></>}
                    {conditions.resource_state&&<Field label="资源的当前状态"><Choice value={stateColumn} placeholder="选择状态字段" disabled={!table} onValueChange={setStateColumn}>{table?.fields.map(name=><option key={name}>{name}</option>)}</Choice></Field>}
                </div></section>}
                {table&&<details><summary>查看编号与归属对应</summary><dl className="jj-facts is-stacked"><div><dt>资源编号</dt><dd>{table.resource_column}</dd></div><div><dt>资源所有者</dt><dd>{table.owner_column}</dd></div></dl></details>}
            </section>:runtime.error?<ErrorNote error={runtime.error} onRetry={runtime.reload}/>:!runtime.data?<Loading>正在读取已有运行设置</Loading>:<Empty title={
                !runtime.data.running?(runtime.data.configuration?.sqlite?.length?'先启动已配置的测试应用':'先准备应用的测试数据库'):
                !runtime.data.source_matches?'当前运行与源码尚未对应':
                !context.runtime_available?'先核对应用的运行记录':
                runtime.data.configuration?.sqlite?.length?'当前运行尚未提供可读取的数据库':'当前运行未配置测试数据库'
            } action={<Button kind="primary" onClick={recover}>核对应用运行</Button>}>
                {runtime.data.configuration?.sqlite?.length?'已有数据库设置保留。核对应用运行后，返回这里选择业务字段。':'在应用连接中设置测试数据库，再返回这里选择业务字段。'}
            </Empty>}
            {Boolean(context.sqlite?.length)&&<p className="jj-small jj-muted">下一步核对允许读取的内容，再检查能否取得判断依据。</p>}
            {Boolean(error)&&<ErrorNote error={error}/>}
        </div>
    </Dialog>
}

