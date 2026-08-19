import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PageTaskHeader } from './PageTaskHeader'

describe('PageTaskHeader', () => {
  it('展示任务标题、状态和唯一主操作', () => {
    const onAction = vi.fn()
    render(<PageTaskHeader title="检查结果" description="查看可信结论" status="尚无结论" next="等待结果" actionLabel="查看完整报告" onAction={onAction} />)
    expect(screen.getByRole('heading', { name: '检查结果' })).toBeInTheDocument()
    expect(screen.getByText('尚无结论')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '查看完整报告' }))
    expect(onAction).toHaveBeenCalledTimes(1)
  })
})
