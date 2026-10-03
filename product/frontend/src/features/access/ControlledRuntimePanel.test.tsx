// 启动必须先预览；断线与历史回执不能触发重复执行或伪装成当前运行。
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {ControlledRuntimePanel} from './ControlledRuntimePanel'
const api=vi.hoisted(()=>({state:vi.fn(),preview:vi.fn(),start:vi.fn(),operation:vi.fn(),stop:vi.fn(),cancel:vi.fn()}))
vi.mock('../../api/applications/controlledRuntime',()=>({controlledRuntimeApi:api}))
const preview={project_id:'app_a',entry:'app.mjs',port:3000,revision:1,preview_fingerprint:'a'.repeat(64),files:[{relative_path:'app.mjs'}]}
beforeEach(()=>{vi.resetAllMocks();sessionStorage.clear();api.state.mockResolvedValue({project_id:'app_a',operation:null,running:false,source_matches:false});api.preview.mockResolvedValue(preview)})
afterEach(cleanup)
const props={projectId:'app_a',revision:0,sourceAuthorized:false,onChanged:vi.fn(),onEndpoint:vi.fn()}

it('授权只读和预览之后，仍需明确启动',async()=>{
  render(<ControlledRuntimePanel {...props}/>);await waitFor(()=>expect(api.state).toHaveBeenCalled())
  expect(screen.getByRole('button',{name:'预览启动'})).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button',{name:'预览启动'}))
  expect(await screen.findByText('将启动 app.mjs')).toBeInTheDocument()
  expect(api.start).not.toHaveBeenCalled()
  api.start.mockImplementation(async(_project,body)=>({project_id:'app_a',operation_id:body.operation_id,state:'PENDING',receipt:null}))
  fireEvent.click(screen.getByRole('button',{name:'确认启动应用'}))
  expect(await screen.findByText('正在启动')).toBeInTheDocument()
  expect(api.start.mock.calls[0][1]).toMatchObject({revision:1,preview_fingerprint:preview.preview_fingerprint,consent_execute:true})
})

it('写响应丢失后只查询原操作，刷新页面仍保留操作键',async()=>{
  api.start.mockRejectedValue(new Error('network'))
  api.operation.mockResolvedValue(null)
  const view=render(<ControlledRuntimePanel {...props} sourceAuthorized/> )
  await waitFor(()=>expect(screen.getByRole('button',{name:'预览启动'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'预览启动'}))
  fireEvent.click(await screen.findByRole('button',{name:'确认启动应用'}))
  expect(await screen.findByRole('button',{name:'查询原操作结果'})).toBeInTheDocument()
  const original=api.start.mock.calls[0][1].operation_id
  view.unmount();render(<ControlledRuntimePanel {...props} sourceAuthorized/>)
  await waitFor(()=>expect(api.operation).toHaveBeenCalledWith('app_a',original))
  expect(api.start).toHaveBeenCalledTimes(1)
  expect(screen.queryByRole('button',{name:'预览启动'})).not.toBeInTheDocument()
})

it('历史成功回执与当前未运行分别呈现',async()=>{
  api.state.mockResolvedValue({project_id:'app_a',running:false,source_matches:true,
    configuration:{entry:'server.mjs',port:7001,file_count:1},
    operation:{state:'SUCCEEDED',receipt:{reference:{port:3000}}}})
  render(<ControlledRuntimePanel {...props} sourceAuthorized/>)
  expect(await screen.findByText(/已保留上次启动回执/)).toBeInTheDocument()
  expect(screen.getByText('尚未运行')).toBeInTheDocument()
  expect(screen.queryByText('符合要求')).not.toBeInTheDocument()
  expect(api.start).not.toHaveBeenCalled()
  // InputNumber会在收到新属性后同步内部显示；回执文字出现不等于输入已经回填。
  await waitFor(()=>expect(screen.getByRole('spinbutton')).toHaveValue('7001'))
  expect(screen.getByRole('textbox')).toHaveValue('server.mjs')
})

it('取消只针对已经保存的启动操作，不创建新加载',async()=>{
  const operation={project_id:'app_a',operation_id:'a'.repeat(32),state:'PENDING',receipt:null}
  api.state.mockResolvedValue({project_id:'app_a',operation,running:false,source_matches:false})
  api.cancel.mockResolvedValue({...operation,state:'CANCELLED'})
  render(<ControlledRuntimePanel {...props} sourceAuthorized/>)
  fireEvent.click(await screen.findByRole('button',{name:'取消本次启动'}))
  await waitFor(()=>expect(api.cancel).toHaveBeenCalledWith('app_a',operation.operation_id))
  await waitFor(()=>expect(screen.queryByRole('button',{name:'取消本次启动'})).not.toBeInTheDocument())
  expect(api.start).not.toHaveBeenCalled()
})
