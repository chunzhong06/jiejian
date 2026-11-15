import {experienceApi,type OfficialDevelopmentJourneyDto} from '../api/experience'
import {useRead} from '../../../shared/lib/useRead'
import {assertProject} from '../../../shared/model/page'

export function useExampleJourney(projectId:string,enabled:boolean,basis=''){
  return useRead(enabled?'example-journey:'+projectId+':'+basis:null,async signal=>{
    const value=await experienceApi.development(signal)
    assertProject(value.project_id,projectId)
    return value
  })
}

/** 只映射阅读目的和导航；准入及转换仍由正式用例检查。 */
export function exampleTask(journey?:OfficialDevelopmentJourneyDto){
  switch(journey?.stage){
    case 'REQUIREMENTS':return {title:'先确认谁能访问哪份资料',description:'负责人可以取得自己的内部完整包；评审的公开访问与内部资料限制需要分别确认。',label:'确认访问要求',path:'/permissions'}
    case 'BASELINE_CHECK':return {title:'先检查正常实现是否遵守要求',description:'使用真实测试账号核对公开内容、内部资料限制和负责人导出，建立后续修改的比较起点。',label:'准备起始检查',path:'/preparation?prepare_example=1'}
    case 'BASELINE_RESULT':return {title:'正常起点已形成，接着看一次错误修改',description:'本次已检查的样本符合要求。下一段保留这些要求，只改变实现，再看实际业务后果。',label:'查看错误修改',path:'/environment?view=change'}
    case 'CHANGED_CHECK':if(['VULNERABLE','EXPOSE_REVOKE'].includes(journey.implementation))return {title:'修改已加载，接着检查实际后果',description:'原来的资料访问要求继续保留。先核对这份修改使用的材料，再执行真实检查。',label:'准备修改后的检查',path:'/preparation'+(journey.current_change_id?'?change_id='+encodeURIComponent(journey.current_change_id):'')};return undefined
    case 'CHECK_RESULT':if(journey.run_id&&['VULNERABLE','EXPOSE_REVOKE'].includes(journey.implementation))return {title:'这份修改的检查结果已形成',description:'对照原访问要求，阅读这次实际观察到的业务后果，再处理具体问题或深入查证。',label:'阅读修改后的结果',path:'/reports?run_id='+encodeURIComponent(journey.run_id)};return undefined
    default:return undefined
  }
}
