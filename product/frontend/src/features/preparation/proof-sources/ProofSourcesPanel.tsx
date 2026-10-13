// 证明准备围绕当前候选组织：由开发客户端中的 Agent 协助配置，GUI只突出读取范围、缺口和采用决定。
import { LoadingState } from '../../../shared/ui/LoadingState'
import { Alert, Button, Checkbox, Input, Modal } from 'antd'
import { useCallback, useState, type ReactNode } from 'react'
import {proofSourcesApi,type ProofSource,type AdoptionPreview,type ProofReceipt} from '../../../api/preparation/proofSources'
import {AgentAssistEntry} from '../../../shared/ui/AgentAssistEntry'
import {ProofBatchPreparation} from './ProofBatchPreparation'
import {ReferenceFilePreparation} from './ReferenceFilePreparation'
import { useProofSources } from './useProofSources'
import { EditorialHeader, EditorialPage } from '../../../shared/ui/Editorial'
import { StatusBadge } from '../../../shared/ui/StatusBadge'
import { TaskActionBar } from '../../../shared/ui/TaskActionBar'
import { useTaskGuard } from '../../../shared/runtime/editGuard'
import '../../../shared/styles/proof-details.css'
import './proof-material-list.css'

const keyLabels: Record<string,string> = {resource_id:'资源标识',owner_id:'资源所有者',state:'业务状态',version:'资源版本',effect_count:'结果发生次数',history_generation:'历史代次',operation_id:'操作标识',operation_resource_id:'操作对应资源',operation_subject_id:'实际操作人',operation_before_version:'操作前版本',operation_after_version:'操作后版本',operation_state:'操作完成状态',unfinished_effects:'未完成后果',title:'资料标题',summary:'资料摘要',body:'完整内容'}
const reasonLabels: Record<string,string> = {CREATION_COLLECTION_VERIFIED:'新对象的独立记录可读取',CREATION_COLLECTION_UNKNOWN:'尚未找到实际业务记录集合',CREATION_COLLECTION_LIMIT:'集合超过本次完整读取上限',CREATION_SOURCE_UNAVAILABLE:'创建证明尚未对应独立记录组件',SOURCE_REQUIRES_MIGRATION:'旧来源需要按通用方式重新准备',PROTECTED_FIELD_READABLE:'受保护字段已读到',RECORD_PROVIDER_UNAVAILABLE:'记录组件或运行对应暂时不可用',RECORD_SOURCE_UNAVAILABLE:'记录来源暂时无法读取',MAPPING_READABLE:'字段已读到',RESOURCE_OWNER_MATCH:'资源与所有者一致',SOURCE_CONTRACT_VERIFIED:'业务记录格式可用于检查',OPERATION_RECORD_COMPLETE:'当前操作记录完整',ACTUAL_IDENTITY_MATCH:'实际账号与角色一致',ACTUAL_IDENTITY_MISMATCH:'实际账号或角色不一致',CONTRACT_UNVERIFIED:'尚无可核对的业务记录合同',MAPPING_MISSING:'没有读到该字段',MAPPING_TYPE_INVALID:'字段类型与要求不同',MAPPING_REQUIRED:'缺少必要字段映射',SOURCE_READ_DENIED:'当前账号不能读取来源',SOURCE_READ_UNAVAILABLE:'来源暂时无法读取',IDENTITY_SESSION_MISSING:'账号需要重新登录',READ_AUTHORITY_UNAVAILABLE:'读取授权或运行实例已失效',RESOURCE_OWNER_MISMATCH:'资源或所有者不一致',COMPLETION_UNCONFIRMED:'操作完成情况尚未核对',JSON_DUPLICATE_KEY:'响应包含重复字段',JSON_INVALID:'响应不是有效对象',JSON_NONFINITE:'响应包含无效数值',JSON_STRUCTURE_LIMIT:'响应结构超出读取范围',RESPONSE_TOO_LARGE:'响应超出读取大小限制'}
const preflightUsable = (source?: ProofSource) => Boolean(source?.preflight?.state === 'SUCCEEDED' && source.preflight.report?.assessment === 'USABLE' && source.preflight.current_basis)
const identityFailed = (source?:ProofSource) => Boolean(source?.preflight?.current_basis && source.preflight.report?.checks.some(item=>['ACTUAL_IDENTITY_MISMATCH','IDENTITY_SESSION_MISSING'].includes(item.code)&&item.status!=='CONFIRMED'))
const sourceLabel = (source: ProofSource) => ['RUNNING','PENDING','RETRY_WAIT'].includes(source.preflight?.state??'') ? '正在核对' : identityFailed(source) ? '需要核对登录账号' : source.config.source_kind === 'JSON_HTTP_RESOURCE' ? '需要重新准备' : source.adopted ? preflightUsable(source) ? '已准备' : '需要复核' : preflightUsable(source) ? '待确认使用' : '待准备'

