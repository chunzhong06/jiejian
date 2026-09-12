// 产品主题：为亮暗两套语义令牌提供同一 Ant Design 投影，不承载页面业务状态。

import { theme as antdTheme, type ThemeConfig } from 'antd'
import { designTokens, metrics } from '../shared/ui/tokens'

export type ResolvedTheme = 'light' | 'dark'

export const lightDesignTokens = designTokens('light')
export const darkDesignTokens = designTokens('dark')

export function createProductTheme(mode: ResolvedTheme): ThemeConfig {
  const designTokens = mode === 'dark' ? darkDesignTokens : lightDesignTokens
  return {
    algorithm: mode === 'dark'
      ? [antdTheme.darkAlgorithm, antdTheme.compactAlgorithm]
      : [antdTheme.defaultAlgorithm, antdTheme.compactAlgorithm],
    token: {
      colorPrimary: designTokens.primary,
      colorInfo: designTokens.evidence,
      colorSuccess: designTokens.safeInk,
      colorWarning: designTokens.warningInk,
      colorError: designTokens.dangerInk,
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
      colorPrimaryText: designTokens.primary,
      colorTextLightSolid: designTokens.onAccent,
      borderRadius: metrics.radius.medium,
      borderRadiusLG: metrics.radius.large,
      borderRadiusSM: metrics.radius.small,
      fontSize: metrics.font.body,
      fontFamily: metrics.sans,
      fontFamilyCode: metrics.mono,
      fontWeightStrong: 600,
      lineHeight: 1.57,
      controlHeight: metrics.control.normal,
      controlHeightLG: metrics.control.large,
      controlHeightSM: metrics.control.small,
    },
    components: {
      Button: { borderRadius: metrics.radius.medium, controlHeight: metrics.control.normal, controlHeightLG: metrics.control.large, controlHeightSM: metrics.control.small, paddingInline: 14, primaryShadow: 'none' },
      Card: { bodyPadding: 20, bodyPaddingSM: 16, headerBg: designTokens.surface, headerHeight: 44 },
      Input: {
        activeBg: designTokens.elevated,
        activeBorderColor: designTokens.primary,
        colorBgContainer: designTokens.elevated,
        colorBorder: designTokens.borderSecondary,
        controlHeight: metrics.control.normal,
        hoverBorderColor: designTokens.primary,
      },
      Layout: { bodyBg: designTokens.background, headerBg: designTokens.surface, siderBg: designTokens.surface },
      Menu: { itemBg: designTokens.surface, itemSelectedBg: designTokens.selected, itemSelectedColor: designTokens.primary },
      Segmented: { itemSelectedBg: designTokens.elevated, trackBg: designTokens.fillSecondary, trackPadding: 2 },
      Select: {
        activeBorderColor: designTokens.primary,
        colorBgContainer: designTokens.elevated,
        colorBorder: designTokens.borderSecondary,
        controlHeight: metrics.control.normal,
        optionSelectedBg: designTokens.selected,
      },
      Tag: { borderRadiusSM: 999, defaultBg: designTokens.fillSecondary, defaultColor: designTokens.secondary },
    },
  }
}
