import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {beforeEach,expect,it,vi} from 'vitest'
import {MaterialEditor} from './MaterialEditor'
import {preparationApi} from '../../../entities/preparation/api/preparation'
import type {MaterialDetails,MaterialReference} from '../../../entities/preparation/api/preparation'
import {ApiError} from '../../../shared/api/http'
import {operationFlowsApi,type OperationFlow} from '../../../entities/preparation/api/operationFlows'
import {testIdentitiesApi} from '../../../entities/preparation/api/testIdentities'
import {recordingsApi,type RecordingViewDto} from '../../../entities/preparation/api/recordings'

const reference:MaterialReference={action_id:'action',action_revision:1,kind:'evidence',member_id:'effect'}
const details:MaterialDetails={material:reference,status:'SATISFIED',reason_codes:[],retained:true,source_recording_id:'old',confirmed_at_us:100,expected_fingerprint:'basis',observed_at_us:100,recording_context:null,
  candidates:[{recording_id:'new',captured_at_us:null,current:true,updates:[reference]}]}
const impact={updates:[reference],retained:[],recheck:[]}
const props=()=>({projectId:'project',reference,label:'业务结果证明',actionName:'导出资料',onBack:vi.fn(),onError:vi.fn()})
beforeEach(()=>{
  vi.spyOn(preparationApi,'material').mockResolvedValue(structuredClone(details))
  vi.spyOn(preparationApi,'previewMaterial').mockResolvedValue(impact)
})
async function select(){fireEvent.click(await screen.findByRole('radio'));fireEvent.click(screen.getByRole('button',{name:'核对后用于检查'}))}

it('材料概览只使用准确动作版本的在用流程，不把较新的未采用修订当作当前材料',async()=>{
  const document:OperationFlow={id:'ofl_current',revision:1,business_action_id:'action',action_revision:1,subject_test_identity_id:'owner',resource_owner_test_identity_id:'owner',provenance:'MANUAL',source_recording_id:null,source_fingerprint:null,actual_resource_id:'current-resource',workflow:{steps:[],target_step_id:'target'},recovery:null}
  vi.spyOn(operationFlowsApi,'context').mockResolvedValue({project_id:'project',source_fingerprint:null,endpoint:null,recordings:[],actions:[{action_id:'action',revision:1,label:'导出资料',state_changing:false,effects:[]}],flows:[{document:{...document,revision:2,actual_resource_id:'unadopted-resource'},adopted:false,in_use:false,configuration_current:true},{document,adopted:true,in_use:true,configuration_current:true}]})
  vi.spyOn(testIdentitiesApi,'list').mockResolvedValue([{identity_id:'owner',label:'负责人',auth_method:'COOKIE'}] as never)
  const view=render(<MaterialEditor {...props()} reference={{action_id:'action',action_revision:1,kind:'resource',member_id:'owner'}}/>)
  expect(await screen.findByText('current-resource')).toBeVisible()
  expect(screen.queryByText('unadopted-resource')).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'建立本次录制'})).not.toBeInTheDocument()
  view.rerender(<MaterialEditor {...props()} reference={{action_id:'action',action_revision:2,kind:'resource',member_id:'owner'}}/>)
  await screen.findByRole('radio')
  expect(screen.queryByText('current-resource')).not.toBeInTheDocument()
})

it.each([false,true])('材料原因与保留状态分别表达，保留原记录=%s',async retained=>{
  vi.mocked(preparationApi.material).mockResolvedValue({...details,status:'NEEDS_USER',reason_codes:['UNRECOGNIZED_REASON'],retained})
  render(<MaterialEditor {...props()}/>);
  expect(await screen.findByText('当前材料需要重新核对。')).toBeVisible()
  expect(screen.queryByText('原记录已保留')!==null).toBe(retained)
  expect(screen.queryByText(/原记录仍保留/)).not.toBeInTheDocument()
  expect(await screen.findByRole('radio')).toBeVisible()
})

it('先核对影响，明确采用后才写入一次',async()=>{
  const save=vi.spyOn(preparationApi,'saveMaterial').mockImplementation(async(_,value)=>({...impact,operation_id:value.operation_id,created_at_us:100,result:'SAVED'}))
  render(<MaterialEditor {...props()}/>);await select()
  const adopt=await screen.findByRole('button',{name:'确认使用这份录制'})
  expect(save).not.toHaveBeenCalled()
  expect(preparationApi.previewMaterial).toHaveBeenCalledWith('project',expect.objectContaining({material:reference,expected_fingerprint:'basis',candidate_recording_id:'new'}))
  fireEvent.click(adopt)
  await waitFor(()=>expect(save).toHaveBeenCalledOnce())
})

