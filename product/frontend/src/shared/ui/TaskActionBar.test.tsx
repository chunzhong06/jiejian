// 验证所有页面共用的操作层级、表单提交与危险操作确认，避免页面各自复制交互约定。
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TaskActionBar } from './TaskActionBar'

describe('共享操作区合同', () => {
  it('只有主操作使用主按钮，刷新和返回保留独立可访问名称', () => {
    const refresh = vi.fn()
    render(<TaskActionBar back={{ label: '返回' }} refresh={{ label: '刷新状态', onClick: refresh }} primary={{ label: '确认采用' }} />)
    expect(screen.getByRole('button', { name: '确认采用' })).toHaveClass('ant-btn-primary')
    expect(screen.getByRole('button', { name: '返回' })).not.toHaveClass('ant-btn-primary')
    fireEvent.click(screen.getByRole('button', { name: '刷新状态' }))
    expect(refresh).toHaveBeenCalledOnce()
  })
  it.each(['loading', 'disabled'] as const)('主操作处于 %s 时不能重复提交', (state) => {
    const submit = vi.fn()
    render(<TaskActionBar primary={{ label: '提交检查', onClick: submit, [state]: true }} />)
    fireEvent.click(screen.getByRole('button', { name: '提交检查' }))
    expect(submit).not.toHaveBeenCalled()
  })
  it('表单型主操作关联指定表单，返回按钮不误提交', () => {
    render(<TaskActionBar back={{ label: '返回' }} primary={{ label: '保存', submitForm: 'proof-form' }} />)
    expect(screen.getByRole('button', { name: '保存' })).toHaveAttribute('form', 'proof-form')
    expect(screen.getByRole('button', { name: '保存' })).toHaveAttribute('type', 'submit')
    expect(screen.getByRole('button', { name: '返回' })).toHaveAttribute('type', 'button')
  })
  it('危险操作必须经过确认，打开确认浮层不能执行', async () => {
    const restart = vi.fn()
    render(<TaskActionBar restart={{ label: '重新开始', onClick: restart, confirm: { title: '确认重新开始？', description: '历史记录保留，本步骤重新准备。', okText: '确认', cancelText: '取消' } }} />)
    fireEvent.click(screen.getByRole('button', { name: '重新开始' }))
    expect(restart).not.toHaveBeenCalled()
    fireEvent.click(await screen.findByRole('button', { name: '确 认' }))
    expect(restart).toHaveBeenCalledOnce()
  })
})
