// 产品主题上下文：保存用户选择、跟随系统变化，并让 Ant Design 与自有 CSS 使用同一解析结果。

import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from 'react'
import { createProductTheme, type ResolvedTheme } from './theme'
import { productCssVariables } from '../shared/ui/tokens'

export type ThemeMode = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'jiejian.theme'
const ThemeModeContext = createContext({
  mode: 'system' as ThemeMode,
  resolved: 'light' as ResolvedTheme,
  setMode: (_mode: ThemeMode) => {},
})

function storedMode(): ThemeMode {
  const value = window.localStorage.getItem(STORAGE_KEY)
  return value === 'light' || value === 'dark' || value === 'system' ? value : 'system'
}

export function ProductThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(storedMode)
  const [systemDark, setSystemDark] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches)
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const resolved: ResolvedTheme = mode === 'system' ? (systemDark ? 'dark' : 'light') : mode

  useEffect(() => {
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches)
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onMotionChange = (event: MediaQueryListEvent) => setReducedMotion(event.matches)
    query.addEventListener('change', onChange)
    motion.addEventListener('change', onMotionChange)
    return () => { query.removeEventListener('change', onChange); motion.removeEventListener('change', onMotionChange) }
  }, [])

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, mode)
    document.documentElement.dataset.theme = resolved
    document.documentElement.style.colorScheme = resolved
    Object.entries(productCssVariables(resolved)).forEach(([key, value]) => document.documentElement.style.setProperty(key, value))
  }, [mode, resolved])

  const value = useMemo(() => ({ mode, resolved, setMode }), [mode, resolved])
  // 组件库必须知道动效已关闭，才能立即卸载退出中的图标与浮层；仅截断CSS会留下可访问残影。
  const productTheme = useMemo(() => {
    const current = createProductTheme(resolved)
    return {...current, token: {...current.token, motion: !reducedMotion}}
  }, [resolved, reducedMotion])
  return <ThemeModeContext.Provider value={value}>
    <ConfigProvider locale={zhCN} theme={productTheme}>{children}</ConfigProvider>
  </ThemeModeContext.Provider>
}

export function useThemeMode() {
  return useContext(ThemeModeContext)
}
