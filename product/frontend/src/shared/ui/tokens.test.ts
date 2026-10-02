// 验证雾蓝·石墨在真实交互和语义表面上的对比，避免只检查单一白底。
import {expect, it} from 'vitest'
import {designTokens, palettes} from './tokens'
function luminance(value: string) {
  const channels = value.startsWith('#') ? [1,3,5].map((i)=>parseInt(value.slice(i,i+2),16)) : value.match(/[\d.]+/g)!.map(Number)
  return channels.map((c)=>c/255).map((c)=>c<=.04045?c/12.92:((c+.055)/1.055)**2.4).reduce((v,c,i)=>v+c*[.2126,.7152,.0722][i],0)
}
function ratio(a:string,b:string){const hi=Math.max(luminance(a),luminance(b)),lo=Math.min(luminance(a),luminance(b));return (hi+.05)/(lo+.05)}
for(const mode of ['light','dark'] as const) it(`${mode} 正文、证据和主按钮对比至少 4.5`,()=>{
 const t=designTokens(mode),p=palettes[mode]
 for(const [fg,bg] of [[t.text,t.background],[t.secondary,t.background],[t.secondary,t.surface],[p.evidenceText,p.evidenceSurface],[p.evidenceText,p.evidenceSubtle],[t.onAccent,t.primary],[t.safeInk,t.background],[t.warningInk,t.background],[t.dangerInk,t.background]]) expect(ratio(fg,bg),`${fg} / ${bg}`).toBeGreaterThanOrEqual(4.5)
})
for(const mode of ['light','dark'] as const) it(`${mode} 提示正文在四类语义底色上保持可读`,()=>{
 const t=designTokens(mode)
 for(const background of [t.infoBg,t.safeBg,t.warningBg,t.dangerBg]) {
  expect(ratio(t.text,background)).toBeGreaterThanOrEqual(4.5)
  expect(ratio(t.secondary,background)).toBeGreaterThanOrEqual(4.5)
 }
})
for(const mode of ['light','dark'] as const) it(`${mode} 状态文字在实际标签底色上的对比至少 4.5`,()=>{
 const t=designTokens(mode)
 for(const [foreground,background] of [[t.safeInk,t.safeTagBg],[t.dangerInk,t.dangerTagBg],[t.warningInk,t.warningTagBg],[t.evidence,t.infoBg],[t.neutral,t.neutralBg],[t.ai,t.aiBg]]) {
  expect(ratio(foreground,background),`${foreground} / ${background}`).toBeGreaterThanOrEqual(4.5)
 }
})
for(const mode of ['light','dark'] as const) it(`${mode} 交互状态、浮层与选择内容保持可读`,()=>{
 const t=designTokens(mode)
 for(const [fg,bg] of [[t.onAccent,t.primaryHover],[t.onAccent,t.primaryActive],[t.primaryInk,t.surface],[t.primaryInk,t.selected],[t.primaryInk,t.elevated],[t.text,t.elevated],[t.secondary,t.elevated],[t.secondary,t.navigation],[t.text,t.hover]]) {
  expect(ratio(fg,bg),`${fg} / ${bg}`).toBeGreaterThanOrEqual(4.5)
 }
 for(const [fg,bg] of [[t.strong,t.surface],[t.primary,t.background],[t.primary,t.elevated]]) {
  expect(ratio(fg,bg),`控件边界 ${fg} / ${bg}`).toBeGreaterThanOrEqual(3)
 }
})
