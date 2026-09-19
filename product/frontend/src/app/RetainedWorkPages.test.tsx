// 离开再返回保持本地输入；项目边界重建时必须清除上一个项目的页面状态。
import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { RetainedWorkPages } from './RetainedWorkPages'
function Draft(){const [value,setValue]=useState('');return <input aria-label="权限草稿" value={value} onChange={event=>setValue(event.target.value)}/>}
describe('工作页面会话',()=>{
  it('导航隐藏页面并保留输入，返回不重新创建草稿',()=>{
    vi.spyOn(window,'scrollTo').mockImplementation(()=>{})
    const view=render(<RetainedWorkPages activeKey="permissions"><Draft/></RetainedWorkPages>)
    fireEvent.change(screen.getByLabelText('权限草稿'),{target:{value:'只允许所属成员'}})
    view.rerender(<RetainedWorkPages activeKey="history"><h1>检查历史</h1></RetainedWorkPages>)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    view.rerender(<RetainedWorkPages activeKey="permissions"><Draft/></RetainedWorkPages>)
    expect(screen.getByLabelText('权限草稿')).toHaveValue('只允许所属成员')
  })
  it('项目切换重建会话，不携带另一个项目的输入',()=>{
    const view=render(<RetainedWorkPages key="p1" activeKey="permissions"><Draft/></RetainedWorkPages>)
    fireEvent.change(screen.getByLabelText('权限草稿'),{target:{value:'p1草稿'}})
    view.rerender(<RetainedWorkPages key="p2" activeKey="permissions"><Draft/></RetainedWorkPages>)
    expect(screen.getByLabelText('权限草稿')).toHaveValue('')
  })
})
