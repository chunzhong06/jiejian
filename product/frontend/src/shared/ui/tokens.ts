// 唯一设计令牌：同一语义对象驱动 Ant Design 与 CSS，不保存业务判断。
export const palettes = {
  light: { background: '#F5F5F7', surface: '#FFFFFF', subtle: '#ECEEF2', text: '#24262C', secondary: '#686C76', border: '#E0E2E7', strong: '#5C626E', evidenceSurface: '#252D3A', evidenceSubtle: '#343E4E', evidenceText: '#F0F3F8', primary: '#4263D5', fact: '#B4C4E1', ai: '#9E8CBC', warning: '#AD8338', safe: '#458366', danger: '#B75D64' },
  dark: { background: '#191B20', surface: '#24272D', subtle: '#323640', text: '#E8E9ED', secondary: '#A3A6B1', border: '#393D46', strong: '#A3A6B1', evidenceSurface: '#202938', evidenceSubtle: '#313D50', evidenceText: '#F0F3F8', primary: '#91A8FF', fact: '#B4C4E1', ai: '#BBACD2', warning: '#DBC084', safe: '#8BC5A6', danger: '#ED999D' },
} as const
export type ProductTheme = keyof typeof palettes
export const metrics = {
  layout: { navigation: 200, header: 60, mobileSummary: 52, content: 1460 },
  space: [4, 8, 12, 16, 20, 24, 32, 40, 48],
  font: { body: 15, secondary: 13, label: 12, section: 22, titleMin: 26, titleMax: 34 },
  radius: { small: 6, medium: 10, large: 16 },
  line: 1, control: { normal: 36, large: 40, small: 28 },
  motion: { instant: 90, fast: 140, normal: 180, slow: 220, emphasis: 280 },
  ease: 'cubic-bezier(.2, 0, 0, 1)',
  sans: '"Segoe UI Variable", "PingFang SC", "Microsoft YaHei", "Microsoft YaHei UI", "Noto Sans SC", system-ui, sans-serif',
  mono: '"SFMono-Regular", "Cascadia Code", Consolas, monospace',
} as const

// 低饱和状态色只作标志；亮色正文由同一色板混入主文字色取得可读对比。
function ink(accent: string, text: string, weight = .45) {
  const channels = [1, 3, 5].map((offset) => Math.round(parseInt(accent.slice(offset, offset + 2), 16) * weight + parseInt(text.slice(offset, offset + 2), 16) * (1 - weight)))
  return `rgb(${channels.join(', ')})`
}
export function designTokens(mode: ProductTheme) {
  const p = palettes[mode]
  return { ...p, secondary: mode === 'light' ? ink(p.secondary, p.text, .96) : p.secondary, evidence: mode === 'light' ? ink(p.fact, p.text) : p.fact,
    safeInk: mode === 'light' ? ink(p.safe, p.text) : p.safe,
    warningInk: mode === 'light' ? ink(p.warning, p.text) : p.warning,
    dangerInk: mode === 'light' ? ink(p.danger, p.text) : p.danger,
    elevated: p.surface, fillSecondary: p.subtle, fillTertiary: p.subtle,
    borderSecondary: p.border, disabled: p.secondary, selected: p.subtle,
    outline: p.primary, onAccent: mode === 'light' ? p.surface : p.background,
  }
}
export function productCssVariables(mode: ProductTheme): Record<string, string> {
  const p = designTokens(mode)
  const values: Record<string, string> = {
    '--font-sans': metrics.sans, '--font-mono': metrics.mono,
    '--color-bg': p.background, '--color-surface': p.surface, '--color-surface-subtle': p.subtle,
    '--color-surface-hover': p.subtle, '--color-text': p.text, '--color-secondary': p.secondary, '--color-tertiary': p.secondary,
    '--color-border': p.border, '--color-border-strong': p.strong, '--color-primary': p.primary, '--color-primary-light': `color-mix(in srgb, ${p.primary} 10%, ${p.background})`,
    '--color-evidence': p.evidence, '--color-fact': p.fact, '--color-safe': p.safeInk, '--color-warning': p.warningInk, '--color-danger': p.dangerInk,
    '--color-safe-mark': p.safe, '--color-warning-mark': p.warning, '--color-danger-mark': p.danger,
    '--color-safe-light': p.subtle, '--color-safe-border': p.safe, '--color-warning-light': p.subtle, '--color-warning-border': p.warning,
    '--color-danger-light': p.subtle, '--color-danger-border': p.danger, '--color-ai': p.ai, '--color-ai-light': p.subtle,
    '--color-on-accent': p.onAccent, '--color-navigation-icon': p.secondary, '--color-neutral-dot': p.secondary,
    '--color-primary-panel': p.surface, '--color-primary-panel-strong': p.subtle, '--color-primary-border': p.border,
    '--color-surface-overlay': p.surface, '--color-floating-surface': p.surface, '--color-info-light': p.subtle, '--color-warm-light': p.surface,
    '--color-evidence-surface': p.evidenceSurface, '--color-evidence-subtle': p.evidenceSubtle, '--color-evidence-text': p.evidenceText,
    '--shadow-focus': `0 2px 4px color-mix(in srgb, ${p.text} 2%, transparent), 0 12px 40px color-mix(in srgb, ${p.text} 5%, transparent)`, '--shadow-floating': `0 4px 12px color-mix(in srgb, ${p.text} 6%, transparent), 0 20px 64px color-mix(in srgb, ${p.text} 16%, transparent)`,
    '--ease-standard': metrics.ease, '--line-width': `${metrics.line}px`,
  }
  metrics.space.forEach((n) => { values[`--space-${n}`] = `${n}px` })
  Object.entries(metrics.radius).forEach(([k, n]) => { values[`--radius-${k}`] = `${n}px` })
  Object.entries(metrics.motion).forEach(([k, n]) => { values[`--motion-${k}`] = `${n}ms` })
  Object.entries(metrics.font).forEach(([k, n]) => { values[`--font-${k}`] = `${n}px` })
  Object.entries(metrics.layout).forEach(([k, n]) => { values[`--layout-${k}`] = `${n}px` })
  return values
}
