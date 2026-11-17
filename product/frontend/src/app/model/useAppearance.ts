import {useEffect,useState} from 'react'
import {commitThemeTransition} from '../../shared/lib/pageTransition'
import {readPreference,writePreference} from '../../shared/lib/preferences'

export function useAppearance(){
  const [appearance,setAppearance]=useState<'light'|'dark'>(()=>readPreference('jiejian.studio.theme')==='dark'?'dark':'light')
  useEffect(()=>{
    document.documentElement.dataset.studioTheme=appearance
    writePreference('jiejian.studio.theme',appearance)
  },[appearance])
  const toggle=()=>commitThemeTransition(()=>setAppearance(value=>value==='light'?'dark':'light'))
  return {appearance,toggle}
}
