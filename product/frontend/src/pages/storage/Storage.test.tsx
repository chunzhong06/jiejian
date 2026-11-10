import {fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {Storage} from './Storage'
import {systemApi} from '../../entities/runtime/api/system'
import {ApiError} from '../../shared/api/http'

afterEach(()=>{vi.restoreAllMocks();sessionStorage.clear()})

it('环境占用时保留清理入口，释放后重新预览，不自动执行删除',async()=>{
 vi.spyOn(systemApi,'maintenanceStatus').mockResolvedValue({protected:{data:'data'},inventory:[{category:'builds',label:'旧构建',relative_path:'frontend/old',state:'CLEANABLE',bytes:10,reason:'闲置'}],entries:{}} as never)
 const preview=vi.spyOn(systemApi,'maintenanceOperation').mockRejectedValueOnce(new ApiError('LOCAL_MAINTENANCE_FAILED','正在准备',undefined,undefined,false,'ENVIRONMENT_BUSY')).mockResolvedValue({plan_id:'plan',scope:'clear-all',expires_at_us:Date.now()*1000+1000000,targets:[],estimated_bytes:0} as never)
 render(<Storage/>);fireEvent.click(screen.getByRole('button',{name:'扫描本地存储'}))
 fireEvent.click(await screen.findByRole('button',{name:'预览清理'}))
 expect(await screen.findByText(/运行环境正在准备，清理尚未开始/)).toBeVisible()
 fireEvent.click(screen.getByRole('button',{name:'预览清理'}))
 expect(await screen.findByRole('heading',{name:'核对清理项目'})).toBeVisible()
 expect(preview).toHaveBeenCalledTimes(2)
 expect(preview.mock.calls.every(([,body])=>body.confirmed===false&&body.dry_run===true)).toBe(true)
 expect(sessionStorage.getItem('jiejian.maintenance.pending')).toBeNull()
})
