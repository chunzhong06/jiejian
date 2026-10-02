// 当前页面的编译身份独立于后端版本；缺少任一侧身份时不宣称已经最新。
import type { SystemStatus } from '../api/system'

declare const __JIEJIAN_FRONTEND_BUILD_ID__: string
export const frontendBuildId = typeof __JIEJIAN_FRONTEND_BUILD_ID__ === 'string' ? __JIEJIAN_FRONTEND_BUILD_ID__ : null
export function frontendIdentityState(served: SystemStatus['frontend_identity'], loaded = frontendBuildId) {
  if (served?.status !== 'CONFIRMED' || !served.build_id || !loaded) return 'UNCONFIRMED'
  return served.build_id === loaded ? 'CURRENT' : 'UPDATE_AVAILABLE'
}
