import {fireEvent,render,screen} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import type {PreparationBatch} from '../../entities/preparation/api/batches'
import {BatchProgress} from './BatchProgress'

const batch:PreparationBatch={schema_version:'1',project_id:'project',operation_id:'batch',state:'RUNNING',cancel_requested:false,message:'正在准备操作流程',error_code:null,completed:0,total:0,preflight_id:null,updated_at_us:1,phase:'RECIPE_RUNNING',identities:[{account:'judge',state:'PREPARED'}]}

it('账号阶段不显示来源的零总数，来源阶段只显示后台实际完成数',()=>{
  const view=render(<BatchProgress batch={batch} onCancel={()=>{}}/>)
  expect(screen.getByRole('heading',{name:'正在准备示例账号和操作'})).toBeVisible()
  expect(screen.queryByText('0 / 0')).not.toBeInTheDocument()
  expect(screen.getByRole('progressbar')).not.toHaveAttribute('value')
  view.rerender(<BatchProgress batch={{...batch,phase:'NEXT',total:4}} onCancel={()=>{}}/>)
  expect(screen.getByRole('progressbar')).toHaveAttribute('value','0')
  expect(screen.getByText('0 / 4')).toBeVisible()
  view.rerender(<BatchProgress batch={{...batch,phase:'NEXT',total:4,completed:2,items:[{label:'业务结果',state:'READY'}]}} onCancel={()=>{}}/>)
  expect(screen.getByRole('progressbar')).toHaveAttribute('value','2')
  expect(screen.getByText('2 / 4')).toBeVisible()
  expect(screen.getByText('已就绪')).toBeVisible()
})

it('停止准备只调用原取消操作，等待回执时禁止重复提交',()=>{
  const cancel=vi.fn()
  const view=render(<BatchProgress batch={batch} onCancel={cancel}/>)
  fireEvent.click(screen.getByRole('button',{name:'停止准备'}))
  expect(cancel).toHaveBeenCalledOnce()
  view.rerender(<BatchProgress batch={{...batch,cancel_requested:true,state:'CANCELLING'}} onCancel={cancel}/>)
  expect(screen.getByRole('button',{name:'正在停止'})).toBeDisabled()
})
