import {render,screen} from '@testing-library/react'
import {expect,it} from 'vitest'
import {RecordingSteps} from './RecordingSteps'
import type {FlowDraftDto} from '../api/recordings'

it('按采集顺序区分前序和本次操作，只公布已经确认的来源',()=>{
 const draft:FlowDraftDto={schema_version:'1',recording_id:'recording',flow_id:'flow',business_action_id:'publish',action_revision:1,subject_test_identity_id:'owner',resource_owner_test_identity_id:'owner',revision:1,target_step_id:'publish',steps:[{id:'read',name:'读取业务状态',resource_candidates:[]},{id:'publish',name:'提交业务操作',resource_candidates:[]}],variables:[{name:'reference',status:'CONFIRMED',candidate_sources:[],confirmed_source:{source_step_id:'read',source_event_sequence:1,json_path:'$.ref'}},{name:'other',status:'UNCONFIRMED',candidate_sources:[{source_step_id:'read',source_event_sequence:1,json_path:'$.other'}]}]}
 render(<RecordingSteps draft={draft} action="发布资料"/>);
 expect(screen.getAllByRole('listitem').map(item=>item.textContent)).toEqual(['读取业务状态后续操作会沿用这一步读取的内容，已确认 1 项来源。','发布资料本次操作'])
 expect(screen.queryByText('提交业务操作')).not.toBeInTheDocument()
})
