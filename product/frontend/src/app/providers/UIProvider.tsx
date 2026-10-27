import {useLayoutEffect,useState,type ReactNode} from 'react'
import {ConfigProvider,type ThemeConfig} from 'antd'

function palette():ThemeConfig{
  const css=getComputedStyle(document.documentElement),tokens:Record<string,string|number>={fontFamily:css.getPropertyValue('--font-ui').trim()||'system-ui, sans-serif',fontSize:14,fontSizeSM:12,fontSizeLG:14,controlHeight:40,controlHeightSM:32,borderRadius:8,borderRadiusLG:12}
  for(const [name,variable] of Object.entries({colorPrimary:'--accent',colorText:'--ink',colorTextSecondary:'--muted',colorBgContainer:'--surface',colorBgElevated:'--surface',colorBorder:'--line-strong',colorBorderSecondary:'--line',colorPrimaryBg:'--accent-soft',colorPrimaryText:'--accent-ink'})){const value=css.getPropertyValue(variable).trim();if(value)tokens[name]=value}
  for(const [name,variable] of Object.entries({motionDurationFast:'--motion-exit',motionDurationMid:'--motion-popup',motionDurationSlow:'--motion-dialog',colorBgTextHover:'--hover',controlItemBgHover:'--hover'})){const value=css.getPropertyValue(variable).trim();if(value)tokens[name]=value}
  return {inherit:false,token:tokens,components:{Select:{optionHeight:38,optionSelectedFontWeight:550}}}
}

export function UIProvider({appearance,children}:{appearance:'light'|'dark';children:ReactNode}){
  const [theme,setTheme]=useState(palette)
  useLayoutEffect(()=>{document.documentElement.dataset.studioTheme=appearance;setTheme(palette())},[appearance])
  return <ConfigProvider theme={theme}>{children}</ConfigProvider>
}
