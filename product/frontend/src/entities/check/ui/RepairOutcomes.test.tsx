import {render,screen} from '@testing-library/react'
import {expect,it} from 'vitest'
import type {RepairComparisonRow} from '../api/repairs'
import {RepairOutcomes} from './RepairOutcomes'

it('同一正常操作合并用途，结果缺失或原题条件改变时不宣称保留',()=>{
  const row:RepairComparisonRow={role:'SELECTED_ALLOW',source_case_id:'before',action_label:'下载展示版',subject_label:'评审',resource_owner_label:'负责人',resource_id:'campus',effect_labels:['展示版被接收'],before_verdict:'SAFE',before_evidence_refs:[],after_case_id:'after',after_verdict:'SAFE',match_status:'MATCHED'}
  const view=render(<RepairOutcomes rows={[row,{...row,role:'REGRESSION'}]}/>)
  expect(screen.getAllByText('评审 · 下载展示版')).toHaveLength(1)
  expect(screen.getByText('正常操作保留')).toBeVisible()
  expect(screen.getByText('正常对照与功能回归')).toBeVisible()
  view.rerender(<RepairOutcomes rows={[{...row,match_status:'CHALLENGE_CHANGED'}]}/>)
  expect(screen.getByText('对应待核对')).toBeVisible()
  expect(screen.queryByText('正常操作保留')).not.toBeInTheDocument()
})
