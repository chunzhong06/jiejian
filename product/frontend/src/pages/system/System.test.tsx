import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {System} from './System'
import {systemApi,type RuntimeDiagnostics,type UpdateOperation} from '../../entities/runtime/api/system'

it('复制失败保留摘要和替代操作，不显示成功',async()=>{
  vi.spyOn(systemApi,'diagnostics').mockResolvedValue({api:'available',worker:'running',browser:'available',checked_at:'2026-10-30T12:00:00Z',runtime_mode:'portable',components:[{key:'worker',label:'执行服务',ready:true}],summary_text:'界鉴诊断摘要'} as RuntimeDiagnostics)
  vi.stubGlobal('navigator',{clipboard:{writeText:vi.fn().mockRejectedValue(new Error('denied'))}})
  render(<System route={{path:'/system',query:new URLSearchParams()}}/>)
  fireEvent.click(await screen.findByRole('button',{name:'复制摘要'}))
  expect(await screen.findByText('未能复制，请下载诊断摘要。')).toBeVisible()
  expect(screen.queryByText('已复制')).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'下载'})).toBeEnabled()
})

it('改选目录使旧预览失效，未知提交只查询原操作',async()=>{
  const operation={operation_id:'upd_test',phase:'PREVIEWED',target_version:'1.3.2',target_release:'old-target',workspace:'data',reason:'',return_path:'/workspace',workspace_upgrade:true} as UpdateOperation
  vi.spyOn(systemApi,'updateInfo').mockResolvedValue({version:'1.3.2',portable:true,release_root:'original',workspace:'data',operation})
  vi.spyOn(systemApi,'previewUpdate').mockResolvedValue({...operation,target_release:'new-target'})
  const confirm=vi.spyOn(systemApi,'confirmUpdate').mockRejectedValue(new TypeError('disconnected'))
  const outcome=vi.spyOn(systemApi,'updateOutcome').mockResolvedValue({...operation,phase:'READY'})
  render(<System route={{path:'/system',query:new URLSearchParams('view=update')}} projectId="app_test"/>)
  expect(await screen.findByText(/此次切换将升级工作区结构/)).toBeVisible()
  fireEvent.click(await screen.findByRole('button',{name:'更换发行目录'}))
  const input=screen.getByLabelText('新版本所在目录')
  fireEvent.change(input,{target:{value:'new-target'}})
  expect(screen.queryByRole('button',{name:'停止并切换版本'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'预览更新'}))
  fireEvent.click(await screen.findByRole('button',{name:'停止并切换版本'}))
  expect(await screen.findByText(/更新请求结果尚未确认/)).toBeVisible()
  expect(screen.getByRole('heading',{name:'交接状态待确认'})).toBeVisible()
  expect(confirm).toHaveBeenCalledTimes(1)
  expect(screen.queryByRole('button',{name:'停止并切换版本'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'查询更新结果'}))
  await waitFor(()=>expect(outcome).toHaveBeenCalledWith('upd_test'))
  expect(await screen.findByRole('heading',{name:'版本切换已完成'})).toBeVisible()
  expect(screen.queryByLabelText('新版本所在目录')).not.toBeInTheDocument()
  expect(screen.getByRole('link',{name:'返回应用'})).toHaveAttribute('href','#/workspace?project_id=app_test')
  fireEvent.click(screen.getByRole('button',{name:'选择其他发行目录'}))
  expect(screen.getByLabelText('新版本所在目录')).toHaveValue('')
})
