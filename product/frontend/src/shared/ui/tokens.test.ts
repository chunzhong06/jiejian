// 验证亮暗主题在真实交互和语义表面上的对比，避免只检查单一白底。
import {expect, it} from 'vitest'
import {designTokens, palettes} from './tokens'
function luminance(value: string) {
  const channels = value.startsWith('#') ? [1,3,5].map((i)=>parseInt(value.slice(i,i+2),16)) : value.match(/[\d.]+/g)!.map(Number)
  return channels.map((c)=>c/255).map((c)=>c<=.04045?c/12.92:((c+.055)/1.055)**2.4).reduce((v,c,i)=>v+c*[.2126,.7152,.0722][i],0)
}
function ratio(a:string,b:string){const hi=Math.max(luminance(a),luminance(b)),lo=Math.min(luminance(a),luminance(b));return (hi+.05)/(lo+.05)}
function composite(foreground:string,background:string) {
 const channels=(v:string)=>v.startsWith('#')?[...[1,3,5].map(i=>parseInt(v.slice(i,i+2),16)),v.length===9?parseInt(v.slice(7,9),16)/255:1]:v.match(/[\d.]+/g)!.map(Number)
 const fg=channels(foreground),bg=channels(background),alpha=fg[3]??1
 return `rgb(${fg.slice(0,3).map((n,i)=>Math.round(n*alpha+bg[i]*(1-alpha))).join(',')})`
}
for(const mode of ['light','dark'] as const) it(`${mode} 主按钮在渐变和无渐变的三个状态中均可读`,()=>{
 const p=palettes[mode]
 for(const surface of [p.background,p.surface,p.elevated,p.infoBg,p.safeTagBg,p.warningTagBg,p.dangerTagBg]) {
  for(const [base,fill] of [[p.primaryBase,p.primaryFill],[p.primaryHoverBase,p.primaryHoverFill],[p.primaryActiveBase,p.primaryActiveFill]]) {
   const bottom=composite(base,surface)
   const stops=fill.match(/#[a-f0-9]{6}|rgba?\([^)]*\)/gi)??[]
   for(const background of [bottom,...stops.map(stop=>composite(stop,bottom))]) expect(ratio(p.primaryText,background)).toBeGreaterThanOrEqual(4.5)
  }
 }
})
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

for(const mode of ['light','dark'] as const) it(`${mode} 渐变叠加后的阅读面与玻璃浮层仍有足够对比`,()=>{
 const p=palettes[mode],stops=p.ambient.match(/#[a-f0-9]{8}/gi)??[]
 const pageColors=[p.background,...stops.map(stop=>composite(stop,p.background)),stops.reduce((bg,stop)=>composite(stop,bg),p.background)]
 for(const bg of pageColors) {
  const chrome = composite(p.glass,bg)
  const gradients = p.chromeGradient.match(/rgba?\([^)]*\)/gi)??[]
  for(const surface of [composite(p.readingSurface,bg),chrome,...gradients.map(stop=>composite(stop,chrome)),composite(p.glassFloating,composite(p.scrim,bg))]) {
   for(const fg of [p.text,p.secondary,p.primaryInk]) expect(ratio(fg,surface),`${fg} / ${surface}`).toBeGreaterThanOrEqual(4.5)
  }
 }
})
