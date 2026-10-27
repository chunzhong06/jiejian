import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {beforeEach,expect,it,vi} from 'vitest'
import {MaterialEditor} from './MaterialEditor'
import {preparationApi} from '../../../entities/preparation/api/preparation'
import type {MaterialDetails,MaterialReference} from '../../../entities/preparation/api/preparation'
import {ApiError} from '../../../shared/api/http'

const reference:MaterialReference={action_id:'action',action_revision:1,kind:'evidence',member_id:'effect'}
const details:MaterialDetails={material:reference,status:'SATISFIED',reason_codes:[],retained:true,source_recording_id:'old',confirmed_at_us:100,expected_fingerprint:'basis',observed_at_us:100,recording_context:null,
  candidates:[{recording_id:'new',captured_at_us:null,current:true,updates:[reference]}]}
const impact={updates:[reference],retained:[],recheck:[]}
const props=()=>({projectId:'project',reference,label:'业务结果证明',actionName:'导出资料',onBack:vi.fn(),onError:vi.fn()})
beforeEach(()=>{
  vi.spyOn(preparationApi,'material').mockResolvedValue(structuredClone(details))
  vi.spyOn(preparationApi,'previewMaterial').mockResolvedValue(impact)
})
async function select(){fireEvent.click(await screen.findByRole('radio'));fireEvent.click(screen.getByRole('button',{name:'核对采用影响'}))}

it('先核对影响，明确采用后才写入一次',async()=>{
  const save=vi.spyOn(preparationApi,'saveMaterial').mockImplementation(async(_,value)=>({...impact,operation_id:value.operation_id,created_at_us:100,result:'SAVED'}))
  render(<MaterialEditor {...props()}/>);await select()
  const adopt=await screen.findByRole('button',{name:'采用这份记录'})
  expect(save).not.toHaveBeenCalled()
  expect(preparationApi.previewMaterial).toHaveBeenCalledWith('project',expect.objectContaining({material:reference,expected_fingerprint:'basis',candidate_recording_id:'new'}))
  fireEvent.click(adopt)
  await waitFor(()=>expect(save).toHaveBeenCalledOnce())
})

it('回执未知时只查询原操作，不再次保存',async()=>{
  const save=vi.spyOn(preparationApi,'saveMaterial').mockRejectedValue(new Error('response unavailable'))
  const receipt=vi.spyOn(preparationApi,'materialReceipt').mockImplementation(async(_,operation_id)=>({...impact,operation_id,created_at_us:100,result:'SAVED'}))
  const p=props();render(<MaterialEditor {...p}/>);await select()
  fireEvent.click(await screen.findByRole('button',{name:'采用这份记录'}))
  const query=await screen.findByRole('button',{name:'查询本次采用'})
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
  expect(screen.queryByRole('button',{name:'采用这份记录'})).not.toBeInTheDocument()
  expect(save).not.toHaveBeenCalled()
})

it.each(['transport','server'])('%s 回执不明后刷新恢复原操作，并拒绝跨项目与错误回执',async(kind)=>{
  const save=vi.spyOn(preparationApi,'saveMaterial').mockRejectedValue(kind==='transport' ? new Error('response unavailable') : new ApiError('STORAGE_FAILURE','写入结果无法确认'))
  const receipt=vi.spyOn(preparationApi,'materialReceipt').mockRejectedValue(new ApiError('RECORD_NOT_FOUND','尚未形成回执'))
  const p=props(),first=render(<MaterialEditor {...p}/>);await select()
  fireEvent.click(await screen.findByRole('button',{name:'采用这份记录'}))
  await screen.findByRole('button',{name:'查询本次采用'})
  const operation=save.mock.calls[0][1].operation_id
  first.unmount()
  const second=render(<MaterialEditor {...p}/>);
  fireEvent.click(await screen.findByRole('button',{name:'查询本次采用'}))
  await waitFor(()=>expect(receipt).toHaveBeenCalledWith('project',operation))
  await waitFor(()=>expect(p.onError).toHaveBeenCalledTimes(2))
  expect(p.onBack).not.toHaveBeenCalled()
  second.rerender(<MaterialEditor {...p} projectId="other-project"/>);
  await screen.findByRole('radio')
  expect(screen.queryByRole('button',{name:'查询本次采用'})).not.toBeInTheDocument()
  second.rerender(<MaterialEditor {...p}/>);
  receipt.mockResolvedValue({...impact,operation_id:'wrong-operation',created_at_us:100,result:'SAVED'})
  fireEvent.click(await screen.findByRole('button',{name:'查询本次采用'}))
  await waitFor(()=>expect(p.onError).toHaveBeenCalledTimes(3))
  expect(p.onBack).not.toHaveBeenCalled()
  receipt.mockResolvedValue({...impact,operation_id:operation,created_at_us:100,result:'SAVED'})
  fireEvent.click(screen.getByRole('button',{name:'查询本次采用'}))
  await waitFor(()=>expect(p.onBack).toHaveBeenCalledOnce())
  expect(save).toHaveBeenCalledOnce()
})
