// 验证文件准备的显式授权、恢复不重取样和跨项目迟到响应保护。
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {ReferenceFilePreparation} from './ReferenceFilePreparation'
import type {ProofContext,ProofSource} from '../../../api/preparation/proofSources'
const api=vi.hoisted(()=>({capturePreview:vi.fn(),captureStatus:vi.fn(),referenceDownload:vi.fn()}))
vi.mock('../../../api/preparation/proofSources',()=>({proofSourcesApi:api}))
const source={source_id:'source',revision:1,config:{action_id:'action',action_revision:1,resource_binding_id:'res',collection:'units',
  source_kind:'REFERENCE_FILE',identity_claims:[{identity_id:'alice',application_subject_id:'alice'}]}} as ProofSource
const context={project_id:'app_a',basis_id:'basis',runtime_available:true,runtime_origin:'http://127.0.0.1:1234',sources:[source],read_scopes:[],
  actions:[{action_id:'action',revision:1,label:'取得文件',execution_identity_id:'alice',recovery_identity_id:'alice',effects:[]}],
  identities:[{identity_id:'alice',actor_id:'owner',label:'Alice',prepared:true}],
  resources:[{resource_binding_id:'res',action_id:'action',action_revision:1,resource_id:'alpha',owner_identity_id:'alice'}],
  reference_inputs:[],allow_permissions:[{intent_id:'allow',action_id:'action',action_revision:1,subject_actor_id:'owner',owner_actor_id:'owner',relation:'OWNS'}]} as ProofContext
const plan={project_id:'app_a',basis_id:'basis',plan_hash:'hash',created_at_us:7,restore:null,
  case:{subject_test_identity_id:'alice',resource_id:'alpha'},runtime:{source_fingerprint:'source-hash',target:{base_url:'http://127.0.0.1:1234',max_response_bytes:4194304},actions:[{display_name:'取得文件',state_changing:true}]}}
const props={projectId:'app_a',context,source,busy:false,pending:false,onWrite:vi.fn().mockResolvedValue(undefined),onRefresh:vi.fn().mockResolvedValue(undefined)}
beforeEach(()=>{vi.clearAllMocks();api.capturePreview.mockResolvedValue(plan)})
afterEach(cleanup)

it('预览不执行，核对范围并勾选后才提交一次',async()=>{
  render(<ReferenceFilePreparation {...props}/>)
  fireEvent.click(screen.getByRole('button',{name:'预览获取操作'}))
  const start=await screen.findByRole('button',{name:'允许并开始本次取样'})
  expect(start).toBeDisabled();expect(props.onWrite).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('checkbox',{name:'允许本次正常操作及所列恢复'}));fireEvent.click(start)
  await waitFor(()=>expect(props.onWrite).toHaveBeenCalledTimes(1))
  expect(props.onWrite.mock.calls[0]).toEqual(['START_REFERENCE_CAPTURE',expect.objectContaining({plan_hash:'hash',plan_created_at_us:7,confirmed:true})])
})

it('恢复缺口禁用新取样，只恢复原capture并明确没有新文件',async()=>{
  api.capturePreview.mockResolvedValue({...plan,restore:{capture_id:'original',resource_id:'alpha',generation:'old'}})
  render(<ReferenceFilePreparation {...props} context={{...context,reference_recovery_gaps:[{capture_id:'original',action_id:'action',resource_id:'alpha',owner_identity_id:'alice',reason:'REFERENCE_RECOVERY_UNVERIFIED'}]}}/>)
  expect(screen.getByRole('button',{name:'预览获取操作'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'核对并恢复'}))
  await screen.findByRole('button',{name:'允许本次恢复核对'})
  expect(api.capturePreview.mock.calls[0][1].restore_capture_id).toBe('original')
  expect(screen.getByText('本次不会重新下载，也不会取得或采用新的文件参照。')).toBeInTheDocument()
  expect(props.onWrite).not.toHaveBeenCalled()
})

it('项目切换丢弃旧预览，不让旧权限操作新项目',async()=>{
  let resolve!:(value:unknown)=>void
  api.capturePreview.mockReturnValue(new Promise(done=>{resolve=done}))
  const view=render(<ReferenceFilePreparation {...props}/>)
  fireEvent.click(screen.getByRole('button',{name:'预览获取操作'}))
  view.rerender(<ReferenceFilePreparation {...props} projectId="app_b" context={{...context,project_id:'app_b'}}/>)
  await act(async()=>{resolve(plan)})
  expect(screen.queryByRole('button',{name:'允许并开始本次取样'})).not.toBeInTheDocument()
  expect(props.onWrite).not.toHaveBeenCalled()
})

it('原写操作回执未知时不能再次取样或上传',()=>{
  render(<ReferenceFilePreparation {...props} pending/>)
  expect(screen.getByRole('radio',{name:'让界鉴获取测试文件'})).toBeDisabled()
  expect(screen.getByRole('radio',{name:'使用已有测试文件'})).toBeDisabled()
  expect(screen.getByRole('button',{name:'预览获取操作'})).toBeDisabled()
})
