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
 expect(screen.getByRole('heading',{name:'本次发现的业务后果'})).toBeVisible()
 expect(screen.getByText('已确认：完整交付包')).toBeVisible()
 expect(screen.queryByRole('link',{name:'查看开放后撤回的修改'})).not.toBeInTheDocument()
})