it('回执未知时只查询原操作，不再次保存',async()=>{
  const save=vi.spyOn(preparationApi,'saveMaterial').mockRejectedValue(new Error('response unavailable'))
  const receipt=vi.spyOn(preparationApi,'materialReceipt').mockImplementation(async(_,operation_id)=>({...impact,operation_id,created_at_us:100,result:'SAVED'}))
  const p=props();render(<MaterialEditor {...p}/>);await select()
  fireEvent.click(await screen.findByRole('button',{name:'确认使用这份录制'}))
  const query=await screen.findByRole('button',{name:'查看本次使用结果'})
  expect(save).toHaveBeenCalledOnce()
  expect(receipt).not.toHaveBeenCalled()
  const operation=save.mock.calls[0][1].operation_id
  fireEvent.click(query)
  await waitFor(()=>expect(receipt).toHaveBeenCalledWith('project',operation))
  expect(save).toHaveBeenCalledOnce()
  expect(p.onBack).toHaveBeenCalledOnce()
})

it('陈旧依据被服务拒绝后不能出现采用操作',async()=>{
  vi.mocked(preparationApi.previewMaterial).mockRejectedValue(new ApiError('STATE_PRECONDITION','来源已经变化'))
  const save=vi.spyOn(preparationApi,'saveMaterial')
  const p=props();render(<MaterialEditor {...p}/>);await select()
  await waitFor(()=>expect(p.onError).toHaveBeenCalledOnce())
  expect(screen.queryByRole('button',{name:'确认使用这份录制'})).not.toBeInTheDocument()
  expect(save).not.toHaveBeenCalled()
})

it.each(['transport','server'])('%s 回执不明后刷新恢复原操作，并拒绝跨项目与错误回执',async(kind)=>{
  const save=vi.spyOn(preparationApi,'saveMaterial').mockRejectedValue(kind==='transport' ? new Error('response unavailable') : new ApiError('STORAGE_FAILURE','写入结果无法确认'))
  const receipt=vi.spyOn(preparationApi,'materialReceipt').mockRejectedValue(new ApiError('RECORD_NOT_FOUND','尚未形成回执'))
  const p=props(),first=render(<MaterialEditor {...p}/>);await select()
  fireEvent.click(await screen.findByRole('button',{name:'确认使用这份录制'}))
  await screen.findByRole('button',{name:'查看本次使用结果'})
  const operation=save.mock.calls[0][1].operation_id
  first.unmount()
  const second=render(<MaterialEditor {...p}/>);
  fireEvent.click(await screen.findByRole('button',{name:'查看本次使用结果'}))
  await waitFor(()=>expect(receipt).toHaveBeenCalledWith('project',operation))
  await waitFor(()=>expect(p.onError).toHaveBeenCalledTimes(2))
  expect(p.onBack).not.toHaveBeenCalled()
  second.rerender(<MaterialEditor {...p} projectId="other-project"/>);
  await screen.findByRole('radio')
  expect(screen.queryByRole('button',{name:'查看本次使用结果'})).not.toBeInTheDocument()
  second.rerender(<MaterialEditor {...p}/>);
  receipt.mockResolvedValue({...impact,operation_id:'wrong-operation',created_at_us:100,result:'SAVED'})
  fireEvent.click(await screen.findByRole('button',{name:'查看本次使用结果'}))
  await waitFor(()=>expect(p.onError).toHaveBeenCalledTimes(3))
  expect(p.onBack).not.toHaveBeenCalled()
  receipt.mockResolvedValue({...impact,operation_id:operation,created_at_us:100,result:'SAVED'})
  fireEvent.click(screen.getByRole('button',{name:'查看本次使用结果'}))
  await waitFor(()=>expect(p.onBack).toHaveBeenCalledOnce())
  expect(save).toHaveBeenCalledOnce()
})

function newRecording(){
  vi.mocked(preparationApi.material).mockResolvedValue({...details,candidates:[],recording_context:{context_id:'context',material:reference,expected_fingerprint:'basis',can_execute:true,business_action_id:'action',action_revision:1,subject_test_identity_id:'owner',resource_owner_test_identity_id:'owner',subject_slot_id:'subject',resource_owner_slot_id:'resource',recording_purpose:'OBSERVATION',parent_recording_id:'original',effect_id:'effect',recording_id:null,title:'',why_now:'',user_responsibility:'',system_will_do:''}})
  vi.spyOn(recordingsApi,'setup').mockResolvedValue({test_identity_options:[],action_options:[]})
}
const recoveredRecording:RecordingViewDto={recording:{recording_id:'recorded',project_id:'project',business_action_id:'action',action_revision:1,subject_test_identity_id:'owner',resource_owner_test_identity_id:'owner',purpose:'OBSERVATION',parent_recording_id:'original',state:'RECORDING',capture_phase:'AWAITING_CAPTURE'}}

