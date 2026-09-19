// 只读材料页的快照隔离、未知能力与读取恢复，避免把陈旧材料展示为当前事实。
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { EvidenceMaterialDetail } from '../../api/preparation'
import { EvidenceMaterials } from './EvidenceMaterials'
const api = vi.hoisted(() => ({ evidence: vi.fn() }))
vi.mock('../../api/preparation', () => ({ preparationApi: api }))
const detail = (project = 'p1'): EvidenceMaterialDetail => ({ project_id: project, action_id: 'a1', action_revision: 1, action_label: '导出资料', effects: [
  { effect_id: 'e1', business_label: '导出文件形成', resource_concept: '项目文件', material_status: 'SATISFIED', binding_fingerprint: 'fp1', source_kind: 'REGISTERED_OBSERVER', source_label: '已绑定的受控来源', registered_source_available: true, closure_supported: true, resource_correlation_supported: null, reason_codes: [] },
  { effect_id: 'e2', business_label: '通知形成', resource_concept: '通知', material_status: 'NEEDS_USER', binding_fingerprint: null, source_kind: null, source_label: '尚无证明材料', registered_source_available: null, closure_supported: null, resource_correlation_supported: null, reason_codes: ['EFFECT_EVIDENCE_REQUIRED'] },
] })
beforeEach(() => { vi.resetAllMocks(); api.evidence.mockResolvedValue(detail()) })
describe('证明材料只读说明', () => {
  it('按业务结果切换，未知能力不显示为支持，也没有保存或执行按钮', async () => {
    render(<EvidenceMaterials projectId="p1" actionId="a1" onBack={vi.fn()} />)
    const article = await screen.findByRole('article', { name: '导出文件形成的证明材料' })
    expect(within(article).getByText('尚不能确认')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /通知形成/ }))
    expect(screen.getByRole('article', { name: '通知形成的证明材料' })).toHaveTextContent('尚无证明材料')
    expect(screen.queryByRole('button', { name: /保存|开始检查|录制/ })).not.toBeInTheDocument()
    expect(api.evidence).toHaveBeenCalledOnce()
  })
  it('失败刷新撤下旧快照，成功重读恢复所选结果', async () => {
    render(<EvidenceMaterials projectId="p1" actionId="a1" onBack={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /通知形成/ }))
    api.evidence.mockRejectedValueOnce(new Error('private reader details'))
    fireEvent.click(screen.getByRole('button', { name: '刷新材料详情' }))
    expect(await screen.findByText('材料详情暂时无法读取')).toBeInTheDocument()
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    expect(screen.queryByText('private reader details')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '刷新材料详情' }))
    expect(await screen.findByRole('article', { name: '通知形成的证明材料' })).toBeInTheDocument()
  })
  it('跨项目迟到响应不能覆盖新项目材料', async () => {
    let resolve!: (value: EvidenceMaterialDetail) => void
    api.evidence.mockImplementationOnce(() => new Promise(done => { resolve = done }))
    const view = render(<EvidenceMaterials projectId="p1" actionId="a1" onBack={vi.fn()} />)
    api.evidence.mockResolvedValue(detail('p2'))
    view.rerender(<EvidenceMaterials projectId="p2" actionId="a1" onBack={vi.fn()} />)
    await screen.findByRole('article')
    const old = detail(); old.action_label = '过期项目'
    await act(async () => resolve(old))
    expect(screen.queryByText('过期项目')).not.toBeInTheDocument()
    expect(screen.getByRole('article')).toHaveTextContent('导出文件形成')
  })
  it('归属不匹配的响应不展示', async () => {
    api.evidence.mockResolvedValue(detail('other'))
    render(<EvidenceMaterials projectId="p1" actionId="a1" onBack={vi.fn()} />)
    expect(await screen.findByText('材料详情暂时无法读取')).toBeInTheDocument()
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })
  it('快照漂移只表示尚未确认，不误报材料不存在', async () => {
    const value = detail(); value.effects = [{...value.effects[1], material_status:'STALE', reason_codes:['EVIDENCE_SNAPSHOT_CHANGED']}]
    api.evidence.mockResolvedValue(value)
    render(<EvidenceMaterials projectId="p1" actionId="a1" onBack={vi.fn()} />)
    expect(await screen.findByRole('article')).toHaveTextContent('材料快照需要重新读取')
    expect(screen.queryByText('尚无证明材料')).not.toBeInTheDocument()
  })
  it('来源失效明确显示，不以能力声明掩盖材料失效', async () => {
    const value = detail(); Object.assign(value.effects[0], { material_status: 'STALE', registered_source_available: false, closure_supported: null, reason_codes: ['REGISTERED_OBSERVER_UNAVAILABLE'] })
    api.evidence.mockResolvedValue(value)
    render(<EvidenceMaterials projectId="p1" actionId="a1" onBack={vi.fn()} />)
    const article = await screen.findByRole('article')
    expect(article).toHaveTextContent('材料需要更新')
    expect(article).toHaveTextContent('历史结果仍保留原有证据')
  })
})
