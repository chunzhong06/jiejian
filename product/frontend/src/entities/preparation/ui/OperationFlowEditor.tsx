import {TaskSurface} from '../../../shared/ui/TaskSurface'
import {WorkflowSteps} from '../../../shared/ui/WorkflowSteps'
import {useWorkflow} from '../../../shared/lib/workflow'
import {IndexActions,IndexSelection} from '../../../shared/ui/IndexSelection'
import './operation-flow.css'
import {EntityEvidenceEditor} from './EntityEvidenceEditor'
import {FlowRequestInputs} from './FlowRequestInputs'
import {FlowTrialPanel} from './FlowTrialPanel'
import {FlowCandidateReview,flowDraftKey} from './FlowCandidateReview'
import {editorDraft,rememberEditorDraft,requestCollaboration,useHandoffContext} from '../../runtime/model/handoff'
import {compileSteps,decodeSteps,newParameter,type EditableStep} from './flowInputs'
import type {ApiSourceReference} from '../api/operationFlows'
import {Choice} from '../../../shared/ui/Choice'
import {FilePicker} from '../../../shared/ui/FilePicker'
import {useEffect,useId,useReducer,useState,type SetStateAction} from 'react'
import {flowDraftReducer,type FlowEditorDraft,type FlowDraftAction} from './flowDraft'
import {useCommand} from '../../../shared/lib/operations'
import {Tabs} from '../../../shared/ui/Tabs'
import {Dialog} from '../../../shared/ui/Dialog'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import PlusOutlined from '@ant-design/icons/PlusOutlined'
import {operationFlowsApi as api,type FlowStep,type OperationFlow,type ApiCandidate} from '../api/operationFlows'
import {testIdentitiesApi} from '../api/testIdentities'
import type {SourceRequest} from '../../application/api/workbench'
import {useRead} from '../../../shared/lib/useRead'
import {go,readRoute} from '../../../shared/lib/navigation'
import {Button} from '../../../shared/ui/actions'
import {Field,Heading} from '../../../shared/ui/layout'
import {PageError, Badge,ErrorNote,Loading,Notice} from '../../../shared/ui/feedback'

