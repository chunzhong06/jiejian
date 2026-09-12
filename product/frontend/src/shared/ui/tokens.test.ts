// 验证正文和主要操作的实际派生 token 对比，不把低饱和标志色直接当文字。
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
