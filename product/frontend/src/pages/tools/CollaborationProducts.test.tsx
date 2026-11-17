import {cleanup,fireEvent,render,screen,within} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {Collaboration} from './Collaboration'
import {CollaborationArtifactReview} from './CollaborationArtifactReview'

afterEach(()=>{cleanup();vi.unstubAllGlobals()})
const response=(data:unknown)=>new Response(JSON.stringify({schema_version:'1',data}),{headers:{'content-type':'application/json'}})
const proofReview={id:'proof-a',title:'核对发布结果的判断方式',destination:'/preparation?proof_sources=1&source_id=proof-a&revision=2',action_label:'审阅判断方式与读取范围'}
const proofOperation={state:'SUCCEEDED',capability:'proofs.save',result:{source_id:'proof-a',revision:2}}
const proofContext={project_id:'app',sources:[{source_id:'proof-a',revision:2,adopted:false,read_scope_confirmed:false,config:{action_id:'publish',action_revision:1,effect_id:'published',resource_binding_id:'alpha-binding',source_kind:'JSON_HTTP_RESOURCE'}}],actions:[{action_id:'publish',revision:1,label:'发布资料',effects:[{effect_id:'published',label:'资料对成员可见'}]}],resources:[{resource_binding_id:'alpha-binding',resource_id:'alpha',owner_identity_id:'owner'}],identities:[{identity_id:'owner',label:'资料负责人'}]}

it('证明产物先读准确业务对象和准备事实，只读审阅不批准读取或采用',async()=>{
 const requests:string[]=[]
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{expect(init?.method??'GET').toBe('GET');requests.push(String(input));return response(proofContext)}))
 render(<CollaborationArtifactReview projectId="app" task={{task_id:'task',operations:[proofOperation]} as never} review={proofReview}/>)
 expect(await screen.findByRole('heading',{name:'发布资料'})).toBeVisible()
 expect(screen.getByText('用来判断：资料对成员可见')).toBeVisible()
 expect(screen.getByText('alpha')).toBeVisible()
 expect(screen.getByText('等待允许读取')).toBeVisible()
 expect(screen.getByText('尚未用于检查')).toBeVisible()
 const link=screen.getByRole('link',{name:proofReview.action_label})
 const query=new URLSearchParams(link.getAttribute('href')!.split('?')[1])
 expect(query.get('revision')).toBe('2')
 const origin=new URLSearchParams(query.get('return_to')!.split('?')[1])
 expect(origin.get('task_item')).toBe('review:proof-a')
 expect(requests).toEqual(['/api/projects/app/proof-preparation'])
})

it('来源新修订明确另行核对，旧产物不冒充当前配置',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>response({...proofContext,sources:[{...proofContext.sources[0],revision:3}]})))
 render(<CollaborationArtifactReview projectId="app" task={{task_id:'task',operations:[proofOperation]} as never} review={proofReview}/>)
 expect(await screen.findByText('原候选已有新修订')).toBeVisible()
 expect(screen.queryByRole('link',{name:proofReview.action_label})).not.toBeInTheDocument()
 expect(screen.queryByRole('heading',{name:'发布资料'})).not.toBeInTheDocument()
 const current=new URLSearchParams(screen.getByRole('link',{name:'核对当前判断方式'}).getAttribute('href')!.split('?')[1])
 expect(current.get('revision')).toBe('3');expect(current.get('source_id')).toBe('proof-a')
 expect(new URLSearchParams(current.get('return_to')!.split('?')[1]).get('task_item')).toBe('review:proof-a')
})

it('项目变化时停止读取，不显示其他项目的同名配置',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>response({...proofContext,project_id:'another-app'})))
 render(<CollaborationArtifactReview projectId="app" task={{task_id:'task',operations:[proofOperation]} as never} review={proofReview}/>)
 expect(await screen.findByRole('alert')).toBeVisible()
 expect(screen.queryByRole('link',{name:proofReview.action_label})).not.toBeInTheDocument()
 expect(screen.queryByRole('heading',{name:'发布资料'})).not.toBeInTheDocument()
})

