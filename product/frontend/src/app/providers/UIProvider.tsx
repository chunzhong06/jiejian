import {useLayoutEffect,useState,type ReactNode} from 'react'
import {ConfigProvider,theme as antTheme,type ThemeConfig} from 'antd'
import {MotionRoot} from '../../shared/ui/MotionRoot'

function palette(appearance:'light'|'dark'):ThemeConfig{
  const css=getComputedStyle(document.documentElement),tokens:Record<string,string|number>={fontFamily:css.getPropertyValue('--font-ui').trim()||'system-ui, sans-serif'}
  // 浮层中的字级与原生控件使用相同角色，不能在组件库映射中另留一套固定字号。
  for(const [name,variable] of Object.entries({fontSize:'--text-body',fontSizeSM:'--text-meta',fontSizeLG:'--text-group',controlHeight:'--control-height',controlHeightSM:'--control-compact',borderRadius:'--radius-control',borderRadiusLG:'--radius-float',fontWeightStrong:'--weight-semibold'}))tokens[name]=parseFloat(css.getPropertyValue(variable))
  for(const [name,variable] of Object.entries({colorPrimary:'--accent',colorPrimaryHover:'--accent-hover',colorPrimaryActive:'--accent-pressed',colorText:'--ink',colorTextSecondary:'--muted',colorBgLayout:'--bg',colorBgContainer:'--control-bg',colorBgElevated:'--surface-elevated',colorTextPlaceholder:'--placeholder',colorTextDisabled:'--disabled-ink',colorBgContainerDisabled:'--disabled-bg',colorBgMask:'--overlay',colorTextTertiary:'--subtle',colorTextLightSolid:'--on-accent',colorBorder:'--line-strong',colorBorderSecondary:'--line',colorPrimaryBg:'--accent-soft',colorPrimaryText:'--accent-ink',colorInfo:'--info',colorInfoBg:'--accent-soft',colorSuccess:'--good',colorSuccessBg:'--good-soft',colorWarning:'--warn',colorWarningBg:'--warn-soft',colorError:'--bad',colorErrorBg:'--bad-soft'})){const value=css.getPropertyValue(variable).trim();if(value)tokens[name]=value}
  for(const [name,variable] of Object.entries({motionDurationFast:'--motion-exit',motionDurationMid:'--motion-popup',motionDurationSlow:'--motion-dialog',colorBgTextHover:'--hover',controlItemBgHover:'--hover',controlItemBgActive:'--selected',controlItemBgActiveHover:'--selected-hover'})){const value=css.getPropertyValue(variable).trim();if(value)tokens[name]=value}
  // 库算法补齐内部派生色，表面、交互和状态仍由同一组产品语义色负责。
  return {inherit:false,algorithm:appearance==='dark'?antTheme.darkAlgorithm:antTheme.defaultAlgorithm,token:tokens,components:{Select:{optionHeight:40,optionPadding:'10px 14px',optionSelectedFontWeight:parseFloat(css.getPropertyValue('--weight-regular'))}}}
}

export function UIProvider({appearance,children}:{appearance:'light'|'dark';children:ReactNode}){
  // 先以关闭动效建立库的稳定上下文，再于首次绘制前采用系统偏好。
  // antd 5.29 的 MotionWrapper 首次从开到关会插入 Provider，导致整个子任务重挂载。
  const [reducedMotion,setReducedMotion]=useState(true)
  useLayoutEffect(()=>{const preference=matchMedia('(prefers-reduced-motion: reduce)'),update=()=>setReducedMotion(preference.matches);update();preference.addEventListener('change',update);return()=>preference.removeEventListener('change',update)},[])
  const [theme,setTheme]=useState(()=>palette(appearance))
  useLayoutEffect(()=>{document.documentElement.dataset.studioTheme=appearance;setTheme(palette(appearance))},[appearance])
  // CSS 关闭动画之外，同步库的生命周期；否则离场浮层可能一直等待不会发生的结束事件。
  return <ConfigProvider theme={{...theme,token:{...theme.token,motion:!reducedMotion}}}><MotionRoot/>{children}</ConfigProvider>
}
