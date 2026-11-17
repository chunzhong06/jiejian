import {render,screen} from '@testing-library/react'
import {expect,it} from 'vitest'
import {OfficialResultContext} from './OfficialResultContext'
import {story} from './report/Report.fixtures'

it('拒绝响应与恢复不覆盖已发布的业务后果及权限判断',()=>{
 const value=story(),item=value.actions[0]
 item.fact_comparison.effects[0].business_label='内部完整包已被接收'
 render(<OfficialResultContext story={value} implementation="EXPOSE_REVOKE"/>);
 expect(screen.getByText('403')).toBeVisible()
 expect(screen.getByText('完整收到内部包')).toBeVisible()
 expect(screen.getByText('已核对')).toBeVisible()
 expect(screen.getByText('不符合规则')).toBeVisible()
})

it('示例已停止时仍可先读历史报告的已确认后果，不提供当前演练接续',()=>{
 const value=story()
 render(<OfficialResultContext story={value}/>);
 expect(screen.getByRole('heading',{name:'内部包访问的业务核对'})).toBeVisible()
 expect(screen.getByText('已确认：完整交付包')).toBeVisible()
 expect(screen.queryByRole('link',{name:'查看开放后撤回的修改'})).not.toBeInTheDocument()
})

it('正常起点和未知观察沿同一关系阅读，不把HTTP状态当成业务判断',()=>{
 const value=story(),item=value.actions[0]
 item.case_verdict='SAFE';item.fact_comparison.effects[0].assessment_state='ABSENT'
 const view=render(<OfficialResultContext story={value}/>);
 expect(screen.getByText('符合规则')).toBeVisible()
 expect(screen.getByText('本次未观察到“完整交付包”')).toBeVisible()
 item.case_verdict='INCONCLUSIVE';item.fact_comparison.effects[0].assessment_state='UNKNOWN'
 view.rerender(<OfficialResultContext story={value}/>);
 expect(screen.getByText('证据不足')).toBeVisible()
 expect(screen.getByText('尚不能确认“完整交付包”')).toBeVisible()
})

it('缺少业务观察时不拿发布判断充当发生事实',()=>{
 const value=story();value.actions[0].fact_comparison.effects=[]
 render(<OfficialResultContext story={value}/>)
 expect(screen.getByText('尚无可读取的业务观察')).toBeVisible()
 expect(screen.getByText('不符合规则')).toBeVisible()
})
