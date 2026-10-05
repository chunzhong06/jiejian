// 搜索保留键盘选择和正式深链；输入本身不得执行目标操作。
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { EntrySearch } from './EntrySearch'

it('筛选账号后回车只定位正式账号入口', () => {
  const onNavigate = vi.fn(), onClose = vi.fn()
  render(<EntrySearch open onNavigate={onNavigate} onClose={onClose} />)
  const search = screen.getByRole('combobox', {name:'查找入口'})
  fireEvent.change(search, {target:{value:'测试账号'}})
  expect(screen.getAllByRole('option')).toHaveLength(1)
  expect(onNavigate).not.toHaveBeenCalled()
  fireEvent.keyDown(search, {key:'Enter'})
  expect(onNavigate).toHaveBeenCalledExactlyOnceWith('/tests?materials=1&identities=1')
  expect(onClose).toHaveBeenCalledOnce()
})

it('方向键改变候选，空结果回车不导航', () => {
  const onNavigate = vi.fn()
  render(<EntrySearch open onNavigate={onNavigate} onClose={vi.fn()} />)
  const search = screen.getByRole('combobox', {name:'查找入口'})
  fireEvent.keyDown(search,{key:'ArrowDown'})
  expect(screen.getByRole('option',{name:/权限约定/})).toHaveAttribute('aria-selected','true')
  fireEvent.change(search,{target:{value:'不存在的入口'}})
  fireEvent.keyDown(search,{key:'Enter'})
  expect(onNavigate).not.toHaveBeenCalled()
  expect(search).not.toHaveAttribute('aria-activedescendant')
})