it('明确未受理的录制创建释放新请求，允许处理条件后重建',async()=>{
 newRecording()
 vi.spyOn(recordingsApi,'createRecording').mockRejectedValue(new ApiError('STATE_PRECONDITION','先核对账号',undefined,undefined,undefined,undefined,'NOT_ACCEPTED'))
 const p=props();render(<MaterialEditor {...p}/>)
 fireEvent.click(await screen.findByLabelText('我已核对本次操作账号与资源所有者'))
 fireEvent.click(screen.getByRole('button',{name:'建立本次录制'}))
 await waitFor(()=>expect(p.onError).toHaveBeenCalledOnce())
 expect(screen.getByRole('button',{name:'建立本次录制'})).toBeEnabled()
 expect(screen.queryByRole('button',{name:'查询并恢复本次录制'})).not.toBeInTheDocument()
})

it('建立录制的服务错误保留原请求，重新打开先查询回执而不重建',async()=>{
  newRecording()
  const create=vi.spyOn(recordingsApi,'createRecording').mockRejectedValue(new ApiError('STORAGE_FAILURE','响应未能完成'))
  const receipt=vi.spyOn(recordingsApi,'receipt').mockResolvedValue(recoveredRecording)
  vi.spyOn(recordingsApi,'recording').mockResolvedValue(recoveredRecording)
  const first=render(<MaterialEditor {...props()}/>)
  fireEvent.click(await screen.findByLabelText('我已核对本次操作账号与资源所有者'))
  fireEvent.click(screen.getByRole('button',{name:'建立本次录制'}))
  expect(await screen.findByRole('button',{name:'查询并恢复本次录制'})).toBeVisible()
  expect(screen.getByRole('button',{name:'建立本次录制'})).toBeDisabled()
  const operation=create.mock.calls[0][2]
  first.unmount();render(<MaterialEditor {...props()}/>)
  expect(await screen.findByRole('button',{name:'开始记录这个操作'})).toBeVisible()
  expect(receipt).toHaveBeenCalledWith('project',operation)
  expect(create).toHaveBeenCalledOnce()
})

it.each(['action','account','purpose','id'])('恢复录制拒绝错误对应：%s，继续保留原请求',async mismatch=>{
  newRecording()
  const create=vi.spyOn(recordingsApi,'createRecording').mockRejectedValue(new TypeError('连接中断'))
  const receipt=vi.spyOn(recordingsApi,'receipt')
  const read=vi.spyOn(recordingsApi,'recording')
  const p=props();render(<MaterialEditor {...p}/>)
  fireEvent.click(await screen.findByLabelText('我已核对本次操作账号与资源所有者'))
  fireEvent.click(screen.getByRole('button',{name:'建立本次录制'}))
  const recover=await screen.findByRole('button',{name:'查询并恢复本次录制'})
  const wrong=structuredClone(recoveredRecording)
  if(mismatch==='action')wrong.recording!.action_revision=2
  if(mismatch==='account')wrong.recording!.subject_test_identity_id='another'
  if(mismatch==='purpose')wrong.recording!.purpose='RECOVERY'
  if(mismatch==='id'){
    const key=Object.keys(sessionStorage).find(key=>key.endsWith(':recording'))!
    const pending=JSON.parse(sessionStorage.getItem(key)!)
    sessionStorage.setItem(key,JSON.stringify({...pending,recordingId:'original-id'}))
    read.mockResolvedValue(wrong)
  }else receipt.mockResolvedValue(wrong)
  fireEvent.click(recover)
  await waitFor(()=>expect(p.onError).toHaveBeenCalledTimes(2))
  await waitFor(()=>expect(screen.getByRole('button',{name:'建立本次录制'})).toBeDisabled())
  await waitFor(()=>expect(mismatch==='id'?read:receipt).toHaveBeenCalled())
  expect(screen.queryByRole('button',{name:'开始记录这个操作'})).not.toBeInTheDocument()
  expect(create).toHaveBeenCalledOnce()
  expect(Object.keys(sessionStorage).some(key=>key.endsWith(':recording'))).toBe(true)
})
