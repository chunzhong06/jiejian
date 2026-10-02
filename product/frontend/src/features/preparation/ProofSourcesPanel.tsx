// 证明准备围绕当前候选组织：默认交回原Agent配置，GUI只突出读取范围、缺口和采用决定。
import { Alert, Button, Checkbox, Input, Modal, Spin } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import { proofSourcesApi as api, type ProofContext, type ProofSource, type AdoptionPreview, type ProofOperationKind, type ProofReceipt } from '../../api/proofSources'
import { ApiError } from '../../api/http'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { StatusBadge } from '../../shared/ui/StatusBadge'
import { TaskActionBar } from '../../shared/ui/TaskActionBar'
import { useTaskGuard } from '../../app/tasks/TaskContinuity'
import './proof-sources.css'

const keyLabels: Record<string,string> = {resource_id:'资源标识',owner_id:'资源所有者',state:'业务状态',version:'资源版本',effect_count:'结果发生次数',history_generation:'历史代次',operation_id:'操作标识',operation_resource_id:'操作对应资源',operation_subject_id:'实际操作人',operation_before_version:'操作前版本',operation_after_version:'操作后版本',operation_state:'操作完成状态',unfinished_effects:'未完成后果',title:'资料标题',summary:'资料摘要',body:'完整内容'}
const reasonLabels: Record<string,string> = {SOURCE_REQUIRES_MIGRATION:'旧来源需要按通用方式重新准备',PROTECTED_FIELD_READABLE:'受保护字段已读到',RECORD_PROVIDER_UNAVAILABLE:'记录组件或运行对应暂时不可用',RECORD_SOURCE_UNAVAILABLE:'记录来源暂时无法读取',MAPPING_READABLE:'字段已读到',RESOURCE_OWNER_MATCH:'资源与所有者一致',SOURCE_CONTRACT_VERIFIED:'业务记录合同已核对',OPERATION_RECORD_COMPLETE:'当前操作记录完整',ACTUAL_IDENTITY_MATCH:'实际账号与角色一致',ACTUAL_IDENTITY_MISMATCH:'实际账号或角色不一致',CONTRACT_UNVERIFIED:'尚无可核对的业务记录合同',MAPPING_MISSING:'没有读到该字段',MAPPING_TYPE_INVALID:'字段类型与要求不同',MAPPING_REQUIRED:'缺少必要字段映射',SOURCE_READ_DENIED:'当前账号不能读取来源',SOURCE_READ_UNAVAILABLE:'来源暂时无法读取',IDENTITY_SESSION_MISSING:'账号需要重新登录',READ_AUTHORITY_UNAVAILABLE:'读取授权或运行实例已失效',RESOURCE_OWNER_MISMATCH:'资源或所有者不一致',COMPLETION_UNCONFIRMED:'操作完成情况尚未核对',JSON_DUPLICATE_KEY:'响应包含重复字段',JSON_INVALID:'响应不是有效对象',JSON_NONFINITE:'响应包含无效数值',JSON_STRUCTURE_LIMIT:'响应结构超出读取范围',RESPONSE_TOO_LARGE:'响应超出读取大小限制'}
type Pending = {kind: ProofOperationKind; operation: string}
const sourceLabel = (source: ProofSource) => source.config.source_kind === 'JSON_HTTP_RESOURCE' ? '需要重新准备' : source.adopted ? source.preflight?.current_basis ? '已采用' : '已采用 · 待复核' : source.preflight?.report?.assessment === 'USABLE' && source.preflight.current_basis ? '待你采用' : source.preflight?.state === 'RUNNING' ? '正在预检查' : source.preflight?.state === 'PENDING' ? '等待预检查' : '待准备'

