// 验证运行环境页对版本、运行身份和三类本地运行数据维护事实的展示与交互。

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { systemApi, SystemStatus } from '../../api/system'
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
}

const status: SystemStatus = {
  version: '1.0.5',
  api: 'available',
  worker: 'running',
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
  afterEach(() => vi.restoreAllMocks())

  it('展示三类本地运行数据并以预览确认清理', async () => {
    vi.spyOn(systemApi, 'maintenanceStatus').mockResolvedValue(maintenanceStatus)
    vi.spyOn(systemApi, 'maintenanceOperation').mockResolvedValue({
      schema_version: '1',
      operation: 'clear-all',
      dry_run: true,
      estimated_bytes: 6144,
      targets: [{ path: 'D:/jiejian/var/cache/assistant/one', estimated_bytes: 1024 }],
      removed: [],
      protected: maintenanceStatus.protected,
      status: maintenanceStatus,
    })

    render(<RuntimePage status={status} profiles={[]} failed={false} />)

    expect(screen.getByText('1.0.5')).toBeInTheDocument()
    expect(screen.getAllByText(/仅构建时需要/)).toHaveLength(2)
    expect(screen.getByText(/源码构建/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('1.0 KiB')).toBeInTheDocument())
    expect(screen.getByText('AI 辅助缓存')).toBeInTheDocument()
    expect(screen.getByText('历史运行日志')).toBeInTheDocument()
    expect(screen.getByText('临时运行文件')).toBeInTheDocument()
    expect(screen.queryByText('预算内')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '清理全部可删除内容' }))
    await waitFor(() => expect(systemApi.maintenanceOperation).toHaveBeenCalledWith('clear-all', { confirmed: false, dry_run: true }))
    expect(await screen.findByText(/预计处理 1 项/)).toBeInTheDocument()
    expect(screen.getByText(/不会删除应用、权限配置、数据库、证据、报告和凭据/)).toBeInTheDocument()
  })
})
