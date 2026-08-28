// 验证应用接入页只保留正式接入向导，不再暴露旧 Profile 注册或项目管理面板。

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AccessPage } from './AccessPage'

const setupProps = vi.hoisted(() => ({ current: undefined as Record<string, unknown> | undefined }))

vi.mock('./ApplicationSetup', () => ({
  ApplicationSetup: (props: Record<string, unknown>) => {
    setupProps.current = props
    return <div data-testid="application-setup">正式应用接入向导</div>
  },
}))

describe('AccessPage', () => {
  it('只展示正式应用接入任务并把导航交给连续向导', () => {
    const onBack = vi.fn()
    const onContinue = vi.fn()
    render(<AccessPage
      selected={{ project_id: 'app-1', name: '示例应用', status: 'DRAFT' }}
      endpointStatus="NEEDS_CONFIRMATION"
      onConnected={vi.fn()}
      onUnderstandingChanged={vi.fn()}
      onBack={onBack}
      onContinue={onContinue}
    />)

    expect(screen.getByRole('heading', { name: '应用接入' })).toBeInTheDocument()
    expect(screen.getByTestId('application-setup')).toHaveTextContent('正式应用接入向导')
    expect(screen.queryByText(/Profile|注册并校验|当前工作概览|项目列表/i)).not.toBeInTheDocument()
    expect(screen.queryByPlaceholderText(/profiles\\profile\.json/i)).not.toBeInTheDocument()
    expect(setupProps.current?.endpointStatus).toBe('NEEDS_CONFIRMATION')

    ;(setupProps.current?.onBack as () => void)()
    ;(setupProps.current?.onContinue as () => void)()
    expect(onBack).toHaveBeenCalledOnce()
    expect(onContinue).toHaveBeenCalledOnce()
  })
})
