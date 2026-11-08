import {LinkTabs} from '../../shared/ui/Tabs'
import {scopedPath} from '../../shared/lib/navigation'

/** 长期目的地共用稳定导航，具体编辑与执行仍保留自己的准确回程。 */
export function TestingSections({value,projectId}:{value:'materials'|'plans'|'scenarios'|'history';projectId?:string}){
 return <LinkTabs label="测试工作" value={value} items={[
  {value:'plans',label:'检查方案',href:'#'+scopedPath('/testing?view=plans',projectId)},
  {value:'materials',label:'操作与材料',href:'#'+scopedPath('/testing',projectId)},
  {value:'scenarios',label:'业务场景',href:'#'+scopedPath('/testing?scenario=list',projectId)},
  {value:'history',label:'检查记录',href:'#'+scopedPath('/reports',projectId)},
 ]}/>
}
