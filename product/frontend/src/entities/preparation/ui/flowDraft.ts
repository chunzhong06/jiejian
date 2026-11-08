import type {OperationFlow,ApiSourceReference,EntityEvidence} from '../api/operationFlows'
import type {EditableStep} from './flowInputs'

export type FlowEditorDraft={phase:number;maintenance?:boolean;origin:'existing'|'recording'|'openapi'|'manual';sourceRequest?:ApiSourceReference;entityEvidence:EntityEvidence[];flowId:string;revision:number;steps:EditableStep[];selected:number;target:string;createdPath:string;subject:string;owner:string;resource:string;recovery:string;restoreMethod:string;restoreBody:string;provenance:OperationFlow['provenance'];recordingId:string;saved?:OperationFlow}

export type FlowDraftAction = {
  [Key in keyof FlowEditorDraft]-?: {type:'field';key:Key;value:FlowEditorDraft[Key]|((previous:FlowEditorDraft[Key])=>FlowEditorDraft[Key])}
}[keyof FlowEditorDraft] | {type:'dirty';latestRevision:number} |
  {type:'steps';steps:EditableStep[];target:string;createdPath:string;latestRevision:number} |
  {type:'load';document:OperationFlow;steps:EditableStep[];revision:number;phase:number;saved:boolean;restoreBody?:string} |
  {type:'saved';document:OperationFlow}

function dirty(state:FlowEditorDraft,latestRevision:number):FlowEditorDraft {
  return {...state,revision:state.saved?Math.max(state.saved.revision,latestRevision)+1:state.revision,saved:undefined}
}

/** 接收已完整解码的内容，一次切换来源、身份、步骤和恢复，避免混合修订。 */
export function flowDraftReducer(state:FlowEditorDraft,action:FlowDraftAction):FlowEditorDraft {
  switch(action.type){
    case 'field': return {...state,[action.key]:typeof action.value==='function'?action.value(state[action.key] as never):action.value}
    case 'dirty': return dirty(state,action.latestRevision)
    case 'steps': return {...dirty(state,action.latestRevision),steps:action.steps,selected:0,target:action.target,createdPath:action.createdPath}
    case 'saved': return {...state,saved:action.document,revision:action.document.revision}
    case 'load': {
      const document=action.document
      return {...state,phase:action.phase,sourceRequest:document.source_request,entityEvidence:document.entity_evidence??[],
        flowId:document.id,revision:action.revision,steps:action.steps,selected:0,target:document.workflow.target_step_id,
        createdPath:(document.workflow.steps.find(item=>item.id===document.workflow.target_step_id)?.request_template.response_extractors?.find(item=>item.extractor_id==='created_resource_id')?.json_path as string)??'',
        subject:document.subject_test_identity_id,owner:document.resource_owner_test_identity_id,resource:document.actual_resource_id,
        recovery:document.recovery?.relative_path??'',restoreMethod:document.recovery?.method??'POST',
        restoreBody:action.restoreBody??JSON.stringify(document.recovery?.json_body??{},null,2),
        provenance:document.provenance,recordingId:document.source_recording_id??'',saved:action.saved?document:undefined}
    }
  }
}