export function ProofSourcesPanel({projectId, requestedSource, onBack, onChanged}: {
  projectId: string; requestedSource?: string | null; onBack: () => void; onChanged: () => Promise<unknown>
}) {
  const [context,setContext] = useState<ProofContext>(), [selected,setSelected] = useState(requestedSource ?? '')
  const [loading,setLoading] = useState(true), [busy,setBusy] = useState(false), [issue,setIssue] = useState<string>(), [notice,setNotice] = useState<string>()
  const [editing,setEditing] = useState(false), [draft,setDraft] = useState(''), [dialog,setDialog] = useState<'scope'|'adopt'>(), [confirmed,setConfirmed] = useState(false)
  const [adoption,setAdoption] = useState<AdoptionPreview>(), [pending,setPending] = useState<Pending>()
  const generation = useRef(0), sending = useRef(false)
  const storageKey = `jiejian-proof-operation:${projectId}`
  useTaskGuard(busy || Boolean(pending) || editing)
  const load = useCallback(async () => {
    const epoch = generation.current
    try {
      const value = await api.context(projectId)
      if (value.project_id !== projectId) throw new Error('scope')
      if (generation.current === epoch) { setContext(value); setLoading(false) }
    } catch { if (generation.current === epoch) { setIssue('准备信息暂时无法读取，请重新读取后继续。'); setLoading(false) } }
  },[projectId])
  useEffect(() => {
    generation.current += 1; setContext(undefined); setSelected(requestedSource ?? ''); setLoading(true); setIssue(undefined); setPending(undefined); setEditing(false); setDialog(undefined)
    try { const stored = sessionStorage.getItem(storageKey); if (stored) { const value = JSON.parse(stored) as Pending; if (/^[0-9a-f]{32}$/.test(value.operation) && ['SAVE_SOURCE','GRANT_SCOPE','START_PREFLIGHT','CANCEL_PREFLIGHT','ADOPT_SOURCE','REVOKE_SCOPE'].includes(value.kind)) { setPending(value); setIssue('上次操作回执尚未确认，请查询原操作。') } } } catch { /* 浏览器存储不可用时仍保留本页内存回执。 */ }
    void load()
    return () => { generation.current += 1 }
  },[load,requestedSource,storageKey])
  const running = context?.sources.some(item => ['PENDING','RUNNING','RETRY_WAIT'].includes(item.preflight?.state ?? ''))
  useEffect(() => { if (!running || busy) return; const timer = setInterval(() => void load(),1500); return () => clearInterval(timer) },[running,busy,load])
  const source = context?.sources.find(item => item.source_id === selected) ?? (!selected ? context?.sources[0] : undefined)
  const action = context?.actions.find(item => item.action_id === source?.config.action_id)
  const effect = action?.effects.find(item => item.effect_id === source?.config.effect_id)
  const savedScope = context?.read_scopes.find(item => source && (!context.runtime_origin || item.origin === context.runtime_origin)
    && (!source.config.read_scope_id || source.config.read_scope_id === item.scope_id)
    && item.path_templates.includes(source.config.relative_path_template)
    && source.config.identity_claims.every(claim => Boolean(claim.request_path && item.path_templates.includes(claim.request_path)))
    && item.resource_binding_ids.includes(source.config.resource_binding_id)
    && source.config.identity_claims.every(claim => item.identity_ids.includes(claim.identity_id))
    && item.max_response_bytes >= source.config.max_response_bytes && item.timeout_us >= source.config.timeout_us)
  const scope = context?.runtime_available ? savedScope : undefined
  const usable = Boolean(source?.preflight?.report?.assessment === 'USABLE' && source.preflight.current_basis)
  const checks = source?.preflight?.report?.checks ?? []
  const mappedCount = checks.filter(item => item.code === 'MAPPING_READABLE' && item.status === 'CONFIRMED').length
  const visibleChecks = [...(mappedCount ? [{code:'MAPPING_READABLE',status:'CONFIRMED' as const,mapping_key:null}] : []), ...checks.filter(item => item.code !== 'MAPPING_READABLE' || item.status !== 'CONFIRMED')]
  const clearPending = () => { setPending(undefined); try { sessionStorage.removeItem(storageKey) } catch { /* 无存储时仅清空本页状态。 */ } }
  const accept = async (receipt: ProofReceipt, expected: Pending) => {
    if (receipt.project_id !== projectId || receipt.operation_id !== expected.operation || receipt.operation_kind !== expected.kind) throw new Error('receipt mismatch')
    clearPending(); setEditing(false); setDialog(undefined)
    if (receipt.result.source_id) setSelected(receipt.result.source_id)
    setNotice(expected.kind === 'ADOPT_SOURCE' ? '证明来源已采用，可以返回检查材料。' : '操作已保存。')
    await load(); try { await onChanged() } catch { setIssue('操作已保存，检查材料的显示尚未同步。请刷新准备情况。') }
  }
  const write = async (kind: ProofOperationKind, body: object) => {
    if (sending.current || pending) return
    const epoch = generation.current, operation = crypto.randomUUID().replaceAll('-',''), next = {kind,operation}
    sending.current = true; setBusy(true); setIssue(undefined); setPending(next)
    try {
      // 先持久保存操作身份，再发写请求；刷新后只能查询同键回执，不自动重发。
      try { sessionStorage.setItem(storageKey,JSON.stringify(next)) } catch { clearPending(); setIssue('浏览器暂时不能保留操作回执，本次尚未提交。请恢复浏览器存储后再试。'); return }
      const receipt = await api.write(projectId,kind,{...body,operation_id:operation})
      if (generation.current === epoch) await accept(receipt,next)
    } catch (error) { if (generation.current === epoch) {
      if (error instanceof ApiError && ['INPUT_INVALID','STATE_PRECONDITION','STORAGE_SECRET','API_VALIDATION_ERROR','RECORD_NOT_FOUND'].includes(error.code)) {
        clearPending(); setIssue(error.message)
      } else setIssue('操作回执尚未确认，请查询原操作。不要重复提交。')
    } } finally { sending.current = false; if (generation.current === epoch) setBusy(false) }
  }
  const recover = async () => {
    if (!pending || sending.current) return
    sending.current = true; setBusy(true); const epoch = generation.current
    try { const receipt = await api.receipt(projectId,pending.kind,pending.operation); if (generation.current === epoch) await accept(receipt,pending) }
    catch { if (generation.current === epoch) setIssue('原操作的回执仍未确认，当前输入不会再次提交。') }
    finally { sending.current = false; if (generation.current === epoch) setBusy(false) }
  }
  const common = source && context ? {source_id:source.source_id,revision:source.revision,basis_id:context.basis_id} : undefined
  const prepareAdoption = async () => {
    if (!source?.preflight) return
    const epoch = generation.current; setBusy(true); setIssue(undefined)
    try { const value = await api.adoptionPreview(projectId,source.source_id,source.preflight.preflight_id)
      if (value.project_id !== projectId || value.source_id !== source.source_id || value.revision !== source.revision) throw new Error('scope')
      if (epoch === generation.current) { setAdoption(value); setConfirmed(false); setDialog('adopt') }
    } catch (error) { if (epoch === generation.current) setIssue(error instanceof Error ? error.message : '采用预览未能读取。') }
    finally { if (epoch === generation.current) setBusy(false) }
  }
  const copyPrompt = async () => {
    try { await navigator.clipboard.writeText(`请使用界鉴MCP为应用 ${projectId}${source ? ` 的证明来源 ${source.source_id}` : ''}完善结果证明。先调用 jiejian_preparation_context，沿用可复用材料；保存有限来源候选，在已有读取授权内预检查并修正缺口。需要确认读取范围或采用时给我GUI入口，不批准或改变权限。`); setNotice('已复制，可粘贴到你正在使用的 Agent。') }
    catch { setIssue('未能复制，请在原 Agent 中让它读取本应用的 preparation_context。') }
  }
  if (loading) return <EditorialPage><Spin />正在读取证明来源…</EditorialPage>
  return <EditorialPage label="证明来源准备">
    <EditorialHeader eyebrow="检查材料 / 结果证明" title="让规则有据可验"><p className="editorial-muted">在原 Agent 中完善配置，在这里核对它将读取什么、还缺什么。</p></EditorialHeader>
    <div className="proof-toolbar"><Button type="link" onClick={onBack} disabled={busy || Boolean(pending)}>返回检查材料</Button><Button onClick={() => void load()} disabled={busy}>刷新准备情况</Button></div>
    {issue && <Alert type="warning" showIcon message={issue} action={pending && <Button onClick={() => void recover()} loading={busy}>查询原操作</Button>}/>}
    {notice && <p className="editorial-muted" role="status">{notice}</p>}
    {!context ? <Button onClick={() => void load()}>重新读取</Button> : <div className="proof-workspace">
      <aside className="proof-index" aria-label="来源候选"><h2>来源候选 <span>{context.sources.length}</span></h2>
        {context.sources.map(item => <button key={item.source_id} className="proof-index-item" aria-current={source?.source_id === item.source_id ? 'true' : undefined} disabled={busy || editing || Boolean(pending)} onClick={() => { setSelected(item.source_id); setIssue(undefined) }}>
          <strong>{context.actions.find(value => value.action_id === item.config.action_id)?.effects.find(value => value.effect_id === item.config.effect_id)?.label ?? '结果证明'}</strong>
          <span>修订 {item.revision} · {sourceLabel(item)}</span></button>)}
        {!context.sources.length && <p className="editorial-muted">Agent 保存来源候选后，会显示在这里。</p>}
        <Button type="link" disabled={busy || Boolean(pending)} onClick={() => { setSelected('__new__'); setDraft(''); setEditing(true) }}>手动补充来源</Button>
      </aside>
      <section className="proof-detail" aria-label="当前证明来源">
        <section className="proof-focus">
          <div><p className="editorial-eyebrow">{source ? `${action?.label ?? '业务动作'} · ${source.client_name}` : '准备下一步'}</p>
            <h2>{!source ? '先让 Agent 整理证明来源' : !context.runtime_available ? '先确认应用的运行实例' : !scope ? '确认这次读取范围' : source.adopted && usable ? '来源已就绪，返回正式检查' : usable ? '核对来源，然后采用' : source.preflight?.report ? '补齐预检查发现的缺口' : '先核对来源是否可用'}</h2>
            <p>{effect?.label ?? '界鉴会根据已经确认的规则和材料，指出可以复用的部分。'}</p></div>
          {source && <StatusBadge kind="preparation" tone={usable ? 'neutral' : 'warning'}>{sourceLabel(source)}</StatusBadge>}
        </section>
        {source && <>
          <dl className="proof-facts"><div><dt>读取内容</dt><dd>单个资源的{source.config.source_contract_id === 'TRANSACTION_HISTORY_V1' ? '业务操作记录' : '可见内容'}</dd></div><div><dt>观察账号</dt><dd>{context.identities.find(item => item.identity_id === source.config.observation_identity_id)?.label ?? '尚未确认'}</dd></div>
            <div><dt>对应资源</dt><dd>{context.resources.find(item => item.resource_binding_id === source.config.resource_binding_id)?.resource_id ?? '资源已经变化'}</dd></div><div><dt>读取范围</dt><dd>{scope ? '已由你确认' : savedScope ? '授权已保存，启动后核对' : '等待确认'}</dd></div></dl>
          {source.preflight && !source.preflight.current_basis && <Alert type="warning" message="准备条件已经变化" description="原报告保留；请对当前账号、资源和运行实例重新预检查。"/>}
          <section className="proof-checks"><div className="proof-section-heading"><h3>预检查发现</h3><span className="editorial-muted">仅核对材料，不作权限判断</span></div>
            {!source.preflight ? <p className="editorial-muted">尚未读取目标。确认范围后才能开始。</p> : !source.preflight.report ? <p role="status">{['PENDING','RUNNING','RETRY_WAIT'].includes(source.preflight.state) ? '正在独立核对身份和资源…' : '这次预检查未形成可用报告，可以核对条件后重新发起。'}</p> :
              <ul>{visibleChecks.map((check,index) => <li key={index}><div><strong>{check.code === 'MAPPING_READABLE' ? `${mappedCount} 项字段映射` : check.mapping_key ? keyLabels[check.mapping_key] ?? '业务字段' : reasonLabels[check.code] ?? '来源核对'}</strong><p>{reasonLabels[check.code] ?? '当前来源还需要核对'}</p></div><StatusBadge kind="preparation" tone={check.status === 'CONFIRMED' ? 'neutral' : 'warning'}>{check.status === 'CONFIRMED' ? '已核对' : check.status === 'UNSUPPORTED' ? '暂不支持' : '待补齐'}</StatusBadge></li>)}</ul>}
          </section>
          <details className="proof-technical"><summary>查看字段与读取依据</summary><p className="editorial-muted">来源位置：{source.config.relative_path_template}</p><dl>{Object.entries(source.config.mappings).map(([key,path]) => <div key={key}><dt>{keyLabels[key] ?? key}</dt><dd>{path.join('.')}</dd></div>)}</dl>
            <p className="editorial-muted">单次最多 {Math.round(source.config.max_response_bytes/1024)} KiB，{source.config.timeout_us/1000000} 秒。来源：{source.config.collection ? `受控资源集合 ${source.config.collection}` : '历史来源，需要重新准备'}</p>
            {scope && <Button type="link" danger disabled={busy || Boolean(pending)} onClick={() => void write('REVOKE_SCOPE',{scope_id:scope.scope_id})}>撤销这项读取授权</Button>}
          </details>
        </>}
        <div className="proof-agent-return"><p>配置仍在原 Agent 中完成；这里保留每次核对和你的采用决定。</p><Button onClick={() => void copyPrompt()}>复制给 Agent 的准备说明</Button></div>
        {!editing && source && <Button type="link" disabled={busy || Boolean(pending)} onClick={() => { setDraft(JSON.stringify(source.config,null,2)); setEditing(true) }}>手动调整配置</Button>}
        {editing && <section className="proof-editor"><h3>手动调整有限来源配置</h3><p className="editorial-muted">填写来源配置 JSON；只接受账号引用、固定读取路径与字段映射，不填写密码、Cookie 或令牌。</p>
          <Input.TextArea aria-label="证明来源配置" value={draft} onChange={event => setDraft(event.target.value)} rows={12} maxLength={32768} disabled={busy || Boolean(pending)}/>
          <TaskActionBar back={{label:'取消编辑',onClick:() => setEditing(false),disabled:busy || Boolean(pending)}} primary={{label:'保存来源候选',disabled:busy || Boolean(pending) || !draft.trim(),onClick:() => {
            try { const config: unknown = JSON.parse(draft); void write('SAVE_SOURCE',{basis_id:context.basis_id,config,source_id:source?.source_id ?? null,expected_revision:source?.revision ?? null}) }
            catch { setIssue('配置不是有效 JSON，请核对括号和字段。') }
          }}}/>
        </section>}
        {!editing && source && <TaskActionBar back={{label:'返回检查材料',onClick:onBack,disabled:busy || Boolean(pending)}}
          restart={source.preflight && ['PENDING','RUNNING','RETRY_WAIT'].includes(source.preflight.state) ? {label:'取消预检查',onClick:() => void write('CANCEL_PREFLIGHT',{preflight_id:source.preflight!.preflight_id}),disabled:busy || Boolean(pending)} : undefined}
          primary={source.config.source_kind === 'JSON_HTTP_RESOURCE' || !context.runtime_available || running ? undefined : !scope ? {label:'确认读取范围',onClick:() => { setConfirmed(false); setDialog('scope') },disabled:busy || Boolean(pending)} : usable && !source.adopted ? {label:'预览采用影响',onClick:() => void prepareAdoption(),disabled:busy || Boolean(pending)} : source.adopted && usable ? undefined : {label:'开始预检查',onClick:() => void write('START_PREFLIGHT',common!),disabled:busy || Boolean(pending)}}/>}
      </section>
    </div>}
    <Modal open={Boolean(dialog)} title={dialog === 'scope' ? '确认来源读取范围' : '采用这项证明来源'} onCancel={() => { if (!busy) setDialog(undefined) }} closable={!busy} maskClosable={false}
      okText={dialog === 'scope' ? '允许这些读取' : '确认采用'} cancelText="返回核对" confirmLoading={busy} okButtonProps={{disabled:!confirmed || Boolean(pending)}} cancelButtonProps={{disabled:busy}}
      onOk={() => { if (dialog === 'scope') void write('GRANT_SCOPE',{...common,confirmed:true}); else if (adoption) void write('ADOPT_SOURCE',{source_id:adoption.source_id,revision:adoption.revision,basis_id:adoption.basis_id,preflight_id:adoption.preflight_id,confirmed:true}) }}>
      {dialog === 'scope' && source && <div className="proof-confirm"><p>允许界鉴使用以下账号核对身份，并只读所选记录集合中的对应资源。</p><dl><dt>应用地址</dt><dd>{context?.runtime_origin}</dd><dt>记录来源</dt><dd>{source.config.relative_path_template}</dd><dt>身份接口</dt><dd>{[...new Set(source.config.identity_claims.map(item => item.request_path).filter(Boolean))].join('、')}</dd><dt>账号对应</dt><dd>{source.config.identity_claims.map(item => `${context?.identities.find(identity => identity.identity_id === item.identity_id)?.label ?? '账号'} → ${item.application_subject_id}`).join('；')}</dd></dl><p>最多 {Math.round(source.config.max_response_bytes/1024)} KiB／次，超时 {source.config.timeout_us/1000000} 秒。</p></div>}
      {dialog === 'adopt' && adoption && <div className="proof-confirm"><p><strong>{adoption.action_label} · {adoption.effect_label}</strong></p><p>{adoption.replaces_existing ? '更新这一结果的证明来源，历史证据仍然保留。' : '为这一结果保存正式证明来源。'}</p><p>资源集合：{adoption.collection}；资源：{adoption.resource_id}。</p>{adoption.mappings?.state && <p>核验字段：{adoption.mappings.state}；受保护状态：{adoption.expected_state ?? '任何变化'}。</p>}{Boolean(adoption.protected_projection?.length) && <p>受保护字段：{adoption.protected_projection?.join('、')}。</p>}<p>继续沿用：{adoption.retained.join('、')}。</p><p>下次检查重新核对：{adoption.recheck.join('、')}。</p><p>采用只完成材料准备，权限结论来自之后的正式检查。</p></div>}
      <Checkbox checked={confirmed} onChange={event => setConfirmed(event.target.checked)} disabled={busy || Boolean(pending)}>我已核对以上范围与影响</Checkbox>
    </Modal>
  </EditorialPage>
}
