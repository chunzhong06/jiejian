import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import EditOutlined from '@ant-design/icons/EditOutlined'
import type {ApiSource,SourceRequest,SourceAnnotation} from '../../entities/application/api/workbench'
import {workbenchApi as api} from '../../entities/application/api/workbench'
import {projectsApi} from '../../entities/application/api/projects'
import type {BusinessActionRevisionDto} from '../../entities/permission/api/businessBoundaries'
import {go} from '../../shared/lib/navigation'
import {Button} from '../../shared/ui/actions'
import {Field} from '../../shared/ui/layout'
import {Choice} from '../../shared/ui/Choice'
import {Badge} from '../../shared/ui/feedback'

// 草稿保留开始编辑时的修订；切换请求后仍按原修订提交。
export type SourceDraft={label:string;action:string;revision:number}
const locations={PATH:'路径',QUERY:'查询参数',HEADER:'请求头',BODY:'请求正文'}

export function SourceRequestDetails({projectId,source,request,annotation,actions,businessReady,draft,onDraft,onSaved,onUpdate,act,busy}:{
  projectId:string;source:ApiSource;request:SourceRequest;annotation?:SourceAnnotation;draft?:SourceDraft;
  actions:BusinessActionRevisionDto[];businessReady:boolean;
  onDraft:(value:SourceDraft|undefined)=>void;onSaved:()=>void;onUpdate:()=>void;
  act:(task:()=>Promise<void>)=>Promise<void>;busy:boolean;
}) {
  const linked=actions.find(item=>item.action_id===annotation?.action_id)
  const edit=()=>onDraft({label:annotation?.label??request.label,action:annotation?.action_id??'',revision:annotation?.revision??0})
  const propose=()=>void act(async()=>{
    const current=await projectsApi.understanding(projectId)
    await api.candidate(projectId,source.source_id,request.item_id,current.revision)
    go('/application?view=business')
  })
  return <section className="jj-request-detail" aria-label="请求详情">
    <Button className="jj-source-back" kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={()=>go('/application?view=sources')}>返回请求列表</Button>
    <header className="jj-request-header">
      <h2>{annotation?.label??request.label}</h2>
      <div className="jj-request-endpoint"><span className="jj-request-method">{request.method}</span><code>{request.path}</code></div>
    </header>
    <section className="jj-request-purpose">
      <div className="jj-request-purpose-heading"><h3>业务关联</h3><Badge tone="neutral">{!businessReady?'关联待核对':linked?'已关联':annotation?.action_id?'需重新关联':'未关联'}</Badge></div>
      {draft?<form className="jj-source-link-editor" onSubmit={event=>{event.preventDefault();void act(async()=>{
        await api.annotate(projectId,source.source_id,request.item_id,draft.label,draft.action||null,draft.revision)
        onDraft(undefined);onSaved()
      })}}>
        <Field label="请求名称"><input maxLength={256} value={draft.label} disabled={busy} onChange={event=>onDraft({...draft,label:event.target.value})}/></Field>
        {(actions.length>0||draft.action)&&<Field label="对应业务动作"><Choice disabled={busy} value={draft.action} onValueChange={action=>onDraft({...draft,action})}><option value="">尚未关联</option>{actions.map(item=><option key={item.action_id} value={item.action_id}>{item.display_name}</option>)}</Choice></Field>}
        <div className="jj-confirmation-actions"><Button kind="quiet" disabled={busy} onClick={()=>onDraft(undefined)}>取消修改</Button><Button kind="primary" type="submit" busy={busy} disabled={!draft.label.trim()}>{actions.length||draft.action?'保存业务关联':'保存请求名称'}</Button></div>
      </form>:<>
        <p className="jj-request-business-name">{linked?.display_name??(annotation?.action_id?'原业务动作已变化':actions.length?'选择对应的业务动作':'这条请求代表什么业务操作？')}</p>
        <p className="jj-small jj-muted">{linked?'整理为测试场景后，可沿用该动作已确认的权限要求。':actions.length?'将请求对应到业务动作，继续配置测试场景。':'先整理业务含义，再确认权限要求和测试场景。'}</p>
        <div className="jj-request-purpose-actions">
          {(linked||!actions.length)&&<Button kind="quiet" icon={<EditOutlined aria-hidden="true"/>} disabled={busy||!businessReady} onClick={edit}>{linked?'修改关联':'修改名称'}</Button>}
          {linked?<Button kind="primary" onClick={()=>go('/testing?action_id='+linked.action_id+'&source_id='+source.source_id+'&request_id='+request.item_id)}>整理测试场景</Button>:actions.length?<Button kind="primary" disabled={busy||!businessReady} onClick={edit}>关联业务动作</Button>:<Button kind="primary" busy={busy} disabled={!businessReady} onClick={propose}>整理业务动作</Button>}
        </div>
        {!linked&&actions.length>0&&<Button kind="quiet" className="jj-source-new-action" busy={busy} onClick={propose}>新增业务动作线索</Button>}
      </>}
    </section>
    <section className="jj-request-parameters"><div className="jj-request-section-heading"><h3>参数</h3><span>{request.parameters.length} 项</span></div>
      {request.parameters.length?<div className="jj-request-table-wrap"><table><thead><tr><th scope="col">名称</th><th scope="col">位置</th><th scope="col">要求</th></tr></thead><tbody>{request.parameters.map(item=><tr key={item.location+item.name}><td><code>{item.name}</code></td><td>{locations[item.location]}</td><td>{item.required?'必填':'可选'}{item.sensitive&&<small>运行时提供受控值</small>}</td></tr>)}</tbody></table></div>:<p className="jj-small jj-muted">来源未声明参数；实际输入可在测试场景中补充。</p>}
    </section>
    <details className="jj-request-origin"><summary>来源信息</summary><dl><div><dt>资料</dt><dd>{source.name}</dd></div><div><dt>修订</dt><dd>{source.revision}</dd></div><div><dt>格式</dt><dd>{source.kind==='OPENAPI'?'OpenAPI':source.kind==='POSTMAN'?'Postman Collection':'HAR'}</dd></div><div><dt>原始位置</dt><dd><code>{request.pointer}</code></dd></div></dl>
      {source.warnings.map(warning=><p className="jj-small" key={warning}>{warning}</p>)}
      <Button kind="quiet" onClick={onUpdate}>更新来源并查看差异</Button>
    </details>
  </section>
}