it('同份流程链接改指其他业务时重新核对，不复用上一份候选读取',async()=>{
 const document={id:'flow',revision:2,business_action_id:'publish',action_revision:1,subject_test_identity_id:'owner',resource_owner_test_identity_id:'owner',actual_resource_id:'alpha',workflow:{target_step_id:'target',steps:[]},recovery:null}
 const review={id:'flow@2',title:'发布流程',destination:'/testing?flow_id=flow&revision=2&action_id=publish',action_label:'核对流程'}
 const task={task_id:'task',operations:[{state:'SUCCEEDED',capability:'flows.save',result:{id:'flow',revision:2}}]}
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>{
  const path=String(input)
  return response(path.includes('/test-identities')?[]:path.endsWith('/flow/2')?document:{project_id:'app',flows:[]})
 }))
 const view=render(<CollaborationArtifactReview projectId="app" task={task as never} review={review}/>)
 expect(await screen.findByRole('link',{name:'进入流程继续核对'})).toBeVisible()
 view.rerender(<CollaborationArtifactReview projectId="app" task={task as never} review={{...review,destination:review.destination.replace('action_id=publish','action_id=withdraw')}}/>)
 expect(await screen.findByRole('alert')).toHaveTextContent('产物关联已变化')
 expect(screen.queryByRole('link',{name:'进入流程继续核对'})).not.toBeInTheDocument()
})

it('多份证明及已审阅场景各保留入口，回程恢复产物页签',async()=>{
 const task={task_id:'task',project_id:'app',goal:'准备发布与撤回',purpose:'SETUP',state:'COMPLETED',references:{},questions:[],events:[],reviews:[],operations:[proofOperation,{...proofOperation,result:{source_id:'proof-b',revision:1}},{state:'SUCCEEDED',capability:'scenarios.save',result:{id:'scenario-a',revision:4}}]}
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>response(String(input).includes('executor')?{available:false}:String(input).endsWith('/activity')?[]:task)))
 render(<Collaboration projectId="app" taskId="task" initialView="context"/>)
 const table=await screen.findByRole('table')
 const links=within(table).getAllByRole('link')
 expect(links).toHaveLength(3)
 expect(links.map(link=>new URLSearchParams(link.getAttribute('href')!.split('?')[1]).get('source_id'))).toEqual(['proof-a','proof-b',null])
 const scenario=new URLSearchParams(links[2].getAttribute('href')!.split('?')[1])
 expect(scenario.get('scenario')).toBe('scenario-a');expect(scenario.get('revision')).toBe('4')
 expect(new URLSearchParams(scenario.get('return_to')!.split('?')[1]).get('task_view')).toBe('context')
})

it('返回准确待审产物时保留选择，其他待答问题不抢占当前事项',async()=>{
 const task={task_id:'task',project_id:'app',goal:'准备发布',purpose:'SETUP',state:'WAITING_USER',references:{},events:[],reviews:[proofReview],operations:[proofOperation],questions:[{question_id:'question',question:'归档后是否允许发布？',options:[],answer:null}]}
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>{const path=String(input);return response(path.includes('proof-preparation')?proofContext:path.includes('executor')?{available:false}:path.endsWith('/activity')?[]:task)}))
 render(<Collaboration projectId="app" taskId="task" initialView="work" initialItem="review:proof-a"/>)
 expect(await screen.findByRole('heading',{name:'发布资料'})).toBeVisible()
 expect(screen.queryByLabelText('你的回答或补充说明')).not.toBeInTheDocument()
 fireEvent.click(screen.getByRole('tab',{name:'产物与相关资料'}))
 fireEvent.click(screen.getByRole('button',{name:'查看待审阅内容'}))
 expect(await screen.findByRole('heading',{name:'发布资料'})).toBeVisible()
})

