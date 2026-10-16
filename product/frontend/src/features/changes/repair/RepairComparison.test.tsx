// 按实际合同义务数量展示前后事实；匹配诊断不能升级为修复成功。
import {render,screen,within} from '@testing-library/react'
import {expect,it} from 'vitest'
import type {RepairComparisonRow} from '../../../api/checks/repairs'
import {RepairComparison} from './RepairComparison'
const row=(role:RepairComparisonRow['role'],id:string):RepairComparisonRow=>({role,source_case_id:id,action_label:'归档资料',subject_label:'成员乙',resource_owner_label:'负责人甲',resource_id:'technical-only',effect_labels:['业务交付对象'],before_verdict:'SAFE',before_evidence_refs:['source'],match_status:'NOT_AVAILABLE'})
it('零回归仍保留原问题与独立正常对照，不写死样例三行',()=>{
 render(<RepairComparison rows={[row('DENY','one'),row('SELECTED_ALLOW','two')]}/>)
 expect(document.querySelectorAll('.repair-comparison > section')).toHaveLength(2)
 expect(screen.getByText('修复后仍应正常的允许操作')).toBeInTheDocument()
 expect(screen.queryByText('technical-only')).not.toBeInTheDocument()
 expect(screen.queryByText(/原问题修复已验证/)).not.toBeInTheDocument()
})
it('全部回归按角色保留，同 Case 不去重且模糊匹配不显示新 SAFE',()=>{
 const entries=[row('DENY','one'),row('SELECTED_ALLOW','two'),...['two','three','four'].map((id)=>({...row('REGRESSION',id),match_status:'AMBIGUOUS' as const,after_verdict:'SAFE' as const}))]
 render(<RepairComparison rows={entries}/>)
 const sections=document.querySelectorAll('.repair-comparison > section');expect(sections).toHaveLength(5)
 expect(screen.getAllByText('修复后仍须通过的其他检查')).toHaveLength(3)
 expect(within(sections[2] as HTMLElement).getByText('存在多项可能对应的操作，尚不能逐项关联')).toBeInTheDocument()
})
