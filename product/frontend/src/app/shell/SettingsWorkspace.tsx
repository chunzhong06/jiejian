import type {ReactNode} from 'react'
import {LinkTabs} from '../../shared/ui/Tabs'
import {scopedPath,type Route} from '../../shared/lib/navigation'
import {settingsPath,settingsSection,settingsSections} from '../../shared/lib/settings'
import {Heading} from '../../shared/ui/layout'
import './settings.css'

export function SettingsWorkspace({route,projectId,children,onPreload}:{route:Route;projectId?:string;children:ReactNode;onPreload:(path:string)=>void}){
  const selected=settingsSection(route)
  return <section className="jj-settings-page"><Heading title="设置"/>
    <div className="jj-settings-layout"><LinkTabs label="设置分类" value={selected??'tools'} className="jj-settings-navigation" items={settingsSections.map(item=>({value:item.key,label:item.label,href:'#'+scopedPath(settingsPath(item.key),projectId)}))} onIntent={value=>onPreload(settingsPath(value as typeof settingsSections[number]['key']))}/>
      <div className="jj-settings-content" key={selected}>{children}</div>
    </div>
  </section>
}
