// 授权工作面回读真实应用列表，覆盖跨标签页接入、空态、失败及精确项目授权。
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ToolsPage } from './ToolsPage'

const api = vi.hoisted(() => ({ projects: vi.fn(), status: vi.fn(), grant: vi.fn() }))
vi.mock('../../api/applications/projects', () => ({ projectsApi: { projects: api.projects } }))
vi.mock('../../api/system/mcp', async () => ({
  ...await vi.importActual<typeof import('../../api/system/mcp')>('../../api/system/mcp'),
  mcpAccessApi: { status: api.status, setProjectAccess: api.grant },
}))
const access = { schema_version:'1', paired:true, accepting_connections:true, connection_state:'CONNECTED', project_grants:[], client_name:'dsh-mcp-client' }
const project = { project_id:'gallery', name:'数字展馆' }
beforeEach(() => { vi.resetAllMocks(); api.status.mockResolvedValue(access); api.projects.mockResolvedValue([project]); api.grant.mockResolvedValue({...access,project_grants:[{project_id:'gallery',level:'PREPARE'}]}) })
afterEach(cleanup)

it('壳层列表为空时仍从服务端读取应用，并只保存用户选定项目的权限', async () => {
  render(<ToolsPage projects={[]} onError={vi.fn()}/> )
  expect(await screen.findByText('数字展馆')).toBeInTheDocument()
  const button = screen.getByRole('button',{name:'调整这次允许范围'})
  await waitFor(() => expect(button).toBeEnabled())
  expect(api.grant).not.toHaveBeenCalled()
  fireEvent.click(button); fireEvent.click(screen.getByRole('radio',{name:'协助整理'}))
  fireEvent.click(screen.getByRole('button',{name:'保存这次允许范围'}))
  await waitFor(() => expect(api.grant).toHaveBeenCalledWith('gallery','PREPARE'))
  expect(document.querySelector('.module-navigation')).not.toBeInTheDocument()
})

it('只有读取成功的空列表才显示接入入口，返回页面后自动发现新应用', async () => {
  let finish!:(value:unknown)=>void
  api.projects.mockImplementationOnce(() => new Promise(resolve => { finish=resolve }))
  render(<ToolsPage projects={[]} onError={vi.fn()}/> )
  expect(screen.getByText('正在读取可授权的应用…')).toBeInTheDocument()
  expect(screen.queryByRole('link',{name:'接入应用'})).not.toBeInTheDocument()
  await act(async () => finish([]))
  expect(screen.getByRole('link',{name:'接入应用'})).toHaveAttribute('href','#/application?new=1')
  fireEvent.focus(window)
  expect(await screen.findByText('数字展馆')).toBeInTheDocument()
  expect(screen.queryByRole('link',{name:'接入应用'})).not.toBeInTheDocument()
})

it('读取失败不冒充没有应用，刷新列表可恢复', async () => {
  api.projects.mockRejectedValueOnce(new Error('offline'))
  render(<ToolsPage projects={[]} onError={vi.fn()}/> )
  expect(await screen.findByText('应用列表读取失败，请刷新应用列表后重试。')).toBeInTheDocument()
  expect(screen.queryByRole('link',{name:'接入应用'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'刷新应用列表'}))
  expect(await screen.findByText('数字展馆')).toBeInTheDocument()
})

it('旧读取迟到不覆盖手动刷新得到的新列表', async () => {
  let old!:(value:unknown)=>void
  api.projects.mockImplementationOnce(() => new Promise(resolve => { old=resolve }))
  render(<ToolsPage projects={[]} onError={vi.fn()}/> )
  fireEvent.click(screen.getByRole('button',{name:'刷新应用列表'}))
  expect(await screen.findByText('数字展馆')).toBeInTheDocument()
  await act(async () => old([]))
  expect(screen.getByText('数字展馆')).toBeInTheDocument()
})
