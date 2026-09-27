// 验证页面抬头只承载标题、短说明和状态，不重新塞回普通操作按钮。

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PageTaskHeader } from './PageTaskHeader'

describe('PageTaskHeader', () => {
  it('只展示任务标题、短说明和状态', () => {
    render(<PageTaskHeader title="检查结果" description="查看可信结论" status="尚无结论" />)
    expect(screen.getByRole('heading', { name: '检查结果' })).toBeInTheDocument()
    expect(screen.getByText('查看可信结论')).toBeInTheDocument()
    expect(screen.getByText('尚无结论')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
