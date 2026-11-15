import {afterEach,expect,it,vi} from 'vitest'
import {recordingsApi} from './recordings'

afterEach(()=>vi.unstubAllGlobals())

it.each([
 {operation:'CONFIRM_TARGET_STEP',step_id:'target'},
 {operation:'CONFIRM_RESOURCE_SLOT',candidate_id:'resource-1234567890abcdef',expected_revision:1},
 {operation:'CONFIRM_VARIABLE_CHOICE',variable_name:'reference',choice_id:'choice-1234567890abcdef'},
 {operation:'REFRESH_RESOURCE_CANDIDATES',expected_revision:1},
])('审阅命令 $operation 可由独立版本 reader 读取',async command=>{
 const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({schema_version:'1',data:{recording:{recording_id:'original',state:'PENDING_REVIEW'}}})))
 vi.stubGlobal('fetch',fetch)
 const result=await recordingsApi.reviewRecording('original',command)
 const [url,init]=fetch.mock.calls[0]
 expect(url).toBe('/api/recordings/original/review')
 expect(JSON.parse(init.body)).toEqual({schema_version:'1',command:{...command,schema_version:'1'}})
 expect(result.recording?.recording_id).toBe('original')
})