it('旧长问题保留原文，原始委派退入资料，不从原文猜测业务摘要',async()=>{
 const goal='在现有应用中整理流程、结果证明和正常对照。'.repeat(6)
 const question='请核对当前资料对应的读取位置和资源归属，再补充缺少的说明。'.repeat(5)
 const task={task_id:'task',project_id:'app',goal,purpose:'SETUP',state:'WAITING_USER',references:{},events:[],reviews:[],operations:[],questions:[{question_id:'question',question,options:[],answer:null}]}
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>response(String(input).includes('executor')?{available:false}:String(input).endsWith('/activity')?[]:task)))
 render(<Collaboration projectId="app" taskId="task"/>)
 expect(await screen.findByRole('heading',{name:'补充任务信息',level:1})).toBeVisible()
 const original=screen.getByText('原始问题与补充依据').closest('details')!
 expect(original).not.toHaveAttribute('open')
 expect(within(original).getByText(question)).toBeInTheDocument()
 fireEvent.click(within(original).getByText('原始问题与补充依据'))
 expect(original).toHaveAttribute('open')
 fireEvent.click(screen.getByRole('tab',{name:'产物与相关资料'}))
 const details=screen.getByText('原始委派说明').closest('details')!
 expect(within(details).getByText(goal)).toBeInTheDocument()
 expect(details).not.toHaveAttribute('open')
})

it('具体问题与回答直接可读，技术原文展开不提交答案或启动模型',async()=>{
 const task={task_id:'task',project_id:'app',goal:'准备资料发布检查',purpose:'SETUP',state:'WAITING_USER',references:{},events:[],reviews:[],operations:[],questions:[{question_id:'question',question:'runtime.read 未取得配置。请核对具体来源。',options:['我来指定来源'],answer:null,presentation:{title:'用什么依据确认资料已经发布？',reason:'还缺少实际发布状态的读取依据。',answer_hint:'可以指定数据来源，或让 Agent 继续查找。'}}]}
 const writes:string[]=[]
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{if(init?.method==='POST')writes.push(String(input));return response(String(input).includes('executor')?{available:false}:String(input).endsWith('/activity')?[]:task)}))
 render(<Collaboration projectId="app" taskId="task"/>)
 expect(await screen.findByRole('heading',{name:task.questions[0].presentation.title,level:1})).toBeVisible()
 expect(screen.getByText(task.questions[0].presentation.reason)).toBeVisible()
 expect(screen.getByText(task.questions[0].presentation.answer_hint)).toBeVisible()
 expect(screen.getByRole('radio',{name:'我来指定来源'})).not.toBeChecked()
 const original=screen.getByText('原始问题与补充依据').closest('details')!
 expect(original).not.toHaveAttribute('open')
 fireEvent.click(within(original).getByText('原始问题与补充依据'))
 expect(within(original).getByText(task.questions[0].question)).toBeVisible()
 expect(writes).toEqual([])
})

it('场景产物复用准确修订的正常与变化阅读，不执行场景',async()=>{
 const review={id:'scene@3',title:'核对发布与撤回实验',destination:'/testing?scenario=scene&revision=3',action_label:'审阅场景与正常对照'}
 const document={id:'scene',project_id:'app',revision:3,label:'发布资料',description:'先发布，再撤回；比较正常流程与省略步骤。',experiments:[{id:'normal',label:'正常发布与撤回',kind:'NORMAL',invocations:[{id:'publish',label:'发布资料',batch:null},{id:'withdraw',label:'撤回资料',batch:null}]},{id:'omit',label:'省略发布直接撤回',kind:'OMIT',invocations:[{id:'withdraw',label:'直接撤回资料',batch:null}]}]}
 const requests:string[]=[]
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{expect(init?.method??'GET').toBe('GET');requests.push(String(input));return response(document)}))
 render(<CollaborationArtifactReview projectId="app" task={{task_id:'task',operations:[{state:'SUCCEEDED',capability:'scenarios.save',result:{id:'scene',revision:3}}]} as never} review={review}/>)
 const experiment=await screen.findByRole('button',{name:/正常发布与撤回/})
 expect(experiment).toHaveAttribute('aria-expanded','false')
 fireEvent.click(experiment)
 expect(screen.getByRole('heading',{name:'正常发布与撤回'})).toBeVisible()
 expect(screen.getByRole('link',{name:review.action_label})).toHaveAttribute('href',expect.stringContaining('revision=3'))
 expect(requests).toContain('/api/projects/app/business-scenarios/scene/3')
 expect(requests.some(path=>path.startsWith('/api/projects/app/business-scenarios/context?scenario_id=scene&revision=3'))).toBe(true)
})
