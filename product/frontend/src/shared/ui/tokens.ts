// 雾蓝·石墨设计令牌：同一语义对象驱动 Ant Design、正文与浮层，不保存业务判断。
export const palettes = {
  light: {
    background: '#F6F7FA', surface: '#FFFFFF', elevated: '#FFFFFF', subtle: '#EEF0F5', hover: '#E8ECF4', navigation: '#F4F5F9',
    text: '#242936', secondary: '#616B7C', border: '#C7CFDC', strong: '#7F8BA0',
    evidenceSurface: '#FFFFFF', evidenceSubtle: '#EEF0F5', evidenceText: '#242936',
    primary: '#465BC1', primaryHover: '#394BA5', primaryActive: '#2F3F8B', primaryInk: '#4055A7', primaryLight: '#ECEFF9', primaryBorder: '#BCC6E7', onAccent: '#FFFFFF',
    fact: '#415E99', infoBg: '#EAF0FB', ai: '#75539A', aiBg: '#F1EBF8',
    safe: '#27664E', safeTagBg: '#E7F2EB', danger: '#A13F51', dangerTagBg: '#F9E9EE', warning: '#8C601D', warningTagBg: '#FBF1DE',
    neutral: '#5E6776', neutralBg: '#ECEFF3', disabled: '#758092', disabledBg: '#EBEEF3',
    scrim: 'rgba(18,24,38,.38)', shadowFloating: '0 12px 36px rgba(26,35,54,.12)', shadowFocus: '0 4px 18px rgba(26,35,54,.04)',
  },
  dark: {
    background: '#171B23', surface: '#1F2530', elevated: '#282F3C', subtle: '#272E3A', hover: '#30394A', navigation: '#242B36',
    text: '#EBEEF5', secondary: '#ADB8CA', border: '#394354', strong: '#78869D',
    evidenceSurface: '#1F2530', evidenceSubtle: '#272E3A', evidenceText: '#EBEEF5',
    primary: '#A8B7EF', primaryHover: '#BBC7F4', primaryActive: '#D0D8FA', primaryInk: '#B4C2F5', primaryLight: '#2B3551', primaryBorder: '#5B6C99', onAccent: '#18213B',
    fact: '#ADC6F3', infoBg: '#28364D', ai: '#CFB6E8', aiBg: '#372C45',
    safe: '#A1D3B5', safeTagBg: '#243A30', danger: '#F0ADBA', dangerTagBg: '#412A32', warning: '#E7C58B', warningTagBg: '#3D3324',
    neutral: '#BDC5D2', neutralBg: '#303642', disabled: '#929CAB', disabledBg: '#2C313C',
    scrim: 'rgba(6,9,16,.64)', shadowFloating: '0 12px 40px rgba(0,0,0,.35)', shadowFocus: '0 4px 18px rgba(0,0,0,.12)',
  },
} as const
export type ProductTheme = keyof typeof palettes
export const metrics = {
  layout: { navigation: 200, header: 60, mobileSummary: 52, content: 1460, task: 1120, form: 1240 },
  space: [4, 8, 12, 16, 20, 24, 32, 40, 48],
  font: { body: 15, secondary: 13, label: 12, local: 16, section: 20, titleMin: 26, titleMax: 30 },
  radius: { small: 7, medium: 10, large: 12 },
  line: 1, control: { normal: 40, large: 44, small: 32 },
  rhythm: { fieldGap: 16, actionGap: 12, sectionGap: 32, headerGap: 32, panelPadding: 24, pagePadding: 32, pagePaddingNarrow: 16, searchWidth: 320 },
  motion: { instant: 90, fast: 140, normal: 180, slow: 220, emphasis: 280 },
  ease: 'cubic-bezier(.2, 0, 0, 1)',
  sans: '"Segoe UI Variable", "PingFang SC", "Microsoft YaHei", "Microsoft YaHei UI", "Noto Sans SC", system-ui, sans-serif',
  mono: '"SFMono-Regular", "Cascadia Code", Consolas, monospace',
} as const