const blank=(index:number):EditableStep=>({id:'step_'+index+'_'+crypto.randomUUID().slice(0,8),method:'GET',path:'/',parameters:[]})
export function OperationFlowEditor({projectId,actionId,onBack,backLabel,initialRequest,initialSource,initialFlow,initialTrialId,candidateFlow}:{projectId:string;actionId:string;onBack:()=>void;backLabel?:string;initialRequest?:SourceRequest;initialSource?:ApiSourceReference;initialFlow?:OperationFlow;initialTrialId?:string;candidateFlow?:OperationFlow}) {
    const workflow=useWorkflow(),workRoute=workflow?.route??readRoute();
    const [restored]=useState(()=>initialFlow?undefined:editorDraft<FlowEditorDraft>(flowDraftKey(projectId,actionId),projectId))
    const [candidateReviewed,setCandidateReviewed]=useState(false)
    // 入口确定工作方式；新建流程保存后不会突然切换导航结构。
    const [maintenance,setMaintenance]=useState(Boolean(initialFlow||restored?.saved||restored?.maintenance))
    const state=useRead('operation-flow:'+projectId,async(signal)=>{const [context,identities]=await Promise.all([api.context(projectId,signal),testIdentitiesApi.list(projectId,signal)]);return{context,identities}})
    const originPanel=useId()
    const [draft,dispatch]=useReducer(flowDraftReducer,undefined,():FlowEditorDraft=>restored??{
        phase:initialRequest?1:0,origin:'existing',sourceRequest:initialSource,entityEvidence:[],
        flowId:'ofl_'+crypto.randomUUID().replaceAll('-',''),revision:1,
        steps:[{id:'step_1',method:initialRequest?.method??'GET',path:initialRequest?.path??'/',
            parameters:(initialRequest?.parameters??[]).filter(item=>item.location!=='HEADER'||!['authorization','cookie','host','content-length','connection','transfer-encoding'].includes(item.name.toLowerCase())).map(item=>({...newParameter(item.location==='BODY'?'JSON_BODY':item.location),name:item.name,source:item.sensitive?'PRIOR_STEP_JSON_PATH':'LITERAL',secret:item.sensitive}))}],
        selected:0,target:'step_1',createdPath:'',subject:'',owner:'',resource:'',recovery:'',restoreMethod:'POST',restoreBody:'{}',provenance:'MANUAL',recordingId:''
    })
    const {phase,origin,sourceRequest,entityEvidence,flowId,revision,steps,selected,target,createdPath,subject,owner,resource,recovery,restoreMethod,restoreBody,provenance,recordingId,saved}=draft
    const field=<Key extends keyof FlowEditorDraft>(key:Key)=>(value:SetStateAction<FlowEditorDraft[Key]>)=>dispatch({type:'field',key,value} as FlowDraftAction)
    const setPhase=field('phase'),setOrigin=field('origin'),setEntityEvidence=field('entityEvidence')
    const setSteps=field('steps'),setSelected=field('selected'),setTarget=field('target'),setCreatedPath=field('createdPath')
    const setSubject=field('subject'),setOwner=field('owner'),setResource=field('resource'),setRecovery=field('recovery'),setRestoreMethod=field('restoreMethod'),setRestoreBody=field('restoreBody')
    const setRecordingId=field('recordingId'),setProvenance=field('provenance')
    const [existingId,setExistingId]=useState(''),[candidates,setCandidates]=useState<ApiCandidate[]>([]),[apiFile,setApiFile]=useState<File>()
    const [csrfPath,setCsrfPath]=useState('/api/csrf'),[csrfField,setCsrfField]=useState('$.csrf'),[csrfHeader,setCsrfHeader]=useState('X-CSRF-Token')
    const [adopted,setAdopted]=useState(false),[trialInteracting,setTrialInteracting]=useState(false)
    const {busy,error,run:act,report:setError}=useCommand('flow:'+projectId+':'+actionId)
    const [csrfOpen,setCsrfOpen]=useState(false)
    const [task,setTask]=useState<'edit'|'trial'|'history'>(()=>initialTrialId?'history':'edit'),[adoptionOpen,setAdoptionOpen]=useState(false)
    const action=state.data?.context.actions.find(item=>item.action_id===actionId)
    // 结果查询或恢复确有配置时才增加一个阶段；普通只读请求直接进入核对。
    const needsOutcome=Boolean(action?.state_changing||action?.effects.some(item=>item.kind==='DATA_DISCLOSURE'))
    const reviewPhase=needsOutcome?4:3
    const outcomeLabel=action?.state_changing?'结果与恢复':'结果核对'
    const latestRevision=(id:string,fallback=0)=>Math.max(fallback,...(state.data?.context.flows.filter(item=>item.document.id===id).map(item=>item.document.revision)??[]))
    // 已保存的内容变更形成下一修订；试运行或导航不隐式采用它。
    const dirty=()=>{dispatch({type:'dirty',latestRevision:saved?latestRevision(saved.id,saved.revision):0});setAdopted(false)}
    const update=(next:EditableStep)=>{dirty();setSteps(steps.map((step,index)=>index===selected?next:step))}
    const loadSteps=(items:FlowStep[],targetId:string)=>{
        try{
            const decoded=decodeSteps(items)
            const created=(items.find(item=>item.id===targetId)?.request_template.response_extractors?.find(item=>item.extractor_id==='created_resource_id')?.json_path as string)??''
            dispatch({type:'steps',steps:decoded,target:targetId,createdPath:created,latestRevision:saved?latestRevision(saved.id,saved.revision):0})
            setAdopted(false)
            return true
        }catch(error){setError(error);return false}
    }
    const load=(document:OperationFlow,options:{saved?:boolean;phase?:number;revision?:number;steps?:EditableStep[];restoreBody?:string}={})=>{
        try{
            const decoded=options.steps??decodeSteps(document.workflow.steps)
            dispatch({type:'load',document,steps:decoded,revision:options.revision??latestRevision(document.id,document.revision)+1,
                phase:options.phase??phase,saved:options.saved??false,restoreBody:options.restoreBody})
            setAdopted(false)
            return true
        }catch(error){setError(error);return false}
    }
    useEffect(()=>{if(initialFlow&&state.data)load(initialFlow,{saved:true,revision:initialFlow.revision,phase:reviewPhase})},[initialFlow?.id,initialFlow?.revision,Boolean(state.data),reviewPhase])
    const effectiveIdentity=state.data?.identities.find(item=>item.auth_method!==null)?.identity_id??''
    // 未保存修改会清除 saved，但维护模式仍须随草稿回到原分类。
    const snapshot:FlowEditorDraft={...draft,maintenance,subject:subject||effectiveIdentity,owner:owner||effectiveIdentity}
    useEffect(()=>{if(!adopted)rememberEditorDraft(flowDraftKey(projectId,actionId),snapshot,projectId)},[draft,maintenance,effectiveIdentity,adopted,projectId,actionId])
    const safePath=(path:string)=>{const shape=path.split(/[?#]/)[0];return /^\/[A-Za-z0-9_./{}~:@%+\-]*$/.test(shape)?shape:null}
    useHandoffContext(action?{projectId,label:action.label+' · 接口流程草稿',references:{...workflow?.references,action_id:actionId,flow_id:flowId,revision:String(revision),return_to:workflow?.origin??'/testing?action_id='+actionId+'&resume_draft=1'},editor:{kind:'FLOW',flow_id:flowId,revision:saved?Math.max(saved.revision,...state.data!.context.flows.filter(item=>item.document.id===flowId).map(item=>item.document.revision))+1:revision,action_id:actionId,action_revision:action.revision,subject_identity_id:snapshot.subject||null,owner_identity_id:snapshot.owner||null,target_step_id:target,steps:steps.map(item=>({id:item.id,method:item.method,path:safePath(item.path),parameters:item.parameters.map(parameter=>({location:parameter.location,name:parameter.name,source:parameter.source,secret:parameter.secret}))})),recovery_path:recovery?safePath(recovery):null,evidence_effect_ids:entityEvidence.map(item=>item.effect_id),evidence_queries:entityEvidence.map(item=>({effect_id:item.effect_id,request_path:safePath(String(item.query.request.path??'')),resource_path:item.query.resource_path,owner_path:item.query.owner_path,data_path:item.query.data_path}))}}:undefined)
    if(state.loading)return <Loading page/>
    if(!state.data)return <PageError title="接口流程" error={state.error}/>
    if(!action)return <><div className="jj-back-link"><Button kind="quiet" onClick={onBack}>{backLabel??'返回检查准备'}</Button></div><PageError title="接口流程" error={new Error('指定的业务操作已不在当前应用中，请返回原位置重新选择。')}/></>
    const {context,identities}=state.data,step=steps[selected]
    const accounts=identities.filter(item=>item.auth_method!==null)
    const subjectId=subject||accounts[0]?.identity_id,ownerId=owner||accounts[0]?.identity_id
    const participantsReady=accounts.some(item=>item.identity_id===subjectId)&&accounts.some(item=>item.identity_id===ownerId)
    const compile=()=>compileSteps(steps,target,createdPath)
    const matching=context.flows.filter(item=>item.document.business_action_id===actionId)
    const existing=matching.find(item=>item.document.id+'@'+item.document.revision===existingId)??matching.find(item=>item.in_use)??matching[0]
    const inspectExisting=()=>{if(load(existing!.document,{saved:existing!.configuration_current,phase:reviewPhase,
        ...(existing!.configuration_current?{revision:existing!.document.revision}:{})}))setMaintenance(true)}
    const phaseLabels=['选择起点','账号与测试数据','执行请求',...(needsOutcome?[outcomeLabel]:[]),'核对并使用']
    const saveFlow=()=>void act(async()=>{
        const candidate=await api.candidate(projectId,{id:flowId,revision,business_action_id:actionId,action_revision:action!.revision,subject_test_identity_id:subjectId,resource_owner_test_identity_id:ownerId,source_fingerprint:context.source_fingerprint,entity_evidence:entityEvidence,source_request:sourceRequest,provenance,source_recording_id:provenance==='RECORDING'?recordingId:null,actual_resource_id:resource,target_step_id:target,steps:compile(),recovery:action!.state_changing?{method:restoreMethod,relative_path:recovery,json_body:JSON.parse(restoreBody)}:null})
        dispatch({type:'saved',document:await api.save(projectId,candidate)});state.reload()
    })
    return <>
      <div hidden={task!=='edit'}>
        <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={onBack}>{backLabel??"返回操作准备"}</Button></div>
        <Heading eyebrow={action?.label} title="接口流程" actions={<Button disabled={busy||trialInteracting} onClick={()=>requestCollaboration(projectId,'SETUP','补全「'+(action?.label??'当前操作')+'」的接口流程，整理执行步骤、结果核对与恢复安排。')}>请 Agent 补全</Button>}/>
        {Boolean(error)&&<ErrorNote error={error}/>}
        {trialInteracting&&<Notice tone="caution">试运行仍有待处理的执行或确认。<Button kind="quiet" onClick={()=>setTask('history')}>查看原试运行</Button></Notice>}
        {candidateFlow&&!candidateReviewed&&<FlowCandidateReview candidate={candidateFlow} previous={restored} accounts={accounts} onKeep={()=>setCandidateReviewed(true)} onApply={preserve=>{
            const values=preserve?steps:[]
            let merged:EditableStep[]
            try{merged=decodeSteps(candidateFlow.workflow.steps)}catch(error){setError(error);return}
            merged=merged.map(item=>({...item,parameters:item.parameters.map(parameter=>{
                const previous=values.find(step=>step.id===item.id)?.parameters.find(old=>old.name===parameter.name&&old.location===parameter.location&&old.source==='LITERAL'&&parameter.source==='LITERAL')
                return previous?{...parameter,value:previous.value,json:previous.json}:parameter
            })}))
            const preserveRecovery=preserve&&recovery===candidateFlow.recovery?.relative_path&&restoreMethod===candidateFlow.recovery?.method
            const changed=JSON.stringify(merged)!==JSON.stringify(decodeSteps(candidateFlow.workflow.steps))||preserveRecovery&&restoreBody!==JSON.stringify(candidateFlow.recovery?.json_body??{},null,2)
            load(candidateFlow,{steps:merged,saved:!changed,phase:reviewPhase,
                revision:changed?latestRevision(candidateFlow.id,candidateFlow.revision)+1:candidateFlow.revision,
                ...(preserveRecovery?{restoreBody}:{})})
            setMaintenance(true);setCandidateReviewed(true)
        }}/>}
        <section className="jj-flow-workspace" data-mode={maintenance?'maintain':'create'} data-phase={phase} data-stages={phaseLabels.length}>
            {maintenance?<fieldset className="jj-flow-maintenance-nav" disabled={busy||trialInteracting}>
                <Tabs label="流程维护" value={String(phase)} onValueChange={value=>setPhase(Number(value))} items={[{value:'1',label:'账号与数据'},{value:'2',label:'执行请求'},...(needsOutcome?[{value:'3',label:outcomeLabel}]:[]),{value:String(reviewPhase),label:'保存与使用'}]} panelId="flow-maintenance-panel" idPrefix="flow-maintenance"/>
                <p className="jj-small jj-muted">第 {revision} 修订 · {saved?'已保存，可按需修改或试运行':'有未保存修改，试运行前请先保存'}</p>
            </fieldset>:<>
            <WorkflowSteps className="jj-flow-phases" label="操作设置进度" steps={phaseLabels.map((label,index)=>({id:index===reviewPhase?'review':['origin','participants','requests','outcome'][index],label,state:phase===index?'current' as const:phase>index?'complete' as const:'pending' as const,disabled:index>phase||busy||trialInteracting}))} onStepChange={id=>setPhase(id==='review'?reviewPhase:['origin','participants','requests','outcome'].indexOf(id))}/>
            </>}
            <div className="jj-flow-body" id={maintenance?'flow-maintenance-panel':undefined} role={maintenance?'tabpanel':undefined} aria-labelledby={maintenance?'flow-maintenance-'+phase:undefined}>
            {phase===0&&<section className="jj-flow-start" key="start"><header><h2>从已有操作开始</h2><p>优先使用真实录制。需要串联多个接口时，再补充执行步骤。</p></header>
                <div className="jj-flow-origins"><Tabs label="流程的来源" value={origin} items={[{value:'existing',label:'沿用已有流程'},{value:'recording',label:'使用操作录制'},{value:'openapi',label:'导入接口文档'},{value:'manual',label:'手动填写接口'}]} idPrefix={originPanel} panelId={originPanel+'-content'} onValueChange={value=>setOrigin(value as typeof origin)}/>
                    <div className="jj-flow-origin-content" key={origin} role="tabpanel" id={originPanel+'-content'} aria-labelledby={originPanel+'-'+origin}>
                    {origin==='existing'&&<><h3>继续修改已保存的流程</h3>{matching.length?<><Field label="选择流程"><Choice value={existing?existing.document.id+'@'+existing.document.revision:''} onValueChange={selectedValue=>setExistingId(selectedValue)}>{matching.map(item=><option key={item.document.id+'@'+item.document.revision} value={item.document.id+'@'+item.document.revision}>{item.in_use?'当前正在使用':'已保存'} / {item.document.workflow.steps.length} 个步骤 / 第 {item.document.revision} 版</option>)}</Choice></Field><p>原来的版本和检查报告会保留。</p><Button kind="primary" onClick={inspectExisting}>核对这份操作</Button></>:<p>还没有保存过流程。请使用操作录制，或手动填写接口。</p>}</>}
                    {origin==='recording'&&<><h3>将录制中的操作带入这里</h3><Field label="选择操作录制"><Choice value={recordingId} onValueChange={selectedValue=>setRecordingId(selectedValue)}><option value="">选择已确认的录制</option>{context.recordings.filter(item=>item.action_id===actionId).map(item=><option key={item.recording_id} value={item.recording_id}>{item.label} / {new Date(item.created_at_us/1000).toLocaleString()}</option>)}</Choice></Field><p>还没有录制时，返回操作准备，在应用中实际操作一次。</p><Button kind="primary" busy={busy} disabled={!recordingId} onClick={()=>void act(async()=>{const value=await api.recording(projectId,recordingId);if(!loadSteps(value.steps,value.target_step_id))return;setResource(value.actual_resource_id);setProvenance('RECORDING');setPhase(1)})}>使用这次录制</Button></>}
                    {origin==='openapi'&&<><h3>从接口文档选择要执行的接口</h3><p>支持 OpenAPI 3.0 / 3.1 的 JSON 文件。这里只读取文档，不发送请求。</p><Field label="接口文档"><FilePicker label="接口文档" file={apiFile} accept="application/json,.json" formats="OpenAPI JSON" maxBytes={1048576} disabled={busy} onFileChange={next=>act(async()=>{const items=next?await api.openapi(projectId,await next.text()):[];setCandidates(items);setApiFile(next);if(next){dirty();setProvenance('OPENAPI')}})}/></Field>{candidates.length>0&&<Field label="文档中的接口"><Choice value="" onValueChange={selectedValue=>{const candidate=candidates[Number(selectedValue)];if(candidate){update({...step,method:candidate.method,path:candidate.path,parameters:candidate.fields.map(name=>({...newParameter('JSON_BODY'),name}))});setPhase(1)}}}><option value="" disabled>选择一个接口继续</option>{candidates.map((item,index)=><option key={index} value={index}>{item.label} / {item.method} {item.path}</option>)}</Choice></Field>}</>}
                    {origin==='manual'&&<><h3>填写应用已有的接口</h3><p>需要知道接口路径和参数。可以加入准备步骤，并设置检查后的数据恢复。</p><Button kind="primary" onClick={()=>{setProvenance('MANUAL');dirty();setPhase(1)}}>开始填写</Button></>}
                    </div>
                </div>
            </section>}
            {phase===1&&<section className="jj-flow-participants" key="participants"><header><h2>这次由谁操作哪份数据</h2><p>选择一次正常操作的账号和数据，检查时会按权限规则替换操作人。</p></header><div className="jj-flow-context"><Field label="用于准备操作的账号"><Choice value={subjectId??''} onValueChange={selectedValue=>{dirty();setSubject(selectedValue)}}>{accounts.map(item=><option key={item.identity_id} value={item.identity_id}>{item.label}</option>)}</Choice></Field><Field label="这份数据属于谁"><Choice value={ownerId??''} onValueChange={selectedValue=>{dirty();setOwner(selectedValue)}}>{accounts.map(item=><option key={item.identity_id} value={item.identity_id}>{item.label}</option>)}</Choice></Field><Field label="用于测试的数据编号"><input placeholder="填写应用中已有的数据编号" value={resource} onChange={event=>{dirty();setResource(event.target.value)}}/></Field></div>{!participantsReady&&<Notice tone="caution">请先登录本次操作所需的账号。已保存的流程会保留。<Button kind="quiet" onClick={()=>(workflow?.open??go)('/preparation?'+new URLSearchParams({identities:'1',action_id:actionId,return_to:workRoute.path+'?'+new URLSearchParams({...Object.fromEntries(workRoute.query),resume_draft:'1'})}),projectId)}>准备账号</Button></Notice>}</section>}
            {phase===2&&<section className="jj-flow-execution" key="execution">
                <header className="jj-flow-section-heading"><h2>设置执行请求</h2><p>先填写要检查的请求。需要提前准备数据时，再添加步骤。</p></header>
                <div className="jj-flow-editor">
                    <aside className="jj-flow-step-index"><h3 className="jj-title-caption">执行顺序</h3>
                        <IndexSelection as="nav" label="操作步骤" identity={String(selected)}>{steps.map((item,index)=><button className="jj-step-select jj-index-item" key={item.id} onClick={()=>setSelected(index)} aria-current={selected===index?'step':undefined}><span>{index+1}</span><div><strong>{item.id===target?'受检请求':'准备请求'}</strong><small title={item.method+' '+item.path}>{item.method} {item.path}</small></div></button>)}</IndexSelection>
                        <IndexActions><Button kind="quiet" icon={<PlusOutlined aria-hidden="true"/>} disabled={steps.length>=32} onClick={()=>{dirty();setSteps([...steps,blank(steps.length+1)]);setSelected(steps.length)}}>添加步骤</Button><Button kind="quiet" disabled={steps.some(item=>item.id==='csrf_setup')} onClick={()=>setCsrfOpen(true)}>准备动态防伪参数</Button></IndexActions>
                    </aside>
                    <section key={step.id} className="jj-flow-step" aria-label={'第 '+(selected+1)+' 步请求'}>
                        <header><div className="jj-object-line"><h3>第 {selected+1} 步</h3>{target===step.id&&<Badge tone="accent">受检请求</Badge>}</div>{target!==step.id&&<Button kind="quiet" onClick={()=>{dirty();setTarget(step.id)}}>设为受检请求</Button>}</header>
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

                <section className="jj-flow-confirm" key="confirm" aria-label="核对接口流程"><header><h2>{adopted?'操作已准备好':'核对接口流程'}</h2>{saved&&<Badge tone={adopted?'positive':'accent'}>{adopted?'已用于检查':'已保存'}</Badge>}</header>
                    <p className="jj-small jj-muted">{adopted?'后续检查会使用这份接口流程，已有报告保留。':'确认用于检查后，后续检查会使用这份已保存的接口流程。'}</p>
                    <dl className="jj-facts jj-flow-review-facts" data-layout="columns"><div><dt>业务操作</dt><dd>{action?.label}</dd></div><div><dt>准备账号</dt><dd>{identities.find(item=>item.identity_id===subjectId)?.label}</dd></div><div><dt>测试数据</dt><dd>{resource}<small>所有者：{identities.find(item=>item.identity_id===ownerId)?.label}</small></dd></div><div><dt>执行步骤</dt><dd>共 {steps.length} 步，第 {steps.findIndex(item=>item.id===target)+1} 步受检</dd></div><div><dt>检查后恢复</dt><dd>{action?.state_changing?recovery:'只读操作，无需恢复'}</dd></div>{entityEvidence.length>0&&<div><dt>结果判断查询</dt><dd>{entityEvidence.map(item=><code key={item.effect_id}>{item.query.request.path as string}</code>)}</dd></div>}</dl>
                    <div className="jj-flow-review-actions">{saved&&<><Button kind="quiet" onClick={()=>setTask('history')}>试运行记录</Button><Button onClick={()=>setTask('trial')}>试运行已保存修订</Button></>}<Button kind="quiet" disabled={busy||trialInteracting} onClick={()=>setPhase(1)}>修改设置</Button>{adopted?<Button kind={trialInteracting?'default':'primary'} disabled={trialInteracting} onClick={onBack}>{workflow?'继续本次检查':'返回检查准备'}</Button>:saved?<Button kind={trialInteracting?'default':'primary'} disabled={trialInteracting} busy={busy} onClick={()=>setAdoptionOpen(true)}>用于后续检查</Button>:<Button kind="primary" busy={busy} disabled={!action||!subjectId||!ownerId||!resource} onClick={saveFlow}>保存操作设置</Button>}</div>
                </section>
            </div>}

            </div>
            {maintenance&&phase<reviewPhase?<footer className="jj-flow-maintenance-actions"><p className="jj-small jj-muted">{saved?'当前修订已保存；正式检查前仍需确认使用这份流程。':'未保存内容保留在当前草稿中。'}</p><div className="jj-inline-actions"><Button kind="quiet" disabled={busy||trialInteracting} onClick={()=>setPhase(reviewPhase)}>保存与使用</Button><Button kind="primary" busy={busy} disabled={Boolean(saved)||!action||!participantsReady||!resource||Boolean(action.state_changing&&!recovery)} onClick={saveFlow}>保存修改</Button></div></footer>:phase>0&&phase<reviewPhase&&<footer><Button disabled={busy} onClick={()=>setPhase(phase-1)}>上一步</Button><Button kind="primary" disabled={busy||phase===1&&(!participantsReady||!resource)||phase===3&&Boolean(action?.state_changing&&!recovery)} onClick={()=>setPhase(phase+1)}>{phase===1?'下一步：设置执行步骤':phase===2&&needsOutcome?'下一步：'+outcomeLabel:'下一步：核对操作'}</Button></footer>}
        </section>
      </div>
      {saved&&<TaskSurface active={task!=='edit'} title={task==='history'?'试运行记录':'试运行接口流程'} context={<>{action.label}{task==='trial'&&<> · 第 {saved.revision} 修订</>}</>} description={task==='history'?'保留每次实际使用的账号、资源和请求反馈。可读取原修订，或据此继续编辑。':'先核对本次账号、资源和请求，再确认执行。试运行形成请求与恢复反馈。'} onBack={()=>setTask('edit')} backLabel="返回流程编辑"><FlowTrialPanel key={saved.id+'@'+saved.revision} projectId={projectId} flow={saved} accounts={accounts} showHeading={false} onViewChange={view=>{if(task!=='edit')setTask(view==='history'?'history':'trial')}} mode={task==='edit'?undefined:task==='history'?'history':'current'} initialTrialId={initialTrialId} onInteractionChange={setTrialInteracting} onResume={document=>{if(load(document)){setPhase(2);setTask('edit')}}}/></TaskSurface>}
      {adoptionOpen&&saved&&<Dialog title="将这份流程用于后续检查" onClose={()=>setAdoptionOpen(false)} closeDisabled={busy} actions={<><Button disabled={busy} onClick={()=>setAdoptionOpen(false)}>返回编辑</Button><Button kind="primary" busy={busy} onClick={()=>void act(async()=>{await api.adopt(projectId,saved);rememberEditorDraft(flowDraftKey(projectId,actionId),undefined);setAdopted(true);setAdoptionOpen(false);state.reload()})}>确认用于检查</Button></>}><p>「{action.label}」后续检查将使用第 {saved.revision} 修订。已有检查报告和旧修订保留；本次确认不会发送业务请求。</p><dl className="jj-facts" data-layout="columns"><div><dt>操作账号</dt><dd>{identities.find(item=>item.identity_id===saved.subject_test_identity_id)?.label}</dd></div><div><dt>测试资源</dt><dd>{saved.actual_resource_id}</dd></div><div><dt>执行请求</dt><dd>{saved.workflow.steps.length} 步</dd></div></dl></Dialog>}
        {csrfOpen&&<Dialog title="准备动态防伪参数" onClose={()=>setCsrfOpen(false)} actions={<Button kind="primary" onClick={()=>{
            dirty();const targetStep=steps.find(item=>item.id===target)!;
            const setup:EditableStep={id:'csrf_setup',method:'GET',path:csrfPath,parameters:[],base:{id:'csrf_setup',purpose:'SETUP',identity_id:'CASE_SUBJECT',request_template:{method:'GET',path:csrfPath,body:{kind:'EMPTY'},response_extractors:[{extractor_id:'csrf_value',kind:'JSON_PATH',json_path:csrfField,secret:true}]},classifier:{accepted:[{kind:'STATUS_IN',statuses:[200]}],denied:[]},depends_on_step_ids:[]}};
            const updated={...targetStep,parameters:[...targetStep.parameters,{...newParameter('HEADER'),slotId:'csrf_value',name:csrfHeader,source:'PRIOR_STEP_JSON_PATH' as const,producer:'csrf_setup',path:csrfField,secret:true}]};
            setSteps([setup,...steps.map(item=>item.id===target?updated:item)]);setSelected(selected+1);setCsrfOpen(false)
        }}>加入准备步骤</Button>}><p className="jj-small jj-muted">在受检请求前以同一身份读取参数，再注入请求头。参数仅在本次执行期间保留。</p><div className="jj-flow-token-fields"><Field label="参数读取路径"><input value={csrfPath} onChange={event=>setCsrfPath(event.target.value)}/></Field><Field label="JSON 参数位置"><input value={csrfField} onChange={event=>setCsrfField(event.target.value)}/></Field><Field label="注入的请求头"><input value={csrfHeader} onChange={event=>setCsrfHeader(event.target.value)}/></Field></div></Dialog>}

    </>
}
