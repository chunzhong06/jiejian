// 唯一设计令牌：同一语义对象驱动 Ant Design 与 CSS，不保存业务判断。
export const palettes = {
  light: { background: '#F4EBD9', surface: '#FFF9EE', subtle: '#EEE4D1', text: '#292721', secondary: '#716B61', border: '#D7CBB7', strong: '#4B473F', evidenceSurface: '#3F514B', evidenceSubtle: '#4A5D56', evidenceText: '#F7F1E5', primary: '#397873', fact: '#9DBBD0', ai: '#D6A4BB', warning: '#DAB95D', safe: '#85AE94', danger: '#CA756B' },
  dark: { background: '#171915', surface: '#20231E', subtle: '#292C26', text: '#F1EADB', secondary: '#B5AEA0', border: '#41453D', strong: '#B5AEA0', evidenceSurface: '#31423D', evidenceSubtle: '#3B4E47', evidenceText: '#F7F1E5', primary: '#78A9A4', fact: '#9DBBD0', ai: '#D6A4BB', warning: '#DAB95D', safe: '#85AE94', danger: '#CA756B' },
} as const
export type ProductTheme = keyof typeof palettes
export const metrics = {
  space: [4, 8, 12, 16, 20, 24, 32, 40, 48],
  font: { body: 16, secondary: 14, label: 13, section: 22, titleMin: 26, titleMax: 42 },
  radius: { small: 4, medium: 4, large: 4 },
  line: 1, control: { normal: 36, large: 40, small: 28 },
  motion: { instant: 90, fast: 140, normal: 180, slow: 220, emphasis: 280 },
  ease: 'cubic-bezier(.2, 0, 0, 1)',
  sans: '"Segoe UI Variable", "PingFang SC", "Microsoft YaHei UI", "Noto Sans SC", system-ui, sans-serif',
  mono: '"SFMono-Regular", "Cascadia Code", Consolas, monospace',
} as const

// 低饱和状态色只作标志；亮色正文由同一色板混入暖墨取得可读对比。
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
    outline: p.primary, onAccent: p.surface,
  }
}
export function productCssVariables(mode: ProductTheme): Record<string, string> {
  const p = designTokens(mode)
  const values: Record<string, string> = {
    '--font-sans': metrics.sans, '--font-mono': metrics.mono,
    '--color-bg': p.background, '--color-surface': p.surface, '--color-surface-subtle': p.subtle,
    '--color-surface-hover': p.subtle, '--color-text': p.text, '--color-secondary': p.secondary, '--color-tertiary': p.secondary,
    '--color-border': p.border, '--color-border-strong': p.strong, '--color-primary': p.primary, '--color-primary-light': p.subtle,
    '--color-evidence': p.evidence, '--color-fact': p.fact, '--color-safe': p.safeInk, '--color-warning': p.warningInk, '--color-danger': p.dangerInk,
    '--color-safe-mark': p.safe, '--color-warning-mark': p.warning, '--color-danger-mark': p.danger,
    '--color-safe-light': p.subtle, '--color-safe-border': p.safe, '--color-warning-light': p.subtle, '--color-warning-border': p.warning,
    '--color-danger-light': p.subtle, '--color-danger-border': p.danger, '--color-ai': p.ai, '--color-ai-light': p.subtle,
    '--color-on-accent': p.onAccent, '--color-navigation-icon': p.secondary, '--color-neutral-dot': p.secondary,
    '--color-primary-panel': p.surface, '--color-primary-panel-strong': p.subtle, '--color-primary-border': p.border,
    '--color-surface-overlay': p.surface, '--color-floating-surface': p.surface, '--color-info-light': p.subtle, '--color-warm-light': p.surface,
    '--color-evidence-surface': p.evidenceSurface, '--color-evidence-subtle': p.evidenceSubtle, '--color-evidence-text': p.evidenceText,
    '--shadow-focus': 'none', '--shadow-floating': `0 8px 24px color-mix(in srgb, ${p.text} 12%, transparent)`,
    '--ease-standard': metrics.ease, '--line-width': `${metrics.line}px`,
  }
  metrics.space.forEach((n) => { values[`--space-${n}`] = `${n}px` })
  Object.entries(metrics.radius).forEach(([k, n]) => { values[`--radius-${k}`] = `${n}px` })
  Object.entries(metrics.motion).forEach(([k, n]) => { values[`--motion-${k}`] = `${n}ms` })
  Object.entries(metrics.font).forEach(([k, n]) => { values[`--font-${k}`] = `${n}px` })
  return values
}
