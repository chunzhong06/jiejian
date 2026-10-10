// 验证记录选择、准确归属、迟到响应和不依赖Agent的说明阅读。
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {EvidenceVerification} from './EvidenceVerification'
import type {EvidenceRecordIndex,EvidenceRecordView} from '../../../api/checks/currentChecks'
const api=vi.hoisted(()=>({evidenceRecords:vi.fn(),evidenceRecord:vi.fn()}))
vi.mock('../../../api/checks/currentChecks',()=>({currentChecksApi:api}))
vi.mock('../../../shared/ui/AgentAssistEntry',()=>({AgentAssistEntry:()=>null}))
const index:EvidenceRecordIndex={project_id:'p',run_id:'run',case_id:'case',action_id:'action',evidence_id:'evidence',records:[
  {record_id:'obs',kind:'OBSERVATION',label:'最终观察',proof_fingerprint:'proof',observer_id:'source',phase:'EVENTUAL',event_id:null},
  {record_id:'before',kind:'OBSERVATION',label:'操作前',proof_fingerprint:'proof',observer_id:'source',phase:'BEFORE',event_id:null},
  {record_id:'fact',kind:'FACT',label:'第1次提交',proof_fingerprint:null,observer_id:null,phase:null,event_id:null},
  {record_id:'node1',kind:'TRACE',label:'收到请求',proof_fingerprint:null,observer_id:null,phase:null,event_id:'entry'},
  {record_id:'node2',kind:'TRACE',label:'权限判断',proof_fingerprint:null,observer_id:null,phase:null,event_id:'auth'},
]}
const view=(id:string):EvidenceRecordView=>({...index,record:index.records.find(item=>item.record_id===id)!,summary:'封存记录对应这次请求。',published_judgement:'本项出现禁止后果',role:'PROOF',
  verification:[{key:'method',title:'怎样取得这条证据',status:'CONFIRMED',text:'按独立提交比较状态。',record_refs:['fact'],source:{logical_file:'evidence/one.json',pointer:'/observations/0',sha256:'hash'},fragment:{method:'ATOMIC_STATE'}}],
  values:[{label:'状态',before:'仅内部',after:'对外开放'}],location:{logical_file:'evidence/one.json',pointer:'/observations/0',sha256:'hash'},fragment:{state:'CONFIRMED'},related_records:[index.records[2]],limitations:[]})
const props={projectId:'p',runId:'run',caseId:'case',actionId:'action',evidenceId:'evidence',selection:{proof:'proof'},onError:vi.fn(),onRecordChange:vi.fn()}
beforeEach(()=>{vi.clearAllMocks();api.evidenceRecords.mockResolvedValue(index);api.evidenceRecord.mockImplementation(async(_p,_r,_e,_c,id)=>view(id))})
afterEach(cleanup)
it('默认定位同一证明最终观察，可打开对应具体提交及封存片段',async()=>{
  render(<EvidenceVerification {...props}/>);await screen.findByText('按独立提交比较状态。')
  expect(api.evidenceRecord).toHaveBeenLastCalledWith('p','run','evidence','case','obs')
  fireEvent.click(within(screen.getByRole('region',{name:'对应的原始记录'})).getByRole('button',{name:'第1次提交'}))
  await waitFor(()=>expect(api.evidenceRecord).toHaveBeenLastCalledWith('p','run','evidence','case','fact'))
  expect(props.onRecordChange).toHaveBeenLastCalledWith('fact')
  expect(await screen.findByText('之前：仅内部')).toBeInTheDocument()
  fireEvent.click(screen.getByText('打开这条封存片段'))
  expect(screen.getByText(/"state": "CONFIRMED"/)).toBeInTheDocument()
})
it.each(['entry','auth'])('流程节点准确打开自身记录：%s',async event=>{
  render(<EvidenceVerification {...props} selection={{event}}/>);await screen.findByText('按独立提交比较状态。')
  expect(api.evidenceRecord).toHaveBeenLastCalledWith('p','run','evidence','case',event==='entry'?'node1':'node2')
})
it('深链未知记录不退回第一条',async()=>{
  render(<EvidenceVerification {...props} selection={{record:'unknown'}}/>);await waitFor(()=>expect(props.onError).toHaveBeenCalledOnce())
  expect(api.evidenceRecord).not.toHaveBeenCalled()
})
it('只有文档定位的旧记录可展示已有执行核对，不制造观察',async()=>{
  const record={...index.records[0],record_id:'outcome',kind:'OUTCOME' as const,label:'实际执行核对',proof_fingerprint:null,observer_id:null,phase:null}
  api.evidenceRecords.mockResolvedValue({...index,records:[record]})
  api.evidenceRecord.mockResolvedValue({...view('obs'),record,role:'SUPPORTING',values:[],related_records:[]})
  render(<EvidenceVerification {...props} selection={{}}/>);await screen.findByText('实际执行核对')
  expect(api.evidenceRecord).toHaveBeenCalledWith('p','run','evidence','case','outcome')
})
it.each(['project_id','case_id','evidence_id'])('拒绝跨对象索引：%s',async field=>{
  api.evidenceRecords.mockResolvedValue({...index,[field]:'other'})
  render(<EvidenceVerification {...props}/>);await waitFor(()=>expect(props.onError).toHaveBeenCalledOnce())
  expect(api.evidenceRecord).not.toHaveBeenCalled()
})
it('精确阶段与延迟响应不能串到另一个检查项',async()=>{
  let resolve!:(value:EvidenceRecordView)=>void
  api.evidenceRecord.mockImplementation(()=>new Promise(done=>{resolve=done}))
  const rendered=render(<EvidenceVerification {...props} selection={{proof:'proof',phase:'BEFORE'}}/>)
  await waitFor(()=>expect(api.evidenceRecord).toHaveBeenCalledWith('p','run','evidence','case','before'))
  rendered.unmount();await act(async()=>resolve(view('before')))
  expect(props.onError).not.toHaveBeenCalled()
})
