// 只读同步调度：请求串行执行，暂时失败退避重试，页面恢复可见时立即核对；绝不重放写操作。
import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/http'

export function useLiveRead(key: string | undefined, read: () => Promise<boolean | void>, interval = 5000, immediate = true) {
  const reader = useRef(read)
  reader.current = read
  const [retrying, setRetrying] = useState(false)
  const [stopped, setStopped] = useState(false)
  const [updatedAt, setUpdatedAt] = useState<number>()
  useEffect(() => {
    if (!key) return
    let disposed = false, pending = false, finished = false, failures = 0
    let timer: ReturnType<typeof setTimeout> | undefined
    setRetrying(false); setStopped(false); setUpdatedAt(undefined)
    const run = async () => {
      if (disposed || pending || finished || document.visibilityState === 'hidden') return
      clearTimeout(timer); pending = true
      try {
        const keepReading = await reader.current()
        if (disposed) return
        failures = 0; setRetrying(false); setUpdatedAt(Date.now())
        finished = keepReading === false
      } catch (error) {
        if (disposed) return
        failures += 1; setRetrying(true)
        // 所属对象或协议校验失败不能当网络波动反复尝试。
        if (error instanceof ApiError && ['STATE_PRECONDITION', 'ARTIFACT_MANIFEST', 'API_VERSION_UNSUPPORTED', 'UNAUTHORIZED', 'FORBIDDEN'].includes(error.code)) {
          finished = true; setStopped(true)
        }
      } finally {
        pending = false
        if (!disposed && !finished) timer = setTimeout(() => void run(), Math.min(30000, interval * 2 ** Math.min(failures, 3)))
      }
    }
    const resume = () => { if (document.visibilityState !== 'hidden') void run() }
    window.addEventListener('focus', resume)
    window.addEventListener('online', resume)
    document.addEventListener('visibilitychange', resume)
    if (immediate) void run()
    else timer = setTimeout(() => void run(), interval)
    return () => {
      disposed = true; clearTimeout(timer)
      window.removeEventListener('focus', resume)
      window.removeEventListener('online', resume)
      document.removeEventListener('visibilitychange', resume)
    }
  }, [key, interval, immediate])
  return { retrying, stopped, updatedAt }
}
