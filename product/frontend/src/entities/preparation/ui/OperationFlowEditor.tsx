import {IndexSelection} from '../../../shared/ui/IndexSelection'
import './operation-flow.css'
import {EntityEvidenceEditor} from './EntityEvidenceEditor'
import {FlowRequestInputs} from './FlowRequestInputs'
import {FlowTrialPanel} from './FlowTrialPanel'
import {FlowCandidateReview,flowDraftKey,type FlowEditorDraft} from './FlowCandidateReview'
import {editorDraft,rememberEditorDraft,requestCollaboration,useHandoffContext} from '../../runtime/model/handoff'
import {compileSteps,decodeSteps,newParameter,type EditableStep} from './flowInputs'
import type {EntityEvidence,ApiSourceReference} from '../api/operationFlows'
import {Choice} from '../../../shared/ui/Choice'
import {useEffect,useId,useState} from 'react'
import {Tabs} from '../../../shared/ui/Tabs'
import {Dialog} from '../../../shared/ui/Dialog'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import PlusOutlined from '@ant-design/icons/PlusOutlined'
import {operationFlowsApi as api,type FlowStep,type OperationFlow,type ApiCandidate} from '../api/operationFlows'
import {testIdentitiesApi} from '../api/testIdentities'
import type {SourceRequest} from '../../application/api/workbench'
import {useRead} from '../../../shared/lib/useRead'
import {go} from '../../../shared/lib/navigation'
import {Button} from '../../../shared/ui/actions'
import {Field,Heading} from '../../../shared/ui/layout'
import {PageError, Badge,ErrorNote,Loading,Notice} from '../../../shared/ui/feedback'

