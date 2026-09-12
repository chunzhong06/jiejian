// 任务导航只转交服务端对象定位，不创建运行或猜下一任务。
import {expect,it} from 'vitest'
import type {PrimaryTaskDto} from '../api/workspace'
import {taskDestination} from './taskDestination'
const task={task_id:'current / slot',task_kind:'PREPARE_TEST_IDENTITY',route:'/tests',run_id:null,change_id:null} as PrimaryTaskDto
it('准备任务把精确任务 ID 带入正式准备页',()=>expect(taskDestination(task)).toBe('/tests?task_id=current+%2F+slot'))
it('原题复验保留精确变化，结果入口保留原 Run',()=>{
 expect(taskDestination({...task,task_kind:'VERIFY_REPAIR',change_id:'change-one'})).toBe('/tests?change_id=change-one')
 expect(taskDestination({...task,task_kind:'VIEW_CURRENT_RESULT',run_id:'run-one'})).toBe('/tests?run_id=run-one')
})
