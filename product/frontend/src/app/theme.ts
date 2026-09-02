// 产品主题：为亮暗两套语义令牌提供同一 Ant Design 投影，不承载页面业务状态。

import { theme as antdTheme, type ThemeConfig } from 'antd'

export type ResolvedTheme = 'light' | 'dark'

export const lightDesignTokens = {
  primary: '#0C6670', evidence: '#2F67D8', safe: '#187A57', warning: '#A56624', danger: '#B64A42',
  text: '#13191C', secondary: '#5E696E', surface: '#FFFFFF', elevated: '#FFFFFF', background: '#F6F7F8',
  border: '#E0E5E7', borderSecondary: '#CDD4D7', fillSecondary: '#F1F3F4', fillTertiary: '#ECEFF1',
  disabled: '#879197', outline: 'rgba(12, 102, 112, .18)', selected: '#E9F3F4',
} as const

export const darkDesignTokens = {
  primary: '#6BB5BC', evidence: '#79A0FF', safe: '#62B491', warning: '#D1A05F', danger: '#DF887E',
  text: '#F2F4F5', secondary: '#A5AFB3', surface: '#151A1D', elevated: '#1B2226', background: '#0E1214',
  border: '#293237', borderSecondary: '#38434A', fillSecondary: '#1B2226', fillTertiary: '#222B30',
  disabled: '#768389', outline: 'rgba(107, 181, 188, .24)', selected: '#183338',
} as const

export function createProductTheme(mode: ResolvedTheme): ThemeConfig {
  const designTokens = mode === 'dark' ? darkDesignTokens : lightDesignTokens
  return {
    algorithm: mode === 'dark'
      ? [antdTheme.darkAlgorithm, antdTheme.compactAlgorithm]
      : [antdTheme.defaultAlgorithm, antdTheme.compactAlgorithm],
    token: {
      colorPrimary: designTokens.primary,
      colorInfo: designTokens.evidence,
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
      borderRadius: 8,
      borderRadiusLG: 12,
      borderRadiusSM: 7,
      fontSize: 14,
      fontFamily: '"Segoe UI Variable", "PingFang SC", "Microsoft YaHei UI", "Noto Sans SC", system-ui, sans-serif',
      fontFamilyCode: '"SFMono-Regular", "Cascadia Code", Consolas, monospace',
      fontWeightStrong: 600,
      lineHeight: 1.57,
      controlHeight: 34,
      controlHeightLG: 36,
      controlHeightSM: 28,
    },
    components: {
      Button: { borderRadius: 8, controlHeight: 34, controlHeightLG: 36, controlHeightSM: 28, paddingInline: 14, primaryShadow: 'none' },
      Card: { bodyPadding: 20, bodyPaddingSM: 16, headerBg: designTokens.surface, headerHeight: 44 },
      Input: {
        activeBg: designTokens.elevated,
        activeBorderColor: designTokens.primary,
        colorBgContainer: designTokens.elevated,
        colorBorder: designTokens.borderSecondary,
        controlHeight: 34,
        hoverBorderColor: designTokens.primary,
      },
      Layout: { bodyBg: designTokens.background, headerBg: designTokens.surface, siderBg: designTokens.surface },
      Menu: { itemBg: designTokens.surface, itemSelectedBg: designTokens.selected, itemSelectedColor: designTokens.primary },
      Segmented: { itemSelectedBg: designTokens.elevated, trackBg: designTokens.fillSecondary, trackPadding: 2 },
      Select: {
        activeBorderColor: designTokens.primary,
        colorBgContainer: designTokens.elevated,
        colorBorder: designTokens.borderSecondary,
        controlHeight: 34,
        optionSelectedBg: designTokens.selected,
      },
      Tag: { borderRadiusSM: 999, defaultBg: designTokens.fillSecondary, defaultColor: designTokens.secondary },
    },
  }
}
