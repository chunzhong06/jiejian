// 产品主题：把统一设计 token 投影到 Ant Design，不承载页面业务状态。

import type { ThemeConfig } from 'antd'

export const designTokens = {
  primary: '#3659D9',
  safe: '#188765',
  warning: '#A8660C',
  danger: '#C83C3C',
  text: '#172033',
  secondary: '#667085',
  surface: '#FFFFFF',
  background: '#F4F6F9',
  border: '#DFE4EC',
} as const

export const productTheme: ThemeConfig = {
  token: {
    colorPrimary: designTokens.primary,
    colorInfo: designTokens.primary,
    colorSuccess: designTokens.safe,
    colorWarning: designTokens.warning,
    colorError: designTokens.danger,
    colorText: designTokens.text,
    colorTextSecondary: designTokens.secondary,
    colorBgBase: designTokens.surface,
    colorBgLayout: designTokens.background,
    colorBorder: designTokens.border,
    colorLink: designTokens.primary,
    borderRadius: 12,
    fontSize: 14,
    fontFamily: '"Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", "Segoe UI", sans-serif',
    controlHeight: 40,
  },
  components: {
    Button: { primaryShadow: 'none' },
    Card: { headerBg: designTokens.surface },
    Layout: { bodyBg: designTokens.background, headerBg: designTokens.surface, siderBg: designTokens.surface },
    Menu: { itemBg: designTokens.surface, itemSelectedBg: '#EEF2FF', itemSelectedColor: designTokens.primary },
  },
}
