// 验证前端只接受当前 API 根消息版本，并保留后端脱敏错误语义。

import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, request } from './http'


function response(body: unknown, options: { ok?: boolean } = {}): Response {
  return {
    ok: options.ok ?? true,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response
}


describe('HTTP API 根消息', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('解包当前版本 1 的成功响应', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ schema_version: '1', data: { status: 'ok' } })))

    await expect(request<{ status: string }>('/api/system/status')).resolves.toEqual({ status: 'ok' })
  })

  it('拒绝未知或缺失的最外层版本', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ schema_version: '2', data: {} })))

    await expect(request('/api/system/status')).rejects.toMatchObject({
      code: 'API_VERSION_UNSUPPORTED',
    })
  })

  it('在版本有效时保留后端错误代码和 trace', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      schema_version: '1',
      error: { code: 'INPUT_INVALID', message: '请求参数无效' },
      trace_id: 'tr_test',
    }, { ok: false })))

    await expect(request('/api/system/status')).rejects.toEqual(
      new ApiError('INPUT_INVALID', '请求参数无效', 'tr_test'),
    )
  })
})
