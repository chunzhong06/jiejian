import { beforeEach, describe, expect, it, vi } from 'vitest'
import { onboardingApi } from './onboarding'
import { request } from './http'

vi.mock('./http', () => ({ request: vi.fn() }))

describe('onboardingApi demo', () => {
  beforeEach(() => vi.clearAllMocks())

  it('sends the explicit versioned demo variant request', async () => {
    vi.mocked(request).mockResolvedValue({} as never)

    await onboardingApi.demoStart('inconclusive')

    expect(request).toHaveBeenCalledWith('/api/onboarding/demo/start', {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', variant: 'inconclusive' }),
    })
  })
})
