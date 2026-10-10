// 验证运行身份、清理预览、按项选择和未知回执的只读恢复。

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { systemApi, SystemStatus, type MaintenanceOperationResult } from '../../api/system/system'
import { RuntimePage } from './RuntimePage'

const maintenanceStatus = {
  schema_version: '1' as const,
  entries: {
    assistant: { path: 'D:/jiejian/var/cache/assistant', bytes: 1024, files: 1 },
    logs: { path: 'D:/jiejian/var/logs', bytes: 2048, files: 2, categories: { app: { path: 'D:/jiejian/var/logs/app', bytes: 2048, files: 2 } } },
    temporary: { path: 'D:/jiejian/var', bytes: 3072, files: 3 },
  },
  protected: {
    data: 'D:/jiejian/var/data',
    applications: true, permissions: true, database: true, evidence: true, reports: true,
    credentials: true, active_runtime: true, current_session_logs: true, development_root_included: false,
  },
  inventory: [
    {category:'assistant',label:'AI 辅助缓存',relative_path:'cache/assistant/one',state:'CLEANABLE' as const,reason:'闲置',bytes:1024,files:1},
    {category:'logs',label:'历史日志',relative_path:'logs/app/old',state:'CLEANABLE' as const,reason:'已关闭',bytes:2048,files:2},
    {category:'temporary',label:'运行临时文件',relative_path:'temp/old',state:'CLEANABLE' as const,reason:'已退出',bytes:3072,files:3},
    {category:'builds',label:'当前构建',relative_path:'runtime/frontend',state:'PROTECTED' as const,reason:'当前界面使用',bytes:4000,files:2},
    {category:'temporary',label:'未登记',relative_path:'temp/unknown',state:'UNKNOWN' as const,reason:'缺少来源证明',bytes:null,files:null},
  ],
}

const status: SystemStatus = {
  version: '1.1.0',
  api: 'available',
  worker: 'unavailable',
  browser: 'available',
  environment: {
    runtime_mode: 'development',
    runtime_fingerprint: 'fingerprint',
    python: { ok: true, version: '3.13.15', environment_type: 'conda', executable: 'D:/runtime/python.exe', prefix: 'D:/runtime', user_site_on_sys_path: false },
    uv: { version: '0.11.12', executable: 'D:/runtime/uv.exe' },
    node: { required: false, version: '24.19.0', executable: 'D:/runtime/node.exe' },
    pnpm: { required: false, version: '11.21.0', executable: 'D:/runtime/pnpm.cjs' },
    playwright: { package_version: '1.61.0', chromium_executable: 'D:/runtime/chromium.exe' },
    frontend: { mode: 'source-build', dist: 'D:/jiejian/var/runtime/frontend', build_state: 'reused' },
  },
}

describe('RuntimePage', () => {
  afterEach(() => {vi.restoreAllMocks();sessionStorage.clear()})

  it('展示三类本地运行数据并以预览确认清理', async () => {
    vi.spyOn(systemApi, 'maintenanceStatus').mockResolvedValue(maintenanceStatus)
    vi.spyOn(systemApi, 'maintenanceOperation').mockResolvedValue({
      schema_version: '1',
      plan_id: 'plan_1',
      scope: 'clear-all',
      operation: 'clear-all',
      generated_at_us: 100,
      expires_at_us: 200,
      dry_run: true,
      estimated_bytes: 6144,
      targets: [{ item_id: 'item_1', label: 'AI 辅助缓存：one', relative_path: 'cache/assistant/one', estimated_bytes: 1024 }],
      removed: [],
      results: [],
      counts: { DELETED: 0, ALREADY_MISSING: 0, SKIPPED_IN_USE: 0, SKIPPED_CHANGED: 0, FAILED: 0 },
      protected: maintenanceStatus.protected,
      status: maintenanceStatus,
    })

    render(<RuntimePage status={status} />)

    expect(screen.getByText('1.1.0')).toBeInTheDocument()
    expect(screen.getByText('检查执行器当前不可用。')).toBeInTheDocument()
    expect(screen.getByText('不可用')).toBeInTheDocument()
    expect(screen.getAllByText(/仅构建时需要/)).toHaveLength(1)
    expect(screen.getByText(/受控本地应用运行时/)).toHaveTextContent('D:/runtime/node.exe')
    expect(screen.getByText(/源码构建/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('1.0 KiB')).toBeInTheDocument())
    expect(screen.getByText('AI 辅助缓存')).toBeInTheDocument()
    expect(screen.getByText('历史日志')).toBeInTheDocument()
    expect(screen.getByText('运行临时文件')).toBeInTheDocument()
    expect(screen.queryByText('预算内')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '预览清理' }))
    await waitFor(() => expect(systemApi.maintenanceOperation).toHaveBeenCalledWith('clear-all', { confirmed: false, dry_run: true }))
    expect(await screen.findByText(/已选 1 项/)).toBeInTheDocument()
    expect(screen.getByText(/确认时只处理这份计划/)).toBeInTheDocument()
    expect(screen.getByText(/cache\/assistant\/one/)).toBeInTheDocument()
    expect(screen.getByText(/保留应用、权限、检查历史和准备材料/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '清理所选' }))
    await waitFor(() => expect(systemApi.maintenanceOperation).toHaveBeenCalledWith('clear-all', { confirmed: true, dry_run: false, plan_id: 'plan_1',item_ids:['item_1'] }))
  })
})

