import {afterEach,expect,test} from 'vitest'
import {cleanup,render,screen,within} from '@testing-library/react'
import type {RepairComparisonRow} from '../api/repairs'
import {RepairCases} from './RepairCases'
afterEach(cleanup)
const row:RepairComparisonRow={role:'SELECTED_ALLOW',source_case_id:'allow',action_label:'读取内部安排',subject_label:'负责人',resource_owner_label:'负责人',resource_id:'loan-42',effect_labels:['内部安排可见'],before_verdict:'SAFE',before_evidence_refs:[],match_status:'NOT_AVAILABLE'}
test('相同正常用例保留对照和回归用途，并解释账号、归属和业务后果',()=>{
 render(<RepairCases rows={[row,{...row,role:'REGRESSION'}]}/>)
 expect(screen.getAllByRole('article')).toHaveLength(1)
 expect(screen.getByRole('heading',{name:'正常对照与功能回归'})).toBeVisible()
 expect(screen.getByText('测试数据：').textContent).toContain('loan-42')
 expect(screen.getByText('核对后果：内部安排可见')).toBeVisible()
})
test('前后对应未成立时保留真实结果，同时明确提示对应待核对',()=>{
 render(<RepairCases rows={[{...row,after_verdict:'SAFE',match_status:'AMBIGUOUS'}]} compare/>)
 const cells=within(screen.getAllByRole('row')[1]).getAllByRole('cell')
 expect(cells[2]).toHaveTextContent('符合规则')
 expect(within(cells[2]).getByText('对应待核对')).toBeVisible()
 expect(screen.queryByText('修复已验证')).toBeNull()
})
