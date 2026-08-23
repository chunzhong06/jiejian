import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { systemApi, SystemStatus } from '../../api/system'
import { RuntimePage } from './RuntimePage'

const cacheStatus = {
  schema_version: '1' as const,
  entries: {
    uv: { path: 'D:/jiejian/var/cache/uv', bytes: 1024, files: 1, budget: 2048, over_budget: false },
    vite: { path: 'D:/jiejian/var/cache/vite', bytes: 0, files: 0, budget: 2048, over_budget: false },
  },
  protected: {
    data: 'D:/jiejian/var/data',
    data_unchanged: true,
    current_runtime_unchanged_by_cache: true,
  },
}

const status: SystemStatus = {
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

  it('展示源码运行身份并通过同一 API 预览缓存维护', async () => {
    vi.spyOn(systemApi, 'cacheStatus').mockResolvedValue(cacheStatus)
    vi.spyOn(systemApi, 'cacheOperation').mockResolvedValue({
      schema_version: '1',
      operation: 'prune',
      dry_run: true,
      estimated_bytes: 1024,
      targets: [{ path: 'D:/jiejian/var/cache/uv', estimated_bytes: 1024 }],
      removed: [],
      protected: cacheStatus.protected,
      status: cacheStatus,
    })

    render(<RuntimePage status={status} profiles={[]} failed={false} />)

    expect(screen.getAllByText(/仅构建时需要/)).toHaveLength(2)
    expect(screen.getByText(/源码构建/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('1.0 KiB')).toBeInTheDocument())
    expect(screen.getByText('Vite 缓存')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '按预算清理' }))
    await waitFor(() => expect(systemApi.cacheOperation).toHaveBeenCalledWith('prune', { confirmed: false, dry_run: true }))
    expect(await screen.findByText(/预计处理 1 项/)).toBeInTheDocument()
  })
})
