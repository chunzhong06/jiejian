import {CommandMenu} from '../../shared/ui/CommandMenu'
import DownOutlined from '@ant-design/icons/DownOutlined'
import PlusOutlined from '@ant-design/icons/PlusOutlined'
import ExperimentOutlined from '@ant-design/icons/ExperimentOutlined'
import AppstoreOutlined from '@ant-design/icons/AppstoreOutlined'
import CheckOutlined from '@ant-design/icons/CheckOutlined'
import type {ProjectDto} from '../../entities/application/api/projects'
import {scopedPath} from '../../shared/lib/navigation'
import {Button} from '../../shared/ui/actions'

export function ApplicationSwitcher({project,projects,choose}:{project?:ProjectDto;projects?:ProjectDto[];choose:(id:string)=>void}) {
  return <div className="jj-project-select"><span className="jj-project-label">当前应用</span>
    <CommandMenu placement="bottomLeft" className="jj-application-menu" menu={{selectable:true,selectedKeys:project?['project:'+project.project_id]:[],
        items:[...(projects??[]).map(item=>({key:'project:'+item.project_id,icon:<AppstoreOutlined aria-hidden="true"/>,label:<span className="jj-command-label"><span>{item.name}</span>{item.project_id===project?.project_id&&<CheckOutlined aria-hidden="true"/>}</span>})),
          ...((projects?.length??0)>0?[{type:'divider' as const}]:[]),
          {key:'create',icon:<PlusOutlined aria-hidden="true"/>,label:<a href={'#'+scopedPath('/application?view=create',project?.project_id)}>新建应用工作区</a>},
          {key:'example',icon:<ExperimentOutlined aria-hidden="true"/>,label:<a href={'#'+scopedPath('/environment',project?.project_id)}>官方示例</a>}],
        onClick:({key})=>{if(key.startsWith('project:'))choose(key.slice(8))}}}>
      <Button className="jj-application-switcher" aria-label={'切换应用，当前：'+(project?.name??'尚未选择')}>
        <span>{project?.name??'选择或新建应用'}</span><DownOutlined aria-hidden="true"/>
      </Button>
    </CommandMenu>
  </div>
}
