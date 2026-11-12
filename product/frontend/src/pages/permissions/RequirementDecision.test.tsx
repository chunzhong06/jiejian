import {fireEvent,render,screen} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {RequirementDecision} from './RequirementDecision'

it('互斥选择不提交；确认传递当前值，等待时保留选择并锁定输入',()=>{
  const onConfirm=vi.fn(),options=[['IN_SCOPE','纳入检查'],['PREPARATION','准备条件']] as const
  const {rerender}=render(<RequirementDecision label="这项要求的处理方式" options={options} confirmLabel="确认范围" busy={false} onConfirm={onConfirm}/>)
  expect(screen.getByRole('button',{name:'确认范围'})).toBeDisabled()
  fireEvent.click(screen.getByRole('radio',{name:'纳入检查'}))
  fireEvent.click(screen.getByRole('radio',{name:'准备条件'}))
  expect(screen.getByRole('radio',{name:'纳入检查'})).not.toBeChecked()
  expect(onConfirm).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'确认范围'}))
  expect(onConfirm).toHaveBeenCalledExactlyOnceWith('PREPARATION')
  rerender(<RequirementDecision label="这项要求的处理方式" options={options} confirmLabel="确认范围" busy onConfirm={onConfirm}/>)
  expect(screen.getByRole('radio',{name:'准备条件'})).toBeChecked()
  expect(screen.getByRole('radio',{name:'准备条件'})).toBeDisabled()
})
