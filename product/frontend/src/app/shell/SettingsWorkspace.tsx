import type {ReactNode} from 'react'
import {LinkTabs} from '../../shared/ui/Tabs'
import {scopedPath,returnDestination,returnDestinationLabel,withReturnDestination,type Route} from '../../shared/lib/navigation'
import {ActionLink} from '../../shared/ui/actions'
import {settingsPath,settingsSection,settingsSections} from '../../shared/lib/settings'
import {Heading} from '../../shared/ui/layout'
import './settings.css'

export function SettingsWorkspace({route,projectId,children,onPreload}:{route:Route;projectId?:string;children:ReactNode;onPreload:(path:string)=>void}){
  const selected=settingsSection(route)
  const origin=returnDestination(route.query.get('return_to'))
  return <section className="jj-settings-page">{origin&&<div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(origin,projectId)} kind="quiet">{returnDestinationLabel(origin)}</ActionLink></div>}<Heading title="设置"/>
    <div className="jj-settings-layout"><LinkTabs label="设置分类" value={selected??'tools'} className="jj-settings-navigation" items={settingsSections.map(item=>({value:item.key,label:item.label,href:'#'+scopedPath(origin?withReturnDestination(settingsPath(item.key),origin):settingsPath(item.key),projectId)}))} onIntent={value=>onPreload(settingsPath(value as typeof settingsSections[number]['key']))}/>
      <div className="jj-settings-content" key={selected}>{children}</div>
    </div>
  </section>
}
