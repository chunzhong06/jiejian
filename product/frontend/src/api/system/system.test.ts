// 验证系统维护写请求保留独立 HTTP 根消息版本。

import { afterEach, describe, expect, it, vi } from 'vitest'

import { systemApi } from './system'


describe('系统维护 API', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('为本地维护操作注入请求根版本', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ schema_version: '1', data: {} }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await systemApi.maintenanceOperation('clear-logs', { confirmed: true, dry_run: false, plan_id: 'plan_1' })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/system/maintenance/clear-logs',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          schema_version: '1',
          confirmed: true,
          dry_run: false,
          plan_id: 'plan_1',
        }),
      }),
    )
  })
})
