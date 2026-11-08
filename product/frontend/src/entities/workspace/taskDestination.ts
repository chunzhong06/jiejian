import type {PrimaryTaskDto,PrimaryTaskKind} from './api/workspace'

const destinations:Record<PrimaryTaskKind,string>={
 CONFIRM_APPLICATION_ENDPOINT:'/application',AUTHORIZE_SOURCE_ANALYSIS:'/application?view=source',RUN_SOURCE_ANALYSIS:'/application?view=source',
 REVIEW_APPLICATION_CANDIDATES:'/application?view=business',REVIEW_ACTOR_IMPLEMENTATION:'/application?view=business',REVIEW_ACTION_IMPLEMENTATION:'/application?view=business',
 REVIEW_BOUNDARY_PROPOSAL:'/permissions',ESTABLISH_BUSINESS_BOUNDARY:'/permissions',REVIEW_PERMISSION_REVISION:'/permissions',COMPLETE_ALLOW_CONTROL:'/permissions',
 SELECT_ALLOW_CONTROL:'/preparation',REVIEW_RECORDING:'/preparation',PREPARE_TEST_IDENTITY:'/preparation',DEMONSTRATE_ACTION:'/preparation',PREPARE_ACTION_RESOURCE:'/preparation',COMPLETE_EFFECT_EVIDENCE:'/preparation',COMPLETE_RECOVERY:'/preparation',
 REGISTER_SOURCE_CHANGE:'/changes?view=register',PREPARE_AGENT_REPAIR:'/reports',VERIFY_REPAIR:'/permissions?view=repair',RUN_CURRENT_CHECK:'/reports?view=plan',VIEW_CURRENT_RESULT:'/reports',
 CREATE_DEVELOPMENT_TASK:'/changes',CONTINUE_DEVELOPMENT_TASK:'/changes',LOAD_DELIVERY_RUNTIME:'/changes',
}

/** 统一承接服务端具名任务，保留对象引用；导航不代表执行授权。 */
export function taskDestination(task:PrimaryTaskDto){
 const selected=task.route==='/permissions'&&destinations[task.task_kind]==='/preparation'?'/permissions':destinations[task.task_kind]
 const [path,search]=selected.split('?'),query=new URLSearchParams(search)
 const fields={action_id:task.business_action_id,action_revision:task.action_revision,actor_id:task.business_actor_id,change_id:task.change_id,proposal_id:task.proposal_id,run_id:task.run_id,recording_id:task.recording_id,identity_id:task.test_identity_id,account_slot:task.identity_slot_id,effect_id:task.effect_id}
 for(const [key,value] of Object.entries(fields))if(value!==null&&value!==undefined)query.set(key,String(value))
 if(task.repair_fingerprint){query.set('repair_reference',task.repair_fingerprint)}
 if(task.task_kind==='PREPARE_TEST_IDENTITY')query.set('identities','1')
 const material=task.task_kind==='COMPLETE_EFFECT_EVIDENCE'?'evidence':task.task_kind==='COMPLETE_RECOVERY'?'recovery':task.task_kind==='PREPARE_ACTION_RESOURCE'?'resource':task.task_kind==='REVIEW_RECORDING'||task.task_kind==='DEMONSTRATE_ACTION'?'execution':null
 if(material){query.set('focus',material);query.set('material_kind',material);if(task.effect_id)query.set('member_id',task.effect_id);else if(material==='resource'&&task.resource_owner_test_identity_id)query.set('member_id',task.resource_owner_test_identity_id)}
 if(task.task_kind==='COMPLETE_EFFECT_EVIDENCE'&&!task.recording_id){query.delete('material_kind');query.set('proof_sources','1')}
 if(task.task_kind==='REVIEW_RECORDING')query.set('material_kind',task.recording_purpose==='OBSERVATION'?'evidence':task.recording_purpose==='RECOVERY'?'recovery':'execution')
 return path+(query.size?'?'+query:'')
}
