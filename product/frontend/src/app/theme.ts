// 产品主题：为亮暗两套语义令牌提供同一 Ant Design 投影，不承载页面业务状态。

import { theme as antdTheme, type ThemeConfig } from 'antd'

export type ResolvedTheme = 'light' | 'dark'

export const lightDesignTokens = {
  primary: '#176A73', safe: '#3E7C6B', warning: '#98653F', danger: '#A85F50',
  text: '#183438', secondary: '#667D80', surface: '#FCFEFD', elevated: '#FFFFFF', background: '#F1F6F6',
  border: '#CBDDDD', borderSecondary: '#DCE9E9', fillSecondary: '#E7F0F0', fillTertiary: '#F3F8F7',
  disabled: '#8DA2A3', outline: 'rgba(23, 106, 115, .22)', selected: '#E2F0F1',
} as const

export const darkDesignTokens = {
  primary: '#7EB9BE', safe: '#76B29C', warning: '#D1A37A', danger: '#D38E7B',
  text: '#EDF4F3', secondary: '#A4B6B5', surface: '#142124', elevated: '#19292C', background: '#0E1719',
  border: '#294348', borderSecondary: '#355157', fillSecondary: '#203438', fillTertiary: '#192A2E',
  disabled: '#72898A', outline: 'rgba(126, 185, 190, .30)', selected: '#1C3438',
} as const

export function createProductTheme(mode: ResolvedTheme): ThemeConfig {
  const designTokens = mode === 'dark' ? darkDesignTokens : lightDesignTokens
  return {
    algorithm: mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
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
      colorBgContainer: designTokens.surface,
      colorBgElevated: designTokens.elevated,
      colorBorder: designTokens.border,
      colorBorderSecondary: designTokens.borderSecondary,
      colorFillSecondary: designTokens.fillSecondary,
      colorFillTertiary: designTokens.fillTertiary,
      colorTextDisabled: designTokens.disabled,
      controlOutline: designTokens.outline,
      colorLink: designTokens.primary,
      borderRadius: 12,
      fontSize: 14,
      fontFamily: '"Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", "Segoe UI", sans-serif',
      controlHeight: 40,
    },
    components: {
      Button: { primaryShadow: 'none' },
      Card: { headerBg: designTokens.surface },
      Input: {
        activeBg: designTokens.elevated,
        activeBorderColor: designTokens.primary,
        colorBgContainer: designTokens.elevated,
        colorBorder: mode === 'dark' ? '#416268' : '#B8CDCE',
        hoverBorderColor: designTokens.primary,
      },
      Layout: { bodyBg: designTokens.background, headerBg: designTokens.surface, siderBg: designTokens.surface },
      Menu: { itemBg: designTokens.surface, itemSelectedBg: designTokens.selected, itemSelectedColor: designTokens.primary },
      Select: {
        activeBorderColor: designTokens.primary,
        colorBgContainer: designTokens.elevated,
        colorBorder: mode === 'dark' ? '#416268' : '#B8CDCE',
        optionSelectedBg: designTokens.selected,
      },
    },
  }
}
