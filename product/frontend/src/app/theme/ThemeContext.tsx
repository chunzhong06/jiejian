// 产品主题上下文：保存用户选择、跟随系统变化，并让 Ant Design 与自有 CSS 使用同一解析结果。

import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { createContext, type ReactNode, useContext, useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { createProductTheme, type ResolvedTheme } from './theme'
import { productCssVariables } from '../../shared/ui/tokens'
import { useControlMotion } from '../../shared/ui/useControlMotion'
import { useProductMotion } from '../../shared/ui/useProductMotion'

export type ThemeMode = 'system' | 'light' | 'dark'
export type MotionMode = 'full' | 'soft' | 'off'
export type DensityMode = 'comfortable' | 'compact'

const STORAGE_KEY = 'jiejian.theme'
const ThemeModeContext = createContext({
  mode: 'system' as ThemeMode,
  resolved: 'light' as ResolvedTheme,
  setMode: (_mode: ThemeMode) => {},
  motion: 'full' as MotionMode,
  setMotion: (_mode: MotionMode) => {},
  density: 'comfortable' as DensityMode,
  setDensity: (_mode: DensityMode) => {},
})

function storedMode(): ThemeMode {
  const value = readPreference(STORAGE_KEY)
  return value === 'light' || value === 'dark' || value === 'system' ? value : 'system'
}

function readPreference(key: string) { try { return window.localStorage.getItem(key) } catch { return null } }
function savePreference(key: string, value: string) { try { window.localStorage.setItem(key, value) } catch { /* 浏览器禁止本地存储时，本次会话仍可调整显示。 */ } }

export function ProductThemeProvider({ children }: { children: ReactNode }) {
  const [motionReady, setMotionReady] = useState(false)
  useLayoutEffect(() => setMotionReady(true), [])
  const [mode, setMode] = useState<ThemeMode>(storedMode)
  const [motion, setMotion] = useState<MotionMode>(() => { const value = readPreference('jiejian.motion'); return value === 'off' || value === 'soft' ? value : 'full' })
  const [density, setDensity] = useState<DensityMode>(() => readPreference('jiejian.density') === 'compact' ? 'compact' : 'comfortable')
  const [systemDark, setSystemDark] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches)
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const resolved: ResolvedTheme = mode === 'system' ? (systemDark ? 'dark' : 'light') : mode
  const resolvedMotion = motion === 'off' ? 'off' : reducedMotion ? 'soft' : motion
  useControlMotion(resolvedMotion)
  useProductMotion(resolvedMotion)

  // Ant Design浮层挂载在body；在文档根标记作用域，使页面和Portal共用交互样式。
  useLayoutEffect(() => {
    const root = document.documentElement
    const previous = root.dataset.product
    root.dataset.product = 'jiejian'
    return () => {
      if (previous === undefined) delete root.dataset.product
      else root.dataset.product = previous
    }
  }, [])

  useEffect(() => {
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches)
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onMotionChange = (event: MediaQueryListEvent) => setReducedMotion(event.matches)
    query.addEventListener('change', onChange)
    motion.addEventListener('change', onMotionChange)
    return () => { query.removeEventListener('change', onChange); motion.removeEventListener('change', onMotionChange) }
  }, [])

  // 首次绘制前同步根主题；路由切换复用同一 Provider，不重置到亮色背景。
  useLayoutEffect(() => {
    savePreference(STORAGE_KEY, mode)
    savePreference('jiejian.motion', motion)
    savePreference('jiejian.density', density)
    document.documentElement.dataset.theme = resolved
    document.documentElement.dataset.motion = resolvedMotion
    document.documentElement.dataset.density = density
    document.documentElement.style.colorScheme = resolved
    Object.entries(productCssVariables(resolved, density)).forEach(([key, value]) => document.documentElement.style.setProperty(key, value))
  }, [mode, resolved, motion, resolvedMotion, density])

  const value = useMemo(() => ({ mode, resolved, setMode, motion, setMotion, density, setDensity }), [mode, resolved, motion, density])
  // 组件库必须知道动效已关闭，才能立即卸载退出中的图标与浮层；仅截断CSS会留下可访问残影。
  const productTheme = useMemo(() => {
    const current = createProductTheme(resolved)
    return {...current, token: {...current.token, motion: motionReady && resolvedMotion === 'full'}}
  }, [resolved, resolvedMotion, motionReady])
  // 组件库首次关闭动效才插入 MotionProvider；先建立此包装，再挂载页面，避免切换偏好时重置选择与输入。
  return <ThemeModeContext.Provider value={value}>
    <ConfigProvider locale={zhCN} theme={productTheme}>{motionReady ? children : null}</ConfigProvider>
  </ThemeModeContext.Provider>
}

export function useThemeMode() {
  return useContext(ThemeModeContext)
}
