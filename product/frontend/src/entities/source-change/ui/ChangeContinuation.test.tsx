import {cleanup,fireEvent,render,screen,within} from '@testing-library/react'
import {afterEach,expect,it} from 'vitest'
import type {SourceChangeViewDto} from '../api/sourceChanges'
import {ChangeContinuation} from './ChangeContinuation'

afterEach(cleanup)
type Material=NonNullable<SourceChangeViewDto['continuation']>['materials'][number]
const account=(action:string,member:string):Material=>({action_id:action,action_label:'操作 '+action,kind:'identity',status:'STALE',reason_codes:['TEST_IDENTITY_LOGIN_REQUIRED'],permission_ids:[],member_id:member,member_label:'同名负责人',handling:'RECHECK',explanation:'核对当前身份。',next_step:'继续原账号核对。'})
function view(materials:Material[]):SourceChangeViewDto{return {
  manifest:{project_id:'app',change_id:'change',reason:'修复读取范围',submitted_by:'LOCAL_GUI',created_at_us:1,claimed_paths:[],repair_reference:null},
  change_set:{status:'COMPARABLE',added_paths:[],modified_paths:[],removed_paths:[]},
  assessment:{payload:{policy_epoch:1,permission_refs:[],action_impacts:[]}},
  revalidation:{status:'READY',can_execute:false,preparation_gaps:[]},
  continuation:{fingerprint:'basis',plan_fingerprint:null,requirements:[],added_requirements:[],materials,next_step:'按原要求复验。',scope:'本次范围'},
}}

it('只合并准确账号和相同处理，同名不同账号仍保留独立材料',()=>{
  render(<ChangeContinuation value={view([account('a','owner'),account('b','owner'),account('a','another')])} origin="/changes?change_id=change"/>)
  fireEvent.click(screen.getByText('当前要求与材料的核对依据'))
  const shared=screen.getByText('共用测试账号').closest('section')!
  expect(within(shared).getAllByText('同名负责人')).toHaveLength(1)
  expect(within(shared).getByText('用于：操作 a、操作 b')).toBeVisible()
  const separate=screen.getByText('各项操作的检查材料').closest('section')!
  expect(within(separate).getByText('同名负责人')).toBeVisible()
})

it('同一账号处理不同不归并，未命名材料仍显示类别',()=>{
  const resource:Material={...account('a','resource'),kind:'resource',member_label:'',explanation:'核对原资源。'}
  render(<ChangeContinuation value={view([account('a','owner'),{...account('b','owner'),handling:'DECIDE'},resource])} origin="/changes?change_id=change"/>)
  fireEvent.click(screen.getByText('当前要求与材料的核对依据'))
  expect(screen.queryByText('共用测试账号')).not.toBeInTheDocument()
  expect(screen.getByText('测试资源')).toBeVisible()
  expect(screen.getByText('需要你决定')).toBeVisible()
})

it('同处理的不同材料仍独立成行，共同核对方式只说明一次',()=>{
  const flow:Material={...account('a','flow'),kind:'execution',member_label:'发布资料流程'}
  const proof:Material={...account('a','proof'),kind:'evidence',member_label:'资料已发布'}
  render(<ChangeContinuation value={view([flow,proof])} origin="/changes?change_id=change"/>)
  fireEvent.click(screen.getByText('当前要求与材料的核对依据'))
  const flowRow=screen.getByText('发布资料流程').closest('tr')!
  expect(within(flowRow).getByText('需要重新核对')).toBeVisible()
  expect(within(flowRow).queryByText('资料已发布')).not.toBeInTheDocument()
  expect(screen.getByText('资料已发布').closest('tr')).not.toBe(flowRow)
  expect(screen.getAllByText('继续原账号核对。')).toHaveLength(1)
})
