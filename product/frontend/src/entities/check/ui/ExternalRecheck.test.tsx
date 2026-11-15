import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {ExternalRecheck} from './ExternalRecheck'
import {currentChecksApi as api,type CheckPreview} from '../api/currentChecks'
import type {RepairContract} from '../api/repairs'

const contract:RepairContract={project_id:'app',source_run_id:'source',source_case_id:'deny',repair_fingerprint:'f'.repeat(64),original_policy_epoch:1,
  deny:{identity:{action_id:'read',resource_id:'order-1',subject_test_identity_id:'member',resource_owner_test_identity_id:'owner',protected_effect_ids:['note']},evidence_refs:[]},regressions:[]}
const preview:CheckPreview={project_id:'app',can_execute:true,plan_fingerprint:'a'.repeat(64),action_count:1,case_count:2,gaps:[],actions:[]}
const mount=()=>render(<ExternalRecheck projectId="app" contract={contract} comparison={[]} endpoint="http://127.0.0.1:8080" onClose={vi.fn()}/> )

it('复验材料不足时返回准确操作与原问题，保持开始门禁',async()=>{
  vi.spyOn(api,'externalPreview').mockResolvedValue({...preview,can_execute:false,gaps:[{action_id:'read',action_revision:1,reason:'IDENTITY_NOT_PREPARED'}]})
  const submit=vi.spyOn(api,'submit')
  mount()
  expect(screen.getAllByRole('button',{name:'返回问题'})).toHaveLength(1)
  fireEvent.change(screen.getByLabelText('本次部署或处理说明'),{target:{value:'已部署读取授权修改'}})
  fireEvent.click(screen.getByRole('button',{name:'预览原问题与正常对照'}))
  const link=await screen.findByRole('link',{name:'核对原问题材料'})
  const query=new URLSearchParams(link.getAttribute('href')!.split('?')[1])
  expect(query.get('action_id')).toBe('read')
  expect(new URLSearchParams(query.get('return_to')!.split('?')[1]).get('source_case_id')).toBe('deny')
  expect(screen.getByRole('button',{name:'确认范围并开始'})).toBeDisabled()
  expect(submit).not.toHaveBeenCalled()
})

it('预览只读，修改部署说明后须重新预览，不自动提交',async()=>{
  const read=vi.spyOn(api,'externalPreview').mockResolvedValue(preview)
  const submit=vi.spyOn(api,'submit')
  mount()
  expect(screen.getAllByRole('button',{name:'返回问题'})).toHaveLength(1)
  fireEvent.change(screen.getByLabelText('本次部署或处理说明'),{target:{value:'已调整订单可见范围'}})
  fireEvent.click(screen.getByRole('button',{name:'预览原问题与正常对照'}))
  expect(await screen.findByRole('button',{name:'确认范围并开始'})).toBeEnabled()
  expect(read).toHaveBeenCalledWith('app',{reference:{source_run_id:'source',source_case_id:'deny',repair_fingerprint:contract.repair_fingerprint},deployment_statement:'已调整订单可见范围'})
  expect(submit).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('本次部署或处理说明'),{target:{value:'另一份部署说明'}})
  expect(screen.queryByRole('button',{name:'确认范围并开始'})).not.toBeInTheDocument()
})

it('恢复未知提交时先查询原回执，未查到不会自动重发',async()=>{
  const saved={operation:'original-operation',fingerprint:preview.plan_fingerprint,command:{reference:{source_run_id:'source',source_case_id:'deny',repair_fingerprint:contract.repair_fingerprint},deployment_statement:'原部署说明'}}
  sessionStorage.setItem('jiejian.external-recheck:app:'+contract.repair_fingerprint,JSON.stringify(saved))
  const receipt=vi.spyOn(api,'receipt').mockResolvedValue(null),submit=vi.spyOn(api,'submit')
  mount()
  expect(screen.getByLabelText('本次部署或处理说明')).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'查看上次提交结果'}))
  expect(await screen.findByRole('button',{name:'恢复原提交'})).toBeEnabled()
  await waitFor(()=>expect(receipt).toHaveBeenCalledWith('app','original-operation'))
  expect(submit).not.toHaveBeenCalled()
  expect(JSON.parse(sessionStorage.getItem('jiejian.external-recheck:app:'+contract.repair_fingerprint)!)).toEqual(saved)
})

it('同一正常用例承担对照和回归时合并展示，保留两个用途',()=>{
 const row={source_case_id:'normal',action_label:'读取内部安排',subject_label:'甲',resource_owner_label:'甲',resource_id:'loan-1042',effect_labels:['内部安排'],before_verdict:'SAFE',before_evidence_refs:[],match_status:'NOT_AVAILABLE'} as const
 render(<ExternalRecheck projectId="app" contract={contract} comparison={[{...row,role:'DENY',source_case_id:'deny',subject_label:'乙',effect_labels:[...row.effect_labels],before_evidence_refs:[]},{...row,role:'SELECTED_ALLOW',effect_labels:[...row.effect_labels],before_evidence_refs:[]},{...row,role:'REGRESSION',effect_labels:[...row.effect_labels],before_evidence_refs:[]}]} endpoint="http://127.0.0.1:8080" onClose={vi.fn()}/> )
 expect(screen.getAllByRole('article')).toHaveLength(2)
 expect(screen.getByRole('heading',{name:'正常对照与功能回归'})).toBeVisible()
})