// 状态和交互色使用已核对的成对值，避免组件库与页面各自混色造成亮暗主题偏差。
export function designTokens(mode: ProductTheme) {
  const p = palettes[mode]
  return { ...p, evidence: p.fact, safeInk: p.safe, dangerInk: p.danger, warningInk: p.warning,
    infoBorder: 'transparent', safeBg: p.safeTagBg, safeBorder: 'transparent',
    warningBg: p.warningTagBg, warningBorder: 'transparent', dangerBg: p.dangerTagBg, dangerBorder: 'transparent',
    fillSecondary: p.subtle, fillTertiary: p.subtle,
    borderSecondary: p.border, selected: p.primaryLight, outline: p.primary,
  }
}
export function productCssVariables(mode: ProductTheme): Record<string, string> {
  const p = designTokens(mode)
  const values: Record<string, string> = {
    '--font-sans': metrics.sans, '--font-mono': metrics.mono,
    '--color-bg': p.background, '--color-surface': p.surface, '--color-surface-subtle': p.subtle,
    '--color-surface-hover': p.hover, '--color-navigation': p.navigation, '--color-text': p.text, '--color-secondary': p.secondary, '--color-tertiary': p.secondary,
    '--color-border': p.border, '--color-border-strong': p.strong, '--color-primary': p.primary, '--color-primary-light': p.primaryLight,
    '--color-primary-hover': p.primaryHover, '--color-primary-active': p.primaryActive, '--color-primary-ink': p.primaryInk, '--color-control-border': p.strong,
    '--color-evidence': p.evidence, '--color-fact': p.fact, '--color-safe': p.safeInk, '--color-warning': p.warningInk, '--color-danger': p.dangerInk,
    '--color-safe-mark': p.safe, '--color-warning-mark': p.warning, '--color-danger-mark': p.danger,
    '--color-safe-light': p.safeTagBg, '--color-warning-light': p.warningTagBg,
    '--color-danger-light': p.dangerTagBg, '--color-ai': p.ai, '--color-ai-light': p.aiBg,
    '--color-neutral': p.neutral, '--color-neutral-light': p.neutralBg, '--color-disabled': p.disabled, '--color-disabled-bg': p.disabledBg,
    '--color-on-accent': p.onAccent, '--color-navigation-icon': p.secondary, '--color-neutral-dot': p.secondary,
    '--color-primary-panel': p.surface, '--color-primary-panel-strong': p.subtle, '--color-primary-border': p.primaryBorder,
    '--color-surface-overlay': p.elevated, '--color-floating-surface': p.elevated, '--color-info-light': p.infoBg, '--color-warm-light': p.surface,
    '--color-evidence-surface': p.evidenceSurface, '--color-evidence-subtle': p.evidenceSubtle, '--color-evidence-text': p.evidenceText,
    '--shadow-focus': p.shadowFocus, '--shadow-floating': p.shadowFloating,
    '--ease-standard': metrics.ease, '--line-width': `${metrics.line}px`,
  }
  metrics.space.forEach((n) => { values[`--space-${n}`] = `${n}px` })
  Object.entries(metrics.radius).forEach(([k, n]) => { values[`--radius-${k}`] = `${n}px` })
  Object.entries(metrics.motion).forEach(([k, n]) => { values[`--motion-${k}`] = `${n}ms` })
  Object.entries(metrics.font).forEach(([k, n]) => { values[`--font-${k}`] = `${n}px` })
  Object.entries(metrics.layout).forEach(([k, n]) => { values[`--layout-${k}`] = `${n}px` })
  Object.entries(metrics.control).forEach(([k, n]) => { values[`--control-${k}`] = `${n}px` })
  Object.entries(metrics.rhythm).forEach(([k, n]) => { values[`--rhythm-${k}`] = `${n}px` })
  return values
}