it('首次读取失败不显示零值，恢复读取后撤下错误并恢复维护入口', async () => {
  const read = vi.spyOn(systemApi, 'maintenanceStatus').mockRejectedValueOnce(new Error('Failed to fetch')).mockResolvedValue(maintenanceStatus)
  render(<RuntimePage status={status}/>)
  expect(await screen.findByText('扫描暂时失败')).toBeInTheDocument()
  expect(screen.queryByText('0 B')).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'预览清理'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'重新扫描'}))
  await waitFor(() => expect(screen.queryByText('扫描暂时失败')).not.toBeInTheDocument())
  expect(screen.getByRole('button',{name:'预览清理'})).toBeEnabled()
  expect(read).toHaveBeenCalledTimes(2)
})

it('只提交选中项目，未知回执跨刷新后仅查询结果', async()=>{
  sessionStorage.clear()
  vi.spyOn(systemApi,'maintenanceStatus').mockResolvedValue(maintenanceStatus)
  const plan:MaintenanceOperationResult={schema_version:'1',plan_id:'recover-plan',scope:'clear-all',operation:'clear-all',generated_at_us:1,expires_at_us:9999,dry_run:true,estimated_bytes:300,
    targets:[{item_id:'one',label:'旧构建',relative_path:'frontend/old-one',estimated_bytes:100},{item_id:'two',label:'下载缓存',relative_path:'cache/old-two',estimated_bytes:200}],
    removed:[],results:[],counts:{DELETED:0,ALREADY_MISSING:0,SKIPPED_IN_USE:0,SKIPPED_CHANGED:0,FAILED:0},protected:maintenanceStatus.protected,status:maintenanceStatus}
  const write=vi.spyOn(systemApi,'maintenanceOperation').mockResolvedValueOnce(plan).mockRejectedValueOnce(new Error('response lost'))
  const read=vi.spyOn(systemApi,'maintenanceOutcome').mockResolvedValue({state:'COMPLETED',result:{...plan,dry_run:false,counts:{...plan.counts,DELETED:1}}})
  const view=render(<RuntimePage status={status}/>)
  fireEvent.click(await screen.findByRole('button',{name:'预览清理'}))
  fireEvent.click(await screen.findByRole('checkbox',{name:/下载缓存/}))
  fireEvent.click(screen.getByRole('button',{name:'清理所选'}))
  expect(await screen.findByText('清理结果待确认')).toBeInTheDocument()
  expect(write).toHaveBeenLastCalledWith('clear-all',{confirmed:true,dry_run:false,plan_id:'recover-plan',item_ids:['one']})
  view.unmount()
  render(<RuntimePage status={status}/>)
  fireEvent.click(await screen.findByRole('button',{name:'读取本次清理结果'}))
  expect(await screen.findByText('本次清理已完成')).toBeInTheDocument()
  expect(read).toHaveBeenCalledWith('recover-plan')
  expect(write).toHaveBeenCalledTimes(2)
  expect(sessionStorage.getItem('jiejian.maintenance.pending')).toBeNull()
  vi.restoreAllMocks()
})
