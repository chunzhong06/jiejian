import {useLayoutEffect,useState,type ReactNode} from 'react'
import {ConfigProvider,theme as antTheme,type ThemeConfig} from 'antd'

function palette(appearance:'light'|'dark'):ThemeConfig{
  const css=getComputedStyle(document.documentElement),tokens:Record<string,string|number>={fontFamily:css.getPropertyValue('--font-ui').trim()||'system-ui, sans-serif',fontSize:14,fontSizeSM:12,fontSizeLG:14,controlHeight:40,controlHeightSM:32,borderRadius:8,borderRadiusLG:12}
  for(const [name,variable] of Object.entries({colorPrimary:'--accent',colorPrimaryHover:'--accent-hover',colorPrimaryActive:'--accent-pressed',colorText:'--ink',colorTextSecondary:'--muted',colorBgLayout:'--bg',colorBgContainer:'--control-bg',colorBgElevated:'--surface-elevated',colorTextPlaceholder:'--placeholder',colorTextDisabled:'--disabled-ink',colorBgContainerDisabled:'--disabled-bg',colorBgMask:'--overlay',colorTextTertiary:'--subtle',colorTextLightSolid:'--on-accent',colorBorder:'--line-strong',colorBorderSecondary:'--line',colorPrimaryBg:'--accent-soft',colorPrimaryText:'--accent-ink',colorInfo:'--info',colorInfoBg:'--accent-soft',colorSuccess:'--good',colorSuccessBg:'--good-soft',colorWarning:'--warn',colorWarningBg:'--warn-soft',colorError:'--bad',colorErrorBg:'--bad-soft'})){const value=css.getPropertyValue(variable).trim();if(value)tokens[name]=value}
  for(const [name,variable] of Object.entries({motionDurationFast:'--motion-exit',motionDurationMid:'--motion-popup',motionDurationSlow:'--motion-dialog',colorBgTextHover:'--hover',controlItemBgHover:'--hover',controlItemBgActive:'--selected',controlItemBgActiveHover:'--selected-hover'})){const value=css.getPropertyValue(variable).trim();if(value)tokens[name]=value}
  // 库算法补齐内部派生色，表面、交互和状态仍由同一组产品语义色负责。
  return {inherit:false,algorithm:appearance==='dark'?antTheme.darkAlgorithm:antTheme.defaultAlgorithm,token:tokens,components:{Select:{optionHeight:40,optionPadding:'10px 14px',optionSelectedFontWeight:550}}}
}

export function UIProvider({appearance,children}:{appearance:'light'|'dark';children:ReactNode}){
  const [theme,setTheme]=useState(()=>palette(appearance))
  useLayoutEffect(()=>{document.documentElement.dataset.studioTheme=appearance;setTheme(palette(appearance))},[appearance])
  return <ConfigProvider theme={theme}>{children}</ConfigProvider>
}