export function ProofSourcesPanel({projectId,requestedSource,onBack,onChanged,onNavigate,embedded=false,actionId,providedMaterials=false,providedPreparation}: {
  projectId: string; requestedSource?: string | null; onBack: () => void; onChanged: () => Promise<unknown>; onNavigate?: (path: string) => void
  embedded?:boolean;actionId?:string;providedMaterials?:boolean;providedPreparation?:(refresh:()=>Promise<unknown>)=>ReactNode
}) {
  const [selected,setSelected] = useState(requestedSource ?? '')
  const [collapsed,setCollapsed] = useState(false)
  const [editing,setEditing] = useState(false), [draft,setDraft] = useState(''), [dialog,setDialog] = useState<'scope'|'adopt'>(), [confirmed,setConfirmed] = useState(false)
  const [adoption,setAdoption] = useState<AdoptionPreview>()
  const [referenceAsset,setReferenceAsset]=useState<string>(),[captureId,setCaptureId]=useState<string>()
  const onReset = useCallback(() => { setSelected(requestedSource ?? ''); setCollapsed(false); setEditing(false); setDialog(undefined);setReferenceAsset(undefined);setCaptureId(undefined) },[requestedSource,actionId])
  const onAccepted = useCallback((receipt: ProofReceipt) => {
    setEditing(false); setDialog(undefined)
    if (receipt.result.source_id) setSelected(previous => !previous || previous === '__new__' ? receipt.result.source_id! : previous)
    if(receipt.result.asset_id)setReferenceAsset(receipt.result.asset_id)
    if(receipt.result.capture_id)setCaptureId(receipt.result.capture_id)
  },[])
  const {context,loading,busy,issue,notice,pending,load,write,recover,readAdoption,setIssue} = useProofSources({projectId,requestedSource,onChanged,onReset,onAccepted})
  useTaskGuard(editing)
  const sources=context?.sources.filter(item=>!actionId||item.config.action_id===actionId)??[]
  const missingEffects=context?.actions.filter(item=>!actionId||item.action_id===actionId).flatMap(item=>item.effects
    .filter(effect=>!sources.some(source=>source.config.action_id===item.action_id&&source.config.effect_id===effect.effect_id))
    .map(effect=>({...effect,actionId:item.action_id})))??[]
  const source=sources.find(item=>item.source_id===selected)??(!selected?sources[0]:undefined)
  const createdSource=source?.config.source_kind==='CREATED_OBJECT_RECORDS'
  const running=['PENDING','RUNNING','RETRY_WAIT'].includes(source?.preflight?.state??'')
  const needsReference=source?.config.source_kind==='REFERENCE_FILE'&&!source.config.reference_artifact
  const action = context?.actions.find(item => item.action_id === (source?.config.action_id ?? actionId))
  const effect = action?.effects.find(item => item.effect_id === source?.config.effect_id)
  const savedScope = context?.read_scopes.find(item => source && (!context.runtime_origin || item.origin === context.runtime_origin)
    && (!source.config.read_scope_id || source.config.read_scope_id === item.scope_id)
    && item.path_templates.includes(source.config.relative_path_template)
    && (source.config.source_kind!=='CREATED_OBJECT_RECORDS'||item.path_templates.includes(`/collections/${source.config.collection}`))
    && source.config.identity_claims.every(claim => Boolean(claim.request_path && item.path_templates.includes(claim.request_path)))
    && item.resource_binding_ids.includes(source.config.resource_binding_id)
    && source.config.identity_claims.every(claim => item.identity_ids.includes(claim.identity_id))
    && item.max_response_bytes >= source.config.max_response_bytes && item.timeout_us >= source.config.timeout_us)
  const scope = context?.runtime_available && source?.read_scope_confirmed !== false ? savedScope : undefined
  const guidance = context?.guidance
  const nextAction = guidance?.state === 'CURRENT' ? guidance.next_action : undefined
  const sourceAdvice = guidance?.sources.find(item => item.source_id === source?.source_id && item.revision === source?.revision)
  const usable = preflightUsable(source)
  const checks = source?.preflight?.report?.checks ?? []
  const mappedCount = checks.filter(item => item.code === 'MAPPING_READABLE' && item.status === 'CONFIRMED').length
  const uniqueChecks = checks.filter((item,index)=>checks.findIndex(other=>other.code===item.code&&other.status===item.status&&other.mapping_key===item.mapping_key)===index)
  const visibleChecks = [...(mappedCount ? [{code:'MAPPING_READABLE',status:'CONFIRMED' as const,mapping_key:null}] : []), ...uniqueChecks.filter(item => item.code !== 'MAPPING_READABLE' || item.status !== 'CONFIRMED')]
  const sourceResource = context?.resources.find(item=>item.resource_binding_id===source?.config.resource_binding_id)
  const staleResource = Boolean(source && !sourceResource)
  const common = source && context ? {source_id:source.source_id,revision:source.revision,basis_id:context.basis_id} : undefined
  const prepareAdoption = () => readAdoption(source, value => { setAdoption(value); setConfirmed(false); setDialog('adopt') })
  if(loading)return embedded?<LoadingState>正在读取证明来源…</LoadingState>:<EditorialPage width="summary"><Button onClick={onBack}>返回检查材料</Button><LoadingState>正在读取证明来源…</LoadingState></EditorialPage>
  const content=<>
    {!embedded&&<EditorialHeader eyebrow="检查材料 / 结果证明" title="准备检查用的文件和记录"><p className="editorial-muted">下载检查需要一份正确的文件作对照；内容和权限变化需要对应的业务记录。选一项，就能查看具体用什么材料。</p></EditorialHeader>}
    {providedPreparation?.(load)}
    {!providedMaterials && !embedded && context && sources.length>0 && !sources.every(item=>item.adopted&&preflightUsable(item)) && <ProofBatchPreparation context={context} onChanged={async()=>{await load();await onChanged()}}/>}
    {context && !sources.length && !editing && <div className="proof-empty-intro"><h3>{embedded ? '还没有这项结果的证明材料' : '先整理可以核对的证明材料'}</h3><p>{embedded ? '检查文件是否真的被取得，需要一份完整测试文件作为参照，并确认它属于哪个资源。' : '需要先找到业务记录或完整测试文件，让界鉴能核对规则约定的结果是否实际发生。'}</p><p className="editorial-muted">{providedMaterials ? '先使用检查材料页的“使用已提供的测试材料”，导入示例候选；也可以请 Agent 按当前需求整理。保存后点击“读取候选”。' : '可以交给 Agent 整理代码、账号和测试资源的对应。即使文件还没有生成，也能先确定获取办法；保存后点击“读取候选”。'}</p></div>}
    {!providedMaterials && !embedded&&<AgentAssistEntry aside heading={<div><h2>当前证明材料</h2><p className="editorial-muted">{source ? `正在核对：${effect?.label ?? '所选结果证明'}` : '先整理可用的文件与业务记录，再核对并采用。'}</p></div>} projectId={projectId} contextKey={`proof:${actionId??source?.config.action_id??'all'}:${source?.source_id??'new'}`}
      title="整理这项结果的证明办法" description="先核对代码、账号和测试资源的对应；文件尚未产生时，也可以先整理来源候选。" returnTo={`/tests?materials=1&project_id=${projectId}${actionId?`&action_id=${actionId}`:''}`}
      onNavigate={onNavigate??onBack} actions={<Button disabled={busy||Boolean(pending)} onClick={()=>void load()}>读取候选</Button>}
      loadContext={async()=>{const value=await proofSourcesApi.context(projectId);const current=value.sources.find(item=>item.source_id===source?.source_id)
        return {projectId:value.project_id,revisionKey:`${value.basis_id}:${current?.source_id??''}:${current?.revision??''}`,
          requestText:`请使用界鉴MCP为应用${projectId}${current?`的来源${current.source_id}（修订 ${current.revision}，动作 ${current.config.action_id}）`:actionId?`的动作${actionId}`:''}整理结果证明。先重新调用 jiejian_preparation_context 核对当前依据。${current?.config.source_kind==='REFERENCE_FILE'?'文件尚未产生时，可先保存reference_artifact和reference_origin为空的来源候选；核对资源集合、真实账号与正常录制。':'根据已确认的业务后果选择受支持的证明方法，缺少实际材料时保留缺口。'}若结果是对象创建，使用 CREATED_OBJECT_RECORDS / OBJECT_CREATION_V1；核对受控集合中的真实创建写入与按新编号恢复的材料，不使用录制旧编号执行正式检查。读取完整集合需要我明确确认。取样、读取授权和采用由我在界面确认。保存响应不明时查询原operation_id。`}}}/>}
    {issue && (!source || pending || editing || dialog) && <Alert type="warning" showIcon message={issue} action={pending && <Button onClick={() => void recover()} loading={busy}>查询原操作</Button>}/>}
    {notice && <p className="editorial-muted" role="status">{notice}</p>}
    {embedded && missingEffects.map(item=><div className="proof-missing-row" key={`${item.actionId}:${item.effect_id}`}>
      <div><strong>{item.label}</strong> <StatusBadge kind="preparation" tone="warning">待准备</StatusBadge>
        <p className="editorial-muted">尚未保存对应的文件或业务记录来源。请从材料页的 Agent 协助入口整理，也可以手动填写。</p></div>
      <Button disabled={busy||editing||Boolean(pending)} onClick={()=>{setSelected('__new__');setCollapsed(false);setDraft('');setEditing(true)}}>准备这项材料</Button>
    </div>)}
    {guidance?.state === 'NEEDS_REFRESH' && <Alert type="warning" showIcon message="准备条件在读取期间发生变化" description={guidance.note}/>}
    {nextAction && !needsReference && !embedded && !pending && !editing && <section className="proof-next-advice work-surface" aria-label="当前准备建议"><div><p className="editorial-eyebrow">{nextAction.handler === 'AGENT' ? '交给开发客户端中的 Agent 整理' : nextAction.handler === 'SYSTEM' ? '正在处理' : '现在需要你做'}</p><h2>{nextAction.title}</h2><p>{nextAction.reason}</p></div>
      {onNavigate && ['REVIEW_RUNTIME','REVIEW_IDENTITY','REVIEW_RULE_REFERENCE'].includes(nextAction.kind) && <Button onClick={() => onNavigate(nextAction.gui_url.slice(1))} disabled={busy}>前往处理</Button>}
    </section>}
    {!context ? <Button onClick={() => void load()}>重新读取</Button> : !sources.length && !editing ? <details className="proof-advanced"><summary>手动配置证明来源</summary><p className="editorial-muted">已经知道记录位置、账号和字段对应时，可以直接填写来源配置。</p><Button disabled={busy || Boolean(pending)} onClick={() => {setSelected('__new__');setDraft('');setEditing(true)}}>填写来源配置</Button></details> : <div className={`proof-workspace${embedded && sources.length < 2 ? " proof-workspace-single" : ""}`}>
      <aside className="proof-index" aria-label="待准备的结果">{!embedded && <h2>要证明的结果 <span>{sources.length}</span></h2>}
        {sources.map((item,index) => <button key={item.source_id} style={embedded?{order:index*2}:undefined} className="proof-index-item" aria-current={source?.source_id === item.source_id ? 'true' : undefined} aria-expanded={source?.source_id===item.source_id&&!collapsed} disabled={editing || Boolean(pending)} onClick={() => { setCollapsed(source?.source_id===item.source_id?!collapsed:false);setSelected(item.source_id); setIssue(undefined) }}>
          <span className="proof-row-identity"><StatusBadge kind="preparation" tone={preflightUsable(item)?'neutral':['RUNNING','PENDING','RETRY_WAIT'].includes(item.preflight?.state??'')?'info':'warning'}>{sourceLabel(item)}</StatusBadge><span className="proof-row-copy"><strong>{context.actions.find(value => value.action_id === item.config.action_id)?.effects.find(value => value.effect_id === item.config.effect_id)?.label ?? '结果证明'}</strong>{!embedded && <span>修订 {item.revision}</span>}</span></span>
          {embedded && <><span className="proof-row-purpose">{item.config.source_kind==='REFERENCE_FILE'?'用完整文件作为检查时的比对参照。':'用业务记录核对实际发生的结果。'}</span><span className="proof-row-operation">{source?.source_id===item.source_id&&!collapsed?'收起详情':item.adopted?'查看材料':'核对这项材料'}</span></>}</button>)}
        {!sources.length && <p className="editorial-muted">Agent 保存来源候选后，会显示在这里。</p>}
        {!providedMaterials && <Button type="link" disabled={busy || Boolean(pending)} onClick={() => { setSelected('__new__'); setDraft(''); setEditing(true) }}>手动补充来源</Button>}
      </aside>
      <section className="proof-detail work-surface" aria-label="当前证明来源" hidden={collapsed&&!editing} style={embedded?{order:Math.max(0,sources.findIndex(item=>item.source_id===source?.source_id))*2+1}:undefined}>
        {sourceAdvice?.next_action && sourceAdvice.next_action.source_id !== nextAction?.source_id && <p className="editorial-muted">这项来源：{sourceAdvice.next_action.reason}</p>}
        {!embedded && <section className="proof-focus">
          <div><p className="editorial-eyebrow">{action?.label ?? '结果证明准备'}</p>
            <h2>{!source ? '选择检查要用的材料' : !context.runtime_available ? '先启动这份应用' : needsReference ? '先取得一份完整测试文件' : !scope ? '允许界鉴读取这项材料' : source.adopted && usable ? '这项材料已经可以用于检查' : usable ? '材料核对完成，可以用于检查' : source.preflight?.report ? '这项材料需要更新' : '检查这项材料是否可用'}</h2>
            {effect && <p>要检查的是：{effect.label}</p>}</div>
          {source && <StatusBadge kind="preparation" tone={usable ? 'neutral' : 'warning'}>{sourceLabel(source)}</StatusBadge>}
        </section>}
        {source && <section className="proof-purpose" aria-label="这项材料怎样用于检查"><h3>这份材料的用途</h3><p>{createdSource ? '每次检查都会创建不同的对象。界鉴先保存集合的检查前状态，再用独立创建记录找到本次新对象；检查后只恢复本次对象，并核对原状态。录制中的编号仅用来说明材料来源。' : source.config.source_kind === 'REFERENCE_FILE'
          ? '这里准备的是一份内容正确的测试文件。正式检查会实际下载一次，再比较文件大小和内容摘要，判断有没有拿到完整文件。'
          : source.config.source_contract_id === 'TRANSACTION_HISTORY_V2' || source.config.source_contract_id === 'TRANSACTION_HISTORY_V1'
            ? '这里准备的是这份资源的业务变化记录。检查时用它判断哪个账号改了什么；即使随后撤回，也能查到之前发生的变化。'
            : '这里准备的是这份资源的内容记录。检查时把账号实际看到的内容与它比较，判断有没有读到规则保护的内容。'}</p>
          <dl className="proof-purpose-facts centered-fact-groups"><div><dt>对应动作</dt><dd>{action?.label}</dd></div><div><dt>{createdSource?'记录集合':source.config.source_kind==='REFERENCE_FILE'?'对照材料':'测试资源'}</dt><dd>{createdSource?source.config.collection:source.config.source_kind==='REFERENCE_FILE'?(source.config.reference_artifact?'已选定的完整文件':'尚未选定完整文件'):sourceResource?.resource_id??'尚未确认'}</dd></div><div><dt>材料类型</dt><dd>{createdSource?'本次请求的独立创建记录':source.config.source_kind==='REFERENCE_FILE'?'文件参照与接收记录':source.config.source_contract_id?.startsWith('TRANSACTION_')?'业务变化记录':'资源内容记录'}</dd></div></dl>
          {needsReference && <p className="editorial-muted">先取得一份完整测试文件，再核对内容与读取范围。</p>}</section>}
        {!running && source?.config.source_kind === 'REFERENCE_FILE' && source.config.reference_artifact && !source.adopted && <section className="proof-prepared-reference"><div><h3>{providedMaterials ? '示例测试文件已准备好' : '已选定一份测试文件'}</h3><p>核对它是否代表「{context.resources.find(item => item.resource_binding_id === source.config.resource_binding_id)?.resource_id}」的完整内容。然后确认读取范围并采用。</p></div><Button href={proofSourcesApi.referenceDownload(projectId,source.config.reference_artifact.asset_id)}>保存文件并核对内容</Button></section>}
        {!running && source?.config.source_kind === 'REFERENCE_FILE' && (needsReference ? <ReferenceFilePreparation key={source.source_id} projectId={projectId} context={context} source={source} busy={busy} pending={Boolean(pending)} preferredAsset={referenceAsset} captureId={captureId} onWrite={write} onRefresh={load}/> : <details className="proof-technical"><summary>查看或更换文件参照</summary><ReferenceFilePreparation key={source.source_id} projectId={projectId} context={context} source={source} busy={busy} pending={Boolean(pending)} preferredAsset={referenceAsset} captureId={captureId} onWrite={write} onRefresh={load}/></details>)}
        {source?.adopted && usable && <section className="proof-adopted-summary"><h3>检查会使用这些材料</h3><p>使用「{context.identities.find(item => item.identity_id === source.config.observation_identity_id)?.label ?? '已配置账号'}」核对「{context.resources.find(item => item.resource_binding_id === source.config.resource_binding_id)?.resource_id ?? '已配置资源'}」。</p><p>{source.config.source_kind === 'REFERENCE_FILE' ? '你选择的完整测试文件已作为比对参照。检查时会将实际收到的文件与它比较。' : '已允许读取这个账号对应的资源记录。检查时会重新读取，旧记录不会当作新结果。'}</p><p>要判断的结果：{effect?.label}。</p></section>}
        {identityFailed(source)&&<section className="proof-identity-recovery"><Alert type="warning" message="实际登录身份未通过核对" description="应用重启可能使旧会话失效，也可能登录了其他账号。请核对并重新准备对应测试账号，再发起新的预检查。旧失败报告仍保留。"/><div className="proof-identity-recovery-actions"><Button disabled={busy||Boolean(pending)} onClick={()=>onNavigate?onNavigate(`/tests?project_id=${encodeURIComponent(projectId)}&identities=1`):window.location.assign(`#/tests?project_id=${encodeURIComponent(projectId)}&identities=1`)}>核对测试账号</Button></div></section>}
        {source && !needsReference && <details className="proof-preflight-details" open={!embedded&&!(source.adopted&&usable)?true:undefined}><summary>查看读取范围与核对记录</summary><div className="proof-preflight-content">
          <ol className="proof-stages" aria-label="证明来源的四项事实">
            <li><span>配置</span><strong>候选修订 {source.revision}</strong></li>
            <li><span>读取范围</span><strong>{scope ? '已确认' : '待你确认'}</strong></li>
            <li><span>预检查</span><strong>{usable ? '当前依据可用' : source.preflight ? '需核对报告' : '尚未进行'}</strong></li>
            <li><span>采用</span><strong>{source.adopted ? usable ? '已采用' : '已采用，待复核' : '尚未采用'}</strong></li>
          </ol>
          <dl className="proof-facts"><div><dt>读取内容</dt><dd>{createdSource?'集合快照与本次创建记录':'单个资源的'}{createdSource?'':source.config.source_kind === 'REFERENCE_FILE' ? '完整文件接收' : source.config.source_contract_id === 'TRANSACTION_HISTORY_V2' ? '独立提交记录' : source.config.source_contract_id === 'TRANSACTION_HISTORY_V1' ? '业务操作记录（旧标准）' : '可见内容'}</dd></div><div><dt>观察账号</dt><dd>{context.identities.find(item => item.identity_id === source.config.observation_identity_id)?.label ?? '尚未确认'}</dd></div>
            <div><dt>{createdSource?'录制样本（不用于正式执行）':'对应资源'}</dt><dd>{context.resources.find(item => item.resource_binding_id === source.config.resource_binding_id)?.resource_id ?? '资源已经变化'}</dd></div><div><dt>读取范围</dt><dd>{scope ? '已由你确认' : savedScope ? '授权已保存，启动后核对' : '等待确认'}</dd></div></dl>
          {source.preflight && !source.preflight.current_basis && <Alert type="warning" message="准备条件已经变化" description="原报告保留；请对当前账号、资源和运行实例重新预检查。"/>}
          <section className="proof-checks"><div className="proof-section-heading"><h3>预检查发现</h3><span className="editorial-muted">仅核对材料，不作权限判断</span></div>
            {!source.preflight ? <p className="editorial-muted">尚未读取目标。确认范围后才能开始。</p> : !source.preflight.report ? <p role="status">{['PENDING','RUNNING','RETRY_WAIT'].includes(source.preflight.state) ? '正在独立核对身份和资源…' : '这次预检查未形成可用报告，可以核对条件后重新发起。'}</p> :
              <ul>{visibleChecks.map((check,index) => <li key={index}><div><strong>{check.code === 'MAPPING_READABLE' ? `${mappedCount} 项字段映射` : check.mapping_key ? keyLabels[check.mapping_key] ?? '业务字段' : reasonLabels[check.code] ?? '来源核对'}</strong>{(check.status !== 'CONFIRMED' || check.code === 'MAPPING_READABLE') && <p>{check.code === 'MAPPING_READABLE' ? '已找到配置中指定的字段。' : check.status === 'CONFIRMED' ? '本项已通过材料核对。' : reasonLabels[check.code] ?? '这一项尚未通过，请检查账号、资源和字段位置。'}</p>}</div><StatusBadge kind="preparation" tone={check.status === 'CONFIRMED' ? 'neutral' : 'warning'}>{check.status === 'CONFIRMED' ? '已核对' : check.status === 'UNSUPPORTED' ? '暂不支持' : '待补齐'}</StatusBadge></li>)}</ul>}
          </section>
          <details className="proof-technical"><summary>查看字段与读取依据</summary><p className="editorial-muted">来源位置：{source.config.relative_path_template}</p><dl>{Object.entries(source.config.mappings).map(([key,path]) => <div key={key}><dt>{keyLabels[key] ?? key}</dt><dd>{path.join('.')}</dd></div>)}</dl>
            <p className="editorial-muted">单次最多 {Math.round(source.config.max_response_bytes/1024)} KiB，{source.config.timeout_us/1000000} 秒。来源：{source.config.collection ? `受控资源集合 ${source.config.collection}` : '历史来源，需要重新准备'}</p>
            {scope && <Button danger disabled={busy || Boolean(pending)} onClick={() => void write('REVOKE_SCOPE',{scope_id:scope.scope_id})}>撤销这项读取授权</Button>}
          </details>
        </div></details>}
        {embedded && !source && <Button type="link" disabled={busy || Boolean(pending)} onClick={() => { setSelected("__new__"); setDraft(""); setEditing(true) }}>手动补充来源</Button>}
        {!providedMaterials && !editing && source && <details className="proof-advanced"><summary>高级：调整来源配置</summary><p className="editorial-muted">只有账号、资源或记录位置对应错误时才需要调整。也可以使用页首的 Agent 协助整理。</p><Button type="link" disabled={busy || Boolean(pending)} onClick={() => { setDraft(JSON.stringify(source.config,null,2)); setEditing(true) }}>手动调整配置</Button></details>}
        {editing && <section className="proof-editor"><h3>手动调整有限来源配置</h3><p className="editorial-muted">填写来源配置 JSON；只接受账号引用、固定读取路径与字段映射，不填写密码、Cookie 或令牌。</p>
          <Input.TextArea aria-label="证明来源配置" value={draft} onChange={event => setDraft(event.target.value)} rows={12} maxLength={32768} disabled={busy || Boolean(pending)}/>
          <TaskActionBar back={{label:'取消编辑',onClick:() => setEditing(false),disabled:busy || Boolean(pending)}} primary={{label:'保存来源候选',disabled:busy || Boolean(pending) || !draft.trim(),onClick:() => {
            try { const config: unknown = JSON.parse(draft); void write('SAVE_SOURCE',{basis_id:context.basis_id,config,source_id:source?.source_id ?? null,expected_revision:source?.revision ?? null}) }
            catch { setIssue('配置不是有效 JSON，请核对括号和字段。') }
          }}}/>
        </section>}
        {staleResource && <Alert type="warning" showIcon message={providedMaterials ? '应用修改后，旧材料仍指向之前的测试资源。请用页首的一键准备更新材料。' : '测试资源已经变化。请让 Agent 更新这项材料的资源对应，再重新核对。'}/>}
        {issue && source && !pending && !editing && !dialog && <p role="alert" className="proof-action-error">{issue}</p>}
        {!editing && source && <div className="proof-task-footer"><p className="editorial-muted">{pending?'本次操作结果还未确认，请查询原操作。':source.preflight&&['PENDING','RUNNING','RETRY_WAIT'].includes(source.preflight.state)?'核对仍在进行，可以先查看其它材料。':source.adopted&&usable?'这项材料已准备好，可以继续处理其它材料。':usable?'材料已通过核对，请确认将它用于后续检查。':'核对这项材料的账号、资源与读取范围。'}</p><TaskActionBar back={!embedded?{label:'返回检查材料',onClick:onBack}:undefined} refresh={!embedded?{label:'刷新准备情况',onClick:() => void load(),disabled:busy}:undefined}
          restart={source.preflight && ['PENDING','RUNNING','RETRY_WAIT'].includes(source.preflight.state) ? {label:'停止本次核对',danger:true,onClick:() => void write('CANCEL_PREFLIGHT',{preflight_id:source.preflight!.preflight_id}),disabled:busy || Boolean(pending)} : undefined}
          primary={pending?{label:'查询本次操作',loading:busy,onClick:()=>void recover()}:identityFailed(source)?{label:'核对测试账号',onClick:()=>onNavigate?onNavigate(`/tests?project_id=${encodeURIComponent(projectId)}&identities=1`):window.location.assign(`#/tests?project_id=${encodeURIComponent(projectId)}&identities=1`),disabled:busy}:source.config.source_kind === 'JSON_HTTP_RESOURCE' || needsReference || staleResource || !context.runtime_available || running ? undefined : !scope ? {label:'确认读取范围',onClick:() => { setConfirmed(false); setDialog('scope') },disabled:busy} : usable && !source.adopted ? {label:'确认使用这项材料',loading:busy,onClick:() => void prepareAdoption(),disabled:busy} : source.adopted && usable ? embedded?{label:'收起详情',onClick:()=>setCollapsed(true)}:undefined : {label:'开始预检查',loading:busy,onClick:() => void write('START_PREFLIGHT',common!),disabled:busy}}/></div>}
      </section>
    </div>}
    {!embedded && !source && !editing && <TaskActionBar back={{label:'返回检查材料',onClick:onBack}}/>}
    <Modal open={Boolean(dialog)} title={dialog === 'scope' ? '确认来源读取范围' : '将这项材料用于检查'} onCancel={() => { if (!busy) setDialog(undefined) }} closable={!busy} maskClosable={false}
      okText={dialog === 'scope' ? '允许这些读取' : '用于后续检查'} cancelText="返回核对" confirmLoading={busy} okButtonProps={{disabled:!confirmed || Boolean(pending)}} cancelButtonProps={{disabled:busy}}
      onOk={() => { if (dialog === 'scope') void write('GRANT_SCOPE',{...common,confirmed:true}); else if (adoption) void write('ADOPT_SOURCE',{source_id:adoption.source_id,revision:adoption.revision,basis_id:adoption.basis_id,preflight_id:adoption.preflight_id,confirmed:true}) }}>
      {dialog === 'scope' && source && <div className="proof-confirm"><p>{createdSource?'允许界鉴核对以下账号，并只读所选集合的全部对象标识、归属、版本和内容摘要，以及本次请求的创建记录。集合最多 256 个对象；超限会停止，不截断后宣称完整。':'允许界鉴使用以下账号核对身份，并只读所选记录集合中的对应资源。'}</p><dl><dt>应用地址</dt><dd>{context?.runtime_origin}</dd><dt>{createdSource?'整个记录集合':'记录来源'}</dt><dd>{createdSource?`/collections/${source.config.collection}`:source.config.relative_path_template}</dd><dt>身份接口</dt><dd>{[...new Set(source.config.identity_claims.map(item => item.request_path).filter(Boolean))].join('、')}</dd><dt>账号对应</dt><dd>{source.config.identity_claims.map(item => `${context?.identities.find(identity => identity.identity_id === item.identity_id)?.label ?? '账号'} → ${item.application_subject_id}`).join('；')}</dd></dl><p>最多 {Math.round(source.config.max_response_bytes/1024)} KiB／次，超时 {source.config.timeout_us/1000000} 秒。</p></div>}
      {dialog === 'adopt' && adoption && <div className="proof-confirm"><p><strong>{adoption.action_label} · {adoption.effect_label}</strong></p><h3>这次确认会保存什么</h3><ul><li>{createdSource?`每次使用本次实际创建的新对象，取证范围为集合 ${adoption.collection}。`:`测试对象：${adoption.resource_id}（${adoption.collection}）。`}</li><li>核对的结果：{adoption.effect_label}。</li><li>{source?.config.source_kind === 'REFERENCE_FILE' ? '把你核对过的完整文件设为参照，以后逐一比较实际收到的文件。' : '把当前账号和记录读取办法用于核对这项业务结果。'}</li></ul><p>{adoption.replaces_existing ? '替换此结果的准备配置，历史证据保留。' : '保存后，这项结果可以使用上述证明办法。'}</p>{adoption.mappings?.state && <p>核验字段：{adoption.mappings.state}；受保护状态：{adoption.expected_state ?? '任何变化'}。</p>}{Boolean(adoption.protected_projection?.length) && <p>受保护字段：{adoption.protected_projection?.join('、')}。</p>}<details><summary>查看保留内容与下轮复核范围</summary><p>继续沿用：{adoption.retained.join('、')}。</p><p>下次检查重新核对：{adoption.recheck.join('、')}。</p></details><p>采用只完成材料准备，权限结论来自之后的正式检查。</p></div>}
      {dialog==='adopt'&&source?.config.source_kind==='REFERENCE_FILE'&&<p>请确认这份参照代表上述测试资源的完整内容；技术比对只能核对实际收到的字节是否一致。</p>}
      <Checkbox checked={confirmed} onChange={event => setConfirmed(event.target.checked)} disabled={busy || Boolean(pending)}>{dialog==='adopt'&&source?.config.source_kind==='REFERENCE_FILE'?'我已核对参照内容、资源归属及采用影响':'我已核对以上范围与影响'}</Checkbox>
    </Modal>
  </>
  return embedded ? <section className="proof-inline proof-material-list" aria-label="结果证明材料">{content}</section> : <EditorialPage label="证明来源准备" width={!sources.length ? 'summary' : undefined}>{content}</EditorialPage>
}
