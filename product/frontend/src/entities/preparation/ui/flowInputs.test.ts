import {expect,it} from 'vitest'
import {compileSteps,decodeSteps,newParameter,type EditableStep} from './flowInputs'
import {flowDraftReducer,type FlowEditorDraft} from './flowDraft'
import type {OperationFlow,FlowStep} from '../api/operationFlows'

const step=(id:string):FlowStep=>({id,purpose:'TARGET',identity_id:'CASE_SUBJECT',request_template:{method:'POST',path:'/orders/{case_resource_id}',body:{kind:'JSON',value:{title:'旧标题'}},query:[{name:'page',literal:'2'}],headers:[{name:'Accept',literal:'application/json'}],input_slots:[{slot_id:'case_resource_id',source:'CASE_RESOURCE_ID',consumer:'PATH',consumer_step_id:id}]},classifier:{accepted:[{kind:'STATUS_IN',statuses:[200]}],denied:[]},depends_on_step_ids:[]})

it('修改正文后查询、请求头、路径资源和输入类型仍可完整往返',()=>{
  const input=decodeSteps([step('target')])
  input[0].parameters.find(item=>item.name==='title')!.value='新标题'
  const result=compileSteps(input,'target','')[0]
  expect(result.request_template.query).toEqual([{name:'page',literal:'2'}])
  expect(result.request_template.headers).toEqual([{name:'Accept',literal:'application/json'}])
  expect(result.request_template.body).toEqual({kind:'JSON',value:{title:'新标题'}})
  expect(result.request_template.input_slots).toEqual([expect.objectContaining({slot_id:'case_resource_id',source:'CASE_RESOURCE_ID',consumer:'PATH'})])
  expect(decodeSteps([result])[0].parameters.map(item=>[item.name,item.location])).toEqual([['title','JSON_BODY'],['page','QUERY'],['Accept','HEADER'],['case_resource_id','PATH']])
})

it('同名的查询和正文动态值有独立引用，敏感请求头由前序提取',()=>{
  const setup=step('setup');setup.request_template={method:'GET',path:'/defaults',body:{kind:'EMPTY'}}
  const inputs=decodeSteps([setup,step('target')])
  inputs[1].parameters.push({...newParameter('QUERY'),name:'value',source:'PRIOR_STEP_JSON_PATH',producer:'setup',path:'$.query'},
    {...newParameter('JSON_BODY'),name:'value',source:'PRIOR_STEP_JSON_PATH',producer:'setup',path:'$.body'},
    {...newParameter('HEADER'),name:'X-CSRF-Token',source:'PRIOR_STEP_HEADER',producer:'setup',path:'X-CSRF-Token',secret:true})
  const output=compileSteps(inputs,'target',''),slots=output[1].request_template.input_slots!
  expect(new Set(slots.map(item=>item.slot_id)).size).toBe(slots.length)
  expect(output[0].request_template.response_extractors).toEqual(expect.arrayContaining([
    expect.objectContaining({kind:'JSON_PATH',json_path:'$.query'}),expect.objectContaining({kind:'JSON_PATH',json_path:'$.body'}),expect.objectContaining({kind:'HEADER',header_name:'X-CSRF-Token',secret:true})]))
  const reopened=decodeSteps(output)
  expect(reopened[1].parameters.find(item=>item.name==='X-CSRF-Token')).toMatchObject({source:'PRIOR_STEP_HEADER',secret:true,producer:'setup'})
  reopened[1].parameters=reopened[1].parameters.filter(item=>item.name!=='X-CSRF-Token')
  expect(compileSteps(reopened,'target','')[1].request_template.headers).toEqual([{name:'Accept',literal:'application/json'}])
})

it('嵌套 JSON 的原取值声明和空 JSON 正文不会在保存时丢失',()=>{
  const setup=step('setup');setup.request_template={method:'GET',path:'/defaults',body:{kind:'EMPTY'},response_extractors:[{extractor_id:'nested',kind:'JSON_PATH',json_path:'$.id'}]}
  const target=step('target');target.request_template.body={kind:'JSON',value:{data:{id:{$slot:'nested'}}}}
  target.request_template.input_slots!.push({slot_id:'nested',consumer:'JSON_BODY',source:'PRIOR_STEP_JSON_PATH',producer_step_id:'setup',source_path:'$.id'})
  expect(compileSteps(decodeSteps([setup,target]),'target','')[1].request_template.input_slots).toContainEqual(expect.objectContaining({slot_id:'nested',source_path:'$.id'}))
  target.request_template.body={kind:'JSON',value:{}}
  expect(compileSteps(decodeSteps([target]),'target','')[0].request_template.body).toEqual({kind:'JSON',value:{}})
})

it('敏感固定值和未来依赖在形成公共候选前拒绝',()=>{
  const input:EditableStep={id:'target',method:'GET',path:'/orders',parameters:[{...newParameter('QUERY'),name:'api_key',value:'private-value'}]}
  expect(()=>compileSteps([input],'target','')).toThrow('敏感参数')
  input.parameters=[{...newParameter('JSON_BODY'),name:'data',json:true,value:'{"credentials":{"token":"private-value","id":{"$slot":"other"}}}'}]
  expect(()=>compileSteps([input],'target','')).toThrow('敏感参数')
  input.parameters=[{...newParameter('HEADER'),name:'X-CSRF',source:'PRIOR_STEP_JSON_PATH',producer:'later',secret:true}]
  expect(()=>compileSteps([input],'target','')).toThrow('之前的请求')
})

it('载入流程同时切换身份资源和恢复，后续修改形成准确的新修订',()=>{
  const before:FlowEditorDraft={phase:1,origin:'manual',entityEvidence:[],flowId:'old',revision:1,steps:decodeSteps([step('old')]),selected:0,target:'old',createdPath:'',subject:'old-subject',owner:'old-owner',resource:'old-resource',recovery:'/old',restoreMethod:'POST',restoreBody:'{}',provenance:'MANUAL',recordingId:''}
  const document:OperationFlow={id:'new',revision:4,business_action_id:'action',action_revision:1,subject_test_identity_id:'subject',resource_owner_test_identity_id:'owner',provenance:'OPENAPI',source_recording_id:null,source_fingerprint:null,actual_resource_id:'resource',workflow:{steps:[step('target')],target_step_id:'target'},recovery:{method:'PUT',relative_path:'/restore',json_body:{state:'draft'}}}
  const loaded=flowDraftReducer(before,{type:'load',document,steps:decodeSteps(document.workflow.steps),revision:4,phase:4,saved:true})
  expect([loaded.flowId,loaded.subject,loaded.owner,loaded.resource,loaded.recovery,loaded.restoreMethod]).toEqual(['new','subject','owner','resource','/restore','PUT'])
  expect(loaded.saved).toBe(document)
  expect(before.flowId).toBe('old')
  const dirty=flowDraftReducer(loaded,{type:'dirty',latestRevision:9})
  expect(dirty.revision).toBe(10)
  expect(dirty.saved).toBeUndefined()
  const edited=flowDraftReducer(dirty,{type:'field',key:'steps',value:items=>[...items,...decodeSteps([step('later')])]})
  expect(edited.steps.map(item=>item.id)).toEqual(['target','later'])
  expect(edited.owner).toBe('owner')
})
