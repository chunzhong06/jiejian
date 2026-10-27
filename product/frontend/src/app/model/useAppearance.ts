import {useEffect,useState} from 'react'
import {commitThemeTransition} from '../../shared/lib/pageTransition'

export function useAppearance(){
  const [appearance,setAppearance]=useState<'light'|'dark'>(()=>localStorage.getItem('jiejian.studio.theme')==='dark'?'dark':'light')
  useEffect(()=>{
    document.documentElement.dataset.studioTheme=appearance
    localStorage.setItem('jiejian.studio.theme',appearance)
  },[appearance])
  const toggle=()=>commitThemeTransition(()=>setAppearance(value=>value==='light'?'dark':'light'))
  return {appearance,toggle}
}
