// 产品主题：为亮暗两套语义令牌提供同一 Ant Design 投影，不承载页面业务状态。

import { theme as antdTheme, type ThemeConfig } from 'antd'
import { designTokens, metrics } from '../shared/ui/tokens'

export type ResolvedTheme = 'light' | 'dark'

export const lightDesignTokens = designTokens('light')
export const darkDesignTokens = designTokens('dark')

export function createProductTheme(mode: ResolvedTheme): ThemeConfig {
  const designTokens = mode === 'dark' ? darkDesignTokens : lightDesignTokens
  const algorithm = mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm
  return {
    // 暗色算法会再次压暗 seed 中的品牌与状态色；保留其余派生值，再恢复已核对的语义色。
    algorithm: (seed, map) => ({ ...algorithm(seed, map), colorPrimary: designTokens.primary,
      colorInfo: designTokens.evidence, colorSuccess: designTokens.safeInk,
      colorWarning: designTokens.warningInk, colorError: designTokens.dangerInk }),
    token: {
      colorPrimary: designTokens.primary,
      colorPrimaryHover: designTokens.primaryHover,
      colorPrimaryActive: designTokens.primaryActive,
      colorPrimaryBg: designTokens.primaryLight,
      colorPrimaryBgHover: designTokens.hover,
      colorPrimaryBorder: designTokens.primaryBorder,
      colorPrimaryBorderHover: designTokens.primary,
      colorInfo: designTokens.evidence,
      colorInfoText: designTokens.evidence,
      colorSuccess: designTokens.safeInk,
      colorSuccessText: designTokens.safeInk,
      colorWarning: designTokens.warningInk,
      colorWarningText: designTokens.warningInk,
      colorError: designTokens.dangerInk,
      colorErrorText: designTokens.dangerInk,
      colorInfoBg: designTokens.infoBg, colorInfoBorder: designTokens.infoBorder,
      colorSuccessBg: designTokens.safeBg, colorSuccessBorder: designTokens.safeBorder,
      colorWarningBg: designTokens.warningBg, colorWarningBorder: designTokens.warningBorder,
      colorErrorBg: designTokens.dangerBg, colorErrorBorder: designTokens.dangerBorder,
      colorText: designTokens.text,
      colorTextSecondary: designTokens.secondary,
      colorTextTertiary: designTokens.secondary,
      colorTextPlaceholder: designTokens.secondary,
      colorBgBase: designTokens.surface,
      colorBgLayout: designTokens.background,
      colorBgContainer: designTokens.surface,
      colorBgElevated: designTokens.elevated,
      colorBgContainerDisabled: designTokens.disabledBg,
      colorBgMask: designTokens.scrim,
      // 交互控件边界必须可辨；容器分隔使用更轻的 colorBorderSecondary。
      colorBorder: designTokens.strong,
      colorBorderSecondary: designTokens.borderSecondary,
      colorFillSecondary: designTokens.fillSecondary,
      colorFillTertiary: designTokens.fillTertiary,
      colorTextDisabled: designTokens.disabled,
      controlOutline: designTokens.outline,
      colorLink: designTokens.primaryInk,
      colorLinkHover: designTokens.primaryInk,
      colorLinkActive: designTokens.primaryInk,
      colorPrimaryText: designTokens.primaryInk,
      colorPrimaryTextHover: designTokens.primaryInk,
      colorPrimaryTextActive: designTokens.primaryInk,
      controlItemBgHover: designTokens.hover,
      controlItemBgActive: designTokens.selected,
      controlItemBgActiveHover: designTokens.selected,
      boxShadow: designTokens.shadowFloating,
      boxShadowSecondary: designTokens.shadowFloating,
      colorTextLightSolid: designTokens.onAccent,
      borderRadius: metrics.radius.medium,
      borderRadiusLG: metrics.radius.large,
      borderRadiusSM: metrics.radius.small,
      fontSize: metrics.font.body,
      fontSizeHeading1: metrics.font.titleMax,
      fontSizeHeading2: metrics.font.section,
      fontSizeHeading3: metrics.font.local,
      fontFamily: metrics.sans,
      fontFamilyCode: metrics.mono,
      fontWeightStrong: 600,
      lineHeight: 1.57,
      controlHeight: metrics.control.normal,
      controlHeightLG: metrics.control.large,
      controlHeightSM: metrics.control.small,
    },
    components: {
      Button: { borderRadius: metrics.radius.small, borderRadiusLG: metrics.radius.small, controlHeight: metrics.control.normal, controlHeightLG: metrics.control.large, controlHeightSM: metrics.control.small, paddingInline: 16, primaryShadow: 'none', defaultShadow: 'none', defaultBg: designTokens.surface, defaultColor: designTokens.primaryInk, defaultBorderColor: designTokens.primaryBorder, defaultHoverColor: designTokens.primaryInk, defaultHoverBg: designTokens.primaryLight, defaultActiveColor: designTokens.primaryInk },
      Card: { bodyPadding: 20, bodyPaddingSM: 16, headerBg: designTokens.surface, headerHeight: 44 },
      Input: {
        borderRadius: metrics.radius.small,
        activeBg: designTokens.surface,
        activeBorderColor: designTokens.primary,
        colorBgContainer: designTokens.surface,
        colorBorder: designTokens.strong,
        controlHeight: metrics.control.normal,
        hoverBorderColor: designTokens.primary,
      },
      Layout: { bodyBg: designTokens.background, headerBg: designTokens.surface, siderBg: designTokens.navigation },
      Menu: { itemBg: designTokens.surface, itemSelectedBg: designTokens.selected, itemSelectedColor: designTokens.primaryInk },
      Segmented: { itemSelectedBg: designTokens.elevated, trackBg: designTokens.fillSecondary, trackPadding: 2 },
      Select: {
        borderRadius: metrics.radius.small,
        activeBorderColor: designTokens.primary,
        colorBgContainer: designTokens.surface,
        colorBorder: designTokens.strong,
        controlHeight: metrics.control.normal,
        optionSelectedBg: designTokens.selected,
        optionActiveBg: designTokens.hover,
      },
      Tag: { borderRadiusSM: metrics.radius.small, defaultBg: designTokens.neutralBg, defaultColor: designTokens.neutral },
      Tabs: { itemColor: designTokens.secondary, itemSelectedColor: designTokens.text, itemHoverColor: designTokens.primaryInk, inkBarColor: designTokens.primary },
      Table: { headerBg: designTokens.subtle, headerColor: designTokens.secondary, borderColor: designTokens.border, rowHoverBg: designTokens.hover, rowSelectedBg: designTokens.selected },
      Modal: { contentBg: designTokens.elevated, headerBg: designTokens.elevated },
      Tooltip: { colorBgSpotlight: designTokens.text, colorTextLightSolid: designTokens.background },
    },
  }
}
