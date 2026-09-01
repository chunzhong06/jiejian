// 产品主题上下文：保存用户选择、跟随系统变化，并让 Ant Design 与自有 CSS 使用同一解析结果。

import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from 'react'
import { createProductTheme, type ResolvedTheme } from './theme'

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
  const resolved: ResolvedTheme = mode === 'system' ? (systemDark ? 'dark' : 'light') : mode

  useEffect(() => {
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, mode)
    document.documentElement.dataset.theme = resolved
    document.documentElement.style.colorScheme = resolved
  }, [mode, resolved])

  const value = useMemo(() => ({ mode, resolved, setMode }), [mode, resolved])
  return <ThemeModeContext.Provider value={value}>
    <ConfigProvider locale={zhCN} theme={createProductTheme(resolved)}>{children}</ConfigProvider>
  </ThemeModeContext.Provider>
}

export function useThemeMode() {
  return useContext(ThemeModeContext)
}