const blank=(index:number):EditableStep=>({id:'step_'+index+'_'+crypto.randomUUID().slice(0,8),method:'GET',path:'/',parameters:[]})
export function OperationFlowEditor({projectId,actionId,onBack,initialRequest,initialSource,initialFlow,initialTrialId,candidateFlow}:{projectId:string;actionId:string;onBack:()=>void;initialRequest?:SourceRequest;initialSource?:ApiSourceReference;initialFlow?:OperationFlow;initialTrialId?:string;candidateFlow?:OperationFlow}) {
    const [restored]=useState(()=>initialFlow?undefined:editorDraft<FlowEditorDraft>(flowDraftKey(projectId,actionId)))
    const [candidateReviewed,setCandidateReviewed]=useState(false)
    const state=useRead('operation-flow:'+projectId,async(signal)=>{const [context,identities]=await Promise.all([api.context(projectId,signal),testIdentitiesApi.list(projectId,signal)]);return{context,identities}})
    const originPanel=useId()
    const [phase,setPhase]=useState(restored?.phase??(initialRequest?1:0)),[origin,setOrigin]=useState<'existing'|'recording'|'openapi'|'manual'>(restored?.origin??'existing'),[existingId,setExistingId]=useState('')
    const [csrfPath,setCsrfPath]=useState('/api/csrf'),[csrfField,setCsrfField]=useState('$.csrf'),[csrfHeader,setCsrfHeader]=useState('X-CSRF-Token')
    const [sourceRequest,setSourceRequest]=useState<ApiSourceReference|undefined>(restored?.sourceRequest??initialSource)
    const [entityEvidence,setEntityEvidence]=useState<EntityEvidence[]>(restored?.entityEvidence??[])
    const [flowId,setFlowId]=useState(()=>restored?.flowId??'ofl_'+crypto.randomUUID().replaceAll('-','')),[revision,setRevision]=useState(restored?.revision??1)
    const [steps,setSteps]=useState<EditableStep[]>(restored?.steps??[{id:'step_1',method:initialRequest?.method??'GET',path:initialRequest?.path??'/',parameters:(initialRequest?.parameters??[]).filter(item=>item.location!=='HEADER'||!['authorization','cookie','host','content-length','connection','transfer-encoding'].includes(item.name.toLowerCase())).map(item=>({...newParameter(item.location==='BODY'?'JSON_BODY':item.location),name:item.name,source:item.sensitive?'PRIOR_STEP_JSON_PATH':'LITERAL',secret:item.sensitive}))}]),[selected,setSelected]=useState(restored?.selected??0),[target,setTarget]=useState(restored?.target??'step_1'),[createdPath,setCreatedPath]=useState(restored?.createdPath??'')
    const [subject,setSubject]=useState(restored?.subject??''),[owner,setOwner]=useState(restored?.owner??''),[resource,setResource]=useState(restored?.resource??''),[recovery,setRecovery]=useState(restored?.recovery??''),[restoreMethod,setRestoreMethod]=useState(restored?.restoreMethod??'POST'),[restoreBody,setRestoreBody]=useState(restored?.restoreBody??'{}')
    const [provenance,setProvenance]=useState<OperationFlow['provenance']>(restored?.provenance??'MANUAL'),[recordingId,setRecordingId]=useState(restored?.recordingId??''),[candidates,setCandidates]=useState<ApiCandidate[]>([])
    const [busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),[saved,setSaved]=useState<OperationFlow|undefined>(restored?.saved),[adopted,setAdopted]=useState(false),[trialInteracting,setTrialInteracting]=useState(false)
    const [csrfOpen,setCsrfOpen]=useState(false)
    const action=state.data?.context.actions.find(item=>item.action_id===actionId)
    // 结果查询或恢复确有配置时才增加一个阶段；普通只读请求直接进入核对。
    const needsOutcome=Boolean(action?.state_changing||action?.effects.some(item=>item.kind==='DATA_DISCLOSURE'))
    const reviewPhase=needsOutcome?4:3
    const outcomeLabel=action?.state_changing?'结果与恢复':'结果核对'
    const act=async(callback:()=>Promise<void>)=>{if(busy)return;setBusy(true);setError(undefined);try{await callback()}catch(e){setError(e)}finally{setBusy(false)}}
    // 草稿保存不改变当前检查输入；再次编辑后，必须保存新修订才能确认使用。
    const dirty=()=>{if(saved)setRevision(Math.max(saved.revision,state.data?.context.flows.find(item=>item.document.id===saved.id)?.document.revision??0)+1);setSaved(undefined);setAdopted(false)}
    const update=(next:EditableStep)=>{dirty();setSteps(steps.map((step,index)=>index===selected?next:step))}
    const loadSteps=(items:FlowStep[],targetId:string)=>{
        try{setSteps(decodeSteps(items))}catch(error){setError(error);return false}
        setSelected(0);setTarget(targetId);setCreatedPath((items.find(item=>item.id===targetId)?.request_template.response_extractors?.find(item=>item.extractor_id==='created_resource_id')?.json_path as string)??'');dirty()
        return true
    }
    const load=(document:OperationFlow)=>{setSourceRequest(document.source_request);setEntityEvidence(document.entity_evidence??[]);if(!loadSteps(document.workflow.steps,document.workflow.target_step_id))return false;setFlowId(document.id);setRevision(Math.max(document.revision,state.data?.context.flows.find(item=>item.document.id===document.id)?.document.revision??0)+1);setSubject(document.subject_test_identity_id);setOwner(document.resource_owner_test_identity_id);setResource(document.actual_resource_id);setRecovery(document.recovery?.relative_path??'');setRestoreMethod(document.recovery?.method??'POST');setRestoreBody(JSON.stringify(document.recovery?.json_body??{},null,2));setProvenance(document.provenance);setRecordingId(document.source_recording_id??'');return true}
    useEffect(()=>{if(initialFlow&&state.data&&load(initialFlow)){setSaved(initialFlow);setRevision(initialFlow.revision);setPhase(reviewPhase)}},[initialFlow?.id,initialFlow?.revision,Boolean(state.data),reviewPhase])
    const effectiveIdentity=state.data?.identities.find(item=>item.auth_method!==null)?.identity_id??''
    const snapshot:FlowEditorDraft={phase,origin,sourceRequest,entityEvidence,flowId,revision,steps,selected,target,createdPath,subject:subject||effectiveIdentity,owner:owner||effectiveIdentity,resource,recovery,restoreMethod,restoreBody,provenance,recordingId,saved}
    useEffect(()=>{rememberEditorDraft(flowDraftKey(projectId,actionId),snapshot)})
    const safePath=(path:string)=>{const shape=path.split(/[?#]/)[0];return /^\/[A-Za-z0-9_./{}~:@%+\-]*$/.test(shape)?shape:null}
    useHandoffContext(action?{projectId,label:action.label+' · 接口流程草稿',references:{action_id:actionId,flow_id:flowId,revision:String(revision),return_to:'/testing?action_id='+actionId+'&resume_draft=1'},editor:{kind:'FLOW',flow_id:flowId,revision:saved?Math.max(saved.revision,...state.data!.context.flows.filter(item=>item.document.id===flowId).map(item=>item.document.revision))+1:revision,action_id:actionId,action_revision:action.revision,subject_identity_id:snapshot.subject||null,owner_identity_id:snapshot.owner||null,target_step_id:target,steps:steps.map(item=>({id:item.id,method:item.method,path:safePath(item.path),parameters:item.parameters.map(parameter=>({location:parameter.location,name:parameter.name,source:parameter.source,secret:parameter.secret}))})),recovery_path:recovery?safePath(recovery):null,evidence_effect_ids:entityEvidence.map(item=>item.effect_id),evidence_queries:entityEvidence.map(item=>({effect_id:item.effect_id,request_path:safePath(String(item.query.request.path??'')),resource_path:item.query.resource_path,owner_path:item.query.owner_path,data_path:item.query.data_path}))}}:undefined)
    if(state.loading)return <Loading page/>
    if(!state.data)return <PageError title="接口流程" error={state.error}/>
    const {context,identities}=state.data,step=steps[selected]
    const accounts=identities.filter(item=>item.auth_method!==null)
    const subjectId=subject||accounts[0]?.identity_id,ownerId=owner||accounts[0]?.identity_id
    const participantsReady=accounts.some(item=>item.identity_id===subjectId)&&accounts.some(item=>item.identity_id===ownerId)
    const compile=()=>compileSteps(steps,target,createdPath)
    const matching=context.flows.filter(item=>item.document.business_action_id===actionId)
    const existing=matching.find(item=>item.document.id+'@'+item.document.revision===existingId)??matching.find(item=>item.in_use)??matching[0]
    const inspectExisting=()=>{
        if(!load(existing!.document))return
        if(existing!.configuration_current){setSaved(existing!.document);setRevision(existing!.document.revision)}
        setPhase(reviewPhase)
    }
    const phaseLabels=['选择起点','账号与测试数据','执行请求',...(needsOutcome?[outcomeLabel]:[]),'核对并使用']
    const saveFlow=()=>void act(async()=>{
        const candidate=await api.candidate(projectId,{id:flowId,revision,business_action_id:actionId,action_revision:action!.revision,subject_test_identity_id:subjectId,resource_owner_test_identity_id:ownerId,source_fingerprint:context.source_fingerprint,entity_evidence:entityEvidence,source_request:sourceRequest,provenance,source_recording_id:provenance==='RECORDING'?recordingId:null,actual_resource_id:resource,target_step_id:target,steps:compile(),recovery:action!.state_changing?{method:restoreMethod,relative_path:recovery,json_body:JSON.parse(restoreBody)}:null})
        setSaved(await api.save(projectId,candidate));state.reload()
    })
    return <>
        <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={onBack}>返回操作准备</Button></div>
        <Heading eyebrow={action?.label} title="接口流程" actions={<Button disabled={busy||trialInteracting} onClick={()=>requestCollaboration(projectId,'SETUP','补全「'+(action?.label??'当前操作')+'」的接口流程，整理执行步骤、结果核对与恢复安排。')}>请 Agent 补全</Button>}/>
        {error&&<ErrorNote error={error}/>}
        {candidateFlow&&!candidateReviewed&&<FlowCandidateReview candidate={candidateFlow} previous={restored} accounts={accounts} onKeep={()=>setCandidateReviewed(true)} onApply={preserve=>{
            const values=preserve?steps:[]
            if(!load(candidateFlow))return
            let merged=decodeSteps(candidateFlow.workflow.steps)
            merged=merged.map(item=>({...item,parameters:item.parameters.map(parameter=>{
                const previous=values.find(step=>step.id===item.id)?.parameters.find(old=>old.name===parameter.name&&old.location===parameter.location&&old.source==='LITERAL'&&parameter.source==='LITERAL')
                return previous?{...parameter,value:previous.value,json:previous.json}:parameter
            })}))
            const preserveRecovery=preserve&&recovery===candidateFlow.recovery?.relative_path&&restoreMethod===candidateFlow.recovery?.method
            const changed=JSON.stringify(merged)!==JSON.stringify(decodeSteps(candidateFlow.workflow.steps))||preserveRecovery&&restoreBody!==JSON.stringify(candidateFlow.recovery?.json_body??{},null,2)
            if(preserveRecovery)setRestoreBody(restoreBody)
            setSteps(merged);setRevision(changed?Math.max(candidateFlow.revision,context.flows.find(item=>item.document.id===candidateFlow.id)?.document.revision??0)+1:candidateFlow.revision);setSaved(changed?undefined:candidateFlow);setCandidateReviewed(true);setPhase(reviewPhase)
        }}/>}
        <section className="jj-flow-workspace" data-phase={phase} data-stages={phaseLabels.length}>
            <IndexSelection as="ol" className="jj-flow-phases" label="操作设置进度" identity={String(phase)}>{phaseLabels.map((label,index)=><li key={label} data-current={phase===index} data-complete={phase>index}><button className="jj-index-item" disabled={index>phase||busy||trialInteracting} aria-current={phase===index?'step':undefined} onClick={()=>setPhase(index)}><span>{phase>index?'✓':index+1}</span>{label}</button></li>)}</IndexSelection>
            <div className="jj-flow-body">
            {phase===0&&<section className="jj-flow-start" key="start"><header><h2>从已有操作开始</h2><p>优先使用真实录制。需要串联多个接口时，再补充执行步骤。</p></header>
                <div className="jj-flow-origins"><Tabs label="流程的来源" value={origin} items={[{value:'existing',label:'沿用已有流程'},{value:'recording',label:'使用操作录制'},{value:'openapi',label:'导入接口文档'},{value:'manual',label:'手动填写接口'}]} idPrefix={originPanel} panelId={originPanel+'-content'} onValueChange={value=>setOrigin(value as typeof origin)}/>
                    <div className="jj-flow-origin-content" key={origin} role="tabpanel" id={originPanel+'-content'} aria-labelledby={originPanel+'-'+origin}>
                    {origin==='existing'&&<><h3>继续修改已保存的流程</h3>{matching.length?<><Field label="选择流程"><Choice value={existing?existing.document.id+'@'+existing.document.revision:''} onValueChange={selectedValue=>setExistingId(selectedValue)}>{matching.map(item=><option key={item.document.id+'@'+item.document.revision} value={item.document.id+'@'+item.document.revision}>{item.in_use?'当前正在使用':'已保存'} / {item.document.workflow.steps.length} 个步骤 / 第 {item.document.revision} 版</option>)}</Choice></Field><p>原来的版本和检查报告会保留。</p><Button kind="primary" onClick={inspectExisting}>核对这份操作</Button></>:<p>还没有保存过流程。请使用操作录制，或手动填写接口。</p>}</>}
                    {origin==='recording'&&<><h3>将录制中的操作带入这里</h3><Field label="选择操作录制"><Choice value={recordingId} onValueChange={selectedValue=>setRecordingId(selectedValue)}><option value="">选择已确认的录制</option>{context.recordings.filter(item=>item.action_id===actionId).map(item=><option key={item.recording_id} value={item.recording_id}>{item.label} / {new Date(item.created_at_us/1000).toLocaleString()}</option>)}</Choice></Field><p>还没有录制时，返回操作准备，在应用中实际操作一次。</p><Button kind="primary" busy={busy} disabled={!recordingId} onClick={()=>void act(async()=>{const value=await api.recording(projectId,recordingId);if(!loadSteps(value.steps,value.target_step_id))return;setResource(value.actual_resource_id);setProvenance('RECORDING');setPhase(1)})}>使用这次录制</Button></>}
                    {origin==='openapi'&&<><h3>从接口文档选择要执行的接口</h3><p>支持 OpenAPI 3.0 / 3.1 的 JSON 文件。这里只读取文档，不发送请求。</p><label className="jj-button jj-file-button">选择接口文档<input type="file" accept="application/json,.json" disabled={busy} onChange={event=>{const file=event.target.files?.[0];if(file)void act(async()=>{if(file.size>1048576)throw new Error('接口文档不能超过 1 MiB');setCandidates(await api.openapi(projectId,await file.text()));dirty();setProvenance('OPENAPI')})}}/></label>{candidates.length>0&&<Field label="文档中的接口"><Choice value="" onValueChange={selectedValue=>{const candidate=candidates[Number(selectedValue)];if(candidate){update({...step,method:candidate.method,path:candidate.path,parameters:candidate.fields.map(name=>({...newParameter('JSON_BODY'),name}))});setPhase(1)}}}><option value="" disabled>选择一个接口继续</option>{candidates.map((item,index)=><option key={index} value={index}>{item.label} / {item.method} {item.path}</option>)}</Choice></Field>}</>}
                    {origin==='manual'&&<><h3>填写应用已有的接口</h3><p>需要知道接口路径和参数。可以加入准备步骤，并设置检查后的数据恢复。</p><Button kind="primary" onClick={()=>{setProvenance('MANUAL');dirty();setPhase(1)}}>开始填写</Button></>}
                    </div>
                </div>
            </section>}
            {phase===1&&<section className="jj-flow-participants" key="participants"><header><h2>这次由谁操作哪份数据</h2><p>选择一次正常操作的账号和数据，检查时会按权限规则替换操作人。</p></header><div className="jj-flow-context"><Field label="用于准备操作的账号"><Choice value={subjectId??''} onValueChange={selectedValue=>{dirty();setSubject(selectedValue)}}>{accounts.map(item=><option key={item.identity_id} value={item.identity_id}>{item.label}</option>)}</Choice></Field><Field label="这份数据属于谁"><Choice value={ownerId??''} onValueChange={selectedValue=>{dirty();setOwner(selectedValue)}}>{accounts.map(item=><option key={item.identity_id} value={item.identity_id}>{item.label}</option>)}</Choice></Field><Field label="用于测试的数据编号"><input placeholder="填写应用中已有的数据编号" value={resource} onChange={event=>{dirty();setResource(event.target.value)}}/></Field></div>{!participantsReady&&<Notice tone="caution">请先登录本次操作所需的账号。已保存的流程会保留。<Button kind="quiet" onClick={()=>go('/preparation?identities=1',projectId)}>准备账号</Button></Notice>}</section>}
            {phase===2&&<section className="jj-flow-execution" key="execution">
                <header className="jj-flow-section-heading"><h2>设置执行请求</h2><p>先填写要检查的请求。需要提前准备数据时，再添加步骤。</p></header>
                <div className="jj-flow-editor">
                    <aside className="jj-flow-step-index"><h3>执行顺序</h3>
                        <IndexSelection as="nav" label="操作步骤" identity={String(selected)}>{steps.map((item,index)=><button className="jj-step-select jj-index-item" key={item.id} onClick={()=>setSelected(index)} aria-current={selected===index?'step':undefined}><span>{index+1}</span><div><strong>{item.id===target?'受检请求':'准备请求'}</strong><small title={item.method+' '+item.path}>{item.method} {item.path}</small></div></button>)}</IndexSelection>
                        <div className="jj-flow-step-tools"><Button kind="quiet" icon={<PlusOutlined aria-hidden="true"/>} disabled={steps.length>=32} onClick={()=>{dirty();setSteps([...steps,blank(steps.length+1)]);setSelected(steps.length)}}>添加步骤</Button><Button kind="quiet" disabled={steps.some(item=>item.id==='csrf_setup')} onClick={()=>setCsrfOpen(true)}>准备动态防伪参数</Button></div>
                    </aside>
                    <section key={step.id} className="jj-flow-step" aria-label={'第 '+(selected+1)+' 步请求'}>
                        <header><h3>第 {selected+1} 步</h3>{target===step.id?<Badge tone="accent">受检请求</Badge>:<Button kind="quiet" onClick={()=>{dirty();setTarget(step.id)}}>设为受检请求</Button>}</header>
                        <div className="jj-flow-request"><Field label="请求方式"><Choice value={step.method} onValueChange={selectedValue=>update({...step,method:selectedValue})}>{['GET','POST','PUT','PATCH','DELETE'].map(method=><option key={method}>{method}</option>)}</Choice></Field><Field label="接口路径" hint="用 {case_resource_id} 代表每次检查的数据编号。"><input value={step.path} onChange={event=>update({...step,path:event.target.value})}/></Field></div>
                        <FlowRequestInputs step={step} previous={steps.slice(0,selected)} busy={busy} onChange={update}/>
                        {steps.length>1&&<footer className="jj-flow-step-actions"><Button kind="quiet" disabled={step.id===target} onClick={()=>{dirty();setSteps(steps.filter((_,index)=>index!==selected));setSelected(0)}}>移除此步骤</Button></footer>}
                    </section>
                </div>
            </section>}
            {needsOutcome&&phase===3&&<section className="jj-flow-outcomes" key="outcomes">
                <header className="jj-flow-section-heading"><h2>{action?.state_changing?'核对结果与恢复安排':'设置结果核对依据'}</h2><p>{action?.state_changing?'请求已经填写。现在确定如何比较返回结果，以及检查后如何恢复数据。':'请求已经填写。选择需要比较的业务结果，再配置独立只读查询。'}</p></header>
                {action&&<EntityEvidenceEditor effects={action.effects} value={entityEvidence} onChange={items=>{dirty();setEntityEvidence(items)}}/>}
                {action?.state_changing&&<section className="jj-flow-resource-result"><h3>新建数据的编号</h3><label className="jj-checkbox"><input type="checkbox" checked={Boolean(createdPath)} onChange={event=>{dirty();setCreatedPath(event.target.checked?'$.id':'')}}/><span>受检请求会新建一份数据</span></label>{createdPath&&<Field label="返回结果中，新数据的编号位于"><input value={createdPath} onChange={event=>{dirty();setCreatedPath(event.target.value)}}/></Field>}</section>}
                {action?.state_changing&&<section className="jj-flow-recovery"><header><h3>检查后恢复原状</h3><p className="jj-small jj-muted">由数据所有者执行应用提供的恢复接口。</p></header><div className="jj-flow-request"><Field label="恢复请求方式"><Choice value={restoreMethod} onValueChange={selectedValue=>{dirty();setRestoreMethod(selectedValue)}}>{['POST','PATCH','PUT','DELETE'].map(method=><option key={method}>{method}</option>)}</Choice></Field><Field label="恢复接口路径"><input value={recovery} onChange={event=>{dirty();setRecovery(event.target.value)}}/></Field></div><Field label="恢复时发送的数据（JSON）"><textarea rows={3} value={restoreBody} onChange={event=>{dirty();setRestoreBody(event.target.value)}}/></Field></section>}
            </section>}
            {phase===reviewPhase&&<div className="jj-flow-review" data-saved={Boolean(saved)}>
                {saved&&<FlowTrialPanel key={saved.id+'@'+saved.revision} projectId={projectId} flow={saved} accounts={accounts} initialTrialId={initialTrialId} onInteractionChange={setTrialInteracting} onResume={document=>{if(load(document))setPhase(2)}}/>}
                <aside className="jj-flow-confirm" key="confirm" aria-label="场景核对"><header><h2>{adopted?'操作已准备好':'场景核对'}</h2>{saved&&<Badge tone={adopted?'positive':'accent'}>{adopted?'已用于检查':'已保存'}</Badge>}</header>
                    <p className="jj-small jj-muted">{adopted?'后续检查使用这份场景，历史报告保持原样。':'确认使用后，后续检查将使用这份保存的场景。'}</p>
                    <dl className="jj-flow-review-facts"><div><dt>业务操作</dt><dd>{action?.label}</dd></div><div><dt>准备账号</dt><dd>{identities.find(item=>item.identity_id===subjectId)?.label}</dd></div><div><dt>测试数据</dt><dd>{resource}<small>所有者：{identities.find(item=>item.identity_id===ownerId)?.label}</small></dd></div><div><dt>执行步骤</dt><dd>共 {steps.length} 步，第 {steps.findIndex(item=>item.id===target)+1} 步受检</dd></div><div><dt>检查后恢复</dt><dd>{action?.state_changing?recovery:'只读操作，无需恢复'}</dd></div>{entityEvidence.length>0&&<div><dt>结果判断查询</dt><dd>{entityEvidence.map(item=><code key={item.effect_id}>{item.query.request.path as string}</code>)}</dd></div>}</dl>
                    <div className="jj-flow-review-actions"><Button kind="quiet" disabled={busy||trialInteracting} onClick={()=>setPhase(1)}>修改设置</Button>{adopted?<Button kind={trialInteracting?'default':'primary'} disabled={trialInteracting} onClick={onBack}>返回检查准备</Button>:saved?<Button kind={trialInteracting?'default':'primary'} disabled={trialInteracting} busy={busy} onClick={()=>void act(async()=>{await api.adopt(projectId,saved);setAdopted(true);state.reload()})}>确认用于检查</Button>:<Button kind="primary" busy={busy} disabled={!action||!subjectId||!ownerId||!resource} onClick={saveFlow}>保存操作设置</Button>}</div>
                </aside>
            </div>}

            </div>
            {phase>0&&phase<reviewPhase&&<footer><Button disabled={busy} onClick={()=>setPhase(phase-1)}>上一步</Button><Button kind="primary" disabled={busy||phase===1&&(!participantsReady||!resource)||phase===3&&Boolean(action?.state_changing&&!recovery)} onClick={()=>setPhase(phase+1)}>{phase===1?'下一步：设置执行步骤':phase===2&&needsOutcome?'下一步：'+outcomeLabel:'下一步：核对操作'}</Button></footer>}
        </section>
        {csrfOpen&&<Dialog title="准备动态防伪参数" onClose={()=>setCsrfOpen(false)} actions={<Button kind="primary" onClick={()=>{
            dirty();const targetStep=steps.find(item=>item.id===target)!;
            const setup:EditableStep={id:'csrf_setup',method:'GET',path:csrfPath,parameters:[],base:{id:'csrf_setup',purpose:'SETUP',identity_id:'CASE_SUBJECT',request_template:{method:'GET',path:csrfPath,body:{kind:'EMPTY'},response_extractors:[{extractor_id:'csrf_value',kind:'JSON_PATH',json_path:csrfField,secret:true}]},classifier:{accepted:[{kind:'STATUS_IN',statuses:[200]}],denied:[]},depends_on_step_ids:[]}};
            const updated={...targetStep,parameters:[...targetStep.parameters,{...newParameter('HEADER'),slotId:'csrf_value',name:csrfHeader,source:'PRIOR_STEP_JSON_PATH' as const,producer:'csrf_setup',path:csrfField,secret:true}]};
            setSteps([setup,...steps.map(item=>item.id===target?updated:item)]);setSelected(selected+1);setCsrfOpen(false)
        }}>加入准备步骤</Button>}><p className="jj-small jj-muted">在受检请求前以同一身份读取参数，再注入请求头。参数仅在本次执行期间保留。</p><div className="jj-flow-token-fields"><Field label="参数读取路径"><input value={csrfPath} onChange={event=>setCsrfPath(event.target.value)}/></Field><Field label="JSON 参数位置"><input value={csrfField} onChange={event=>setCsrfField(event.target.value)}/></Field><Field label="注入的请求头"><input value={csrfHeader} onChange={event=>setCsrfHeader(event.target.value)}/></Field></div></Dialog>}

    </>
}
