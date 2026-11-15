import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {Run} from './CheckRun'
import {currentChecksApi as api,type CheckStatus} from '../../entities/check/api/currentChecks'
import {experienceApi} from '../../entities/application/api/experience'
import {story} from './report/Report.fixtures'

const status:CheckStatus={run:{run_id:'run-task',project_id:'run-project',lifecycle:'RUNNING',verdict:null,plan_fingerprint:'a'.repeat(64),policy_epoch:1,created_at_us:1,finished_at_us:null},job:{job_id:'job-task',state:'RUNNING',attempt:1,cancel_requested:false},progress:{phase:'EXECUTING',completed_cases:2,planned_cases:2,current_case:{case_id:'case',action_label:'下载公开文件',expectation:'ALLOW',planned_subject_label:'评审账号',planned_resource_owner_label:'项目负责人',resource_id:'public-file',effect_labels:['收到完整文件']}},result_integrity:'NOT_PUBLISHED'}
const props={projectId:'run-project',runId:'run-task',name:'本机测试',official:false,route:{path:'/reports',query:new URLSearchParams()},refresh:vi.fn(),onError:vi.fn()}
afterEach(()=>vi.restoreAllMocks())

it('检查数已返回仍按真实阶段显示，停止只提交原任务并等待实际结束',async()=>{
 vi.spyOn(api,'status').mockResolvedValueOnce(status).mockResolvedValue({...status,job:{...status.job!,cancel_requested:true}})
 const story=vi.spyOn(api,'story'),cancel=vi.spyOn(api,'cancel').mockResolvedValue(undefined as never)
 render(<Run {...props}/>)
 expect(await screen.findByRole('heading',{name:'正在核对业务结果'})).toBeVisible()
 expect(screen.getByText('已完成 2 / 2 项')).toBeVisible()
 expect(screen.getByRole('heading',{name:'下载公开文件'})).toBeVisible()
 fireEvent.click(screen.getByRole('button',{name:'停止这次检查'}))
 await waitFor(()=>expect(screen.getByRole('heading',{name:'正在停止这次检查'})).toBeVisible())
 expect(screen.getByRole('button',{name:'正在停止'})).toBeDisabled()
 expect(cancel).toHaveBeenCalledExactlyOnceWith('job-task');expect(story).not.toHaveBeenCalled()
})

it.each(['QUEUED','FINALIZING','INVALID'] as const)('准确表达排队、汇总与报告不可用：%s',async(mode)=>{
 const value:CheckStatus=mode==='QUEUED'?{...status,run:{...status.run,lifecycle:'QUEUED'},progress:null}:mode==='FINALIZING'?{...status,progress:{...status.progress!,phase:'FINALIZING',current_case:null}}:{...status,run:{...status.run,lifecycle:'FAILED'},result_integrity:'INVALID',job:{...status.job!,state:'FAILED',error_code:'JOB_FAILED',cause_code:'TARGET_UNREACHABLE'}}
 vi.spyOn(api,'status').mockResolvedValue(value);const story=vi.spyOn(api,'story')
 render(<Run {...props}/>)
 expect(await screen.findByRole('heading',{name:mode==='QUEUED'?'已提交，等待执行':mode==='FINALIZING'?'正在收尾并核对记录':'报告未通过完整性校验'})).toBeVisible()
 if(mode==='INVALID'){expect(screen.getByRole('link',{name:'核对应用连接'})).toHaveAttribute('href',expect.stringContaining('return_to='));expect(screen.queryByRole('button',{name:'停止这次检查'})).not.toBeInTheDocument()}
 expect(story).not.toHaveBeenCalled()
})

it.each(['current','historical','foreign'] as const)('示例下一步只属于准确当前报告：%s',async(mode)=>{
 const value={...story(),verdict:'PASS' as const}
 vi.spyOn(api,'status').mockResolvedValue({...status,run:{...status.run,project_id:value.project_id,run_id:value.run_id,lifecycle:'COMPLETED',verdict:'PASS'},result_integrity:'VALID',job:null,progress:null})
 vi.spyOn(api,'story').mockResolvedValue(value)
 const journey={project_id:mode==='foreign'?'another-project':value.project_id,implementation:'BASELINE' as const,delivery_source:'PRESET_DEMONSTRATION' as const,run_id:mode==='historical'?'newer-run':value.run_id,verdict:'PASS' as const,can_optimize:true,repair_verified:false,evidence_limited:false,reason:'原发布事实',transition_basis:'basis',change_options:[],policy_epoch:3,stage:'BASELINE_RESULT' as const}
 // 首次读取发生在报告形成之前；正式结果到达后必须按新依据重读。
 vi.spyOn(experienceApi,'development').mockResolvedValueOnce({...journey,stage:'BASELINE_CHECK',run_id:null,verdict:null,can_optimize:false}).mockResolvedValue(journey)
 render(<Run {...props} projectId={value.project_id} runId={value.run_id} official/>)
 if(mode==='current')expect(await screen.findByRole('link',{name:'查看错误修改'})).toHaveAttribute('href',expect.stringContaining('view=change'))
 else expect(await screen.findByRole('link',{name:'沿用本次范围继续检查'})).toBeVisible()
 await waitFor(()=>expect(api.story).toHaveBeenCalled())
 if(mode!=='current')expect(screen.queryByRole('link',{name:'查看错误修改'})).not.toBeInTheDocument()
})
