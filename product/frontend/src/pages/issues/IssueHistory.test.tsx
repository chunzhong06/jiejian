import {fireEvent,render,screen} from '@testing-library/react'
import {expect,it} from 'vitest'
import {IssueHistory} from './IssueHistory'
import type {RepairHistoryEvent} from '../../entities/check/api/repairs'

it('连续观察定位两次准确记录并保留原问题回程；中断不产生比较入口',()=>{
 const event=(kind:RepairHistoryEvent['kind'],run_id:string,created_at_us:number):RepairHistoryEvent=>({kind,run_id,created_at_us,source_run_id:'original',status:null,change_id:null,reason_codes:[]})
 render(<IssueHistory origin="/issues?issue=exact" events={[event('FOUND','first',1),event('CHECK_INTERRUPTED','interrupted',2),event('RECURRED','again',3)]}/> )
 expect(screen.getAllByRole('link',{name:'与上次观察比较'})).toHaveLength(1)
 fireEvent.click(screen.getByRole('link',{name:'与上次观察比较'}))
 const query=new URLSearchParams(location.hash.split('?')[1])
 expect(query.get('baseline')).toBe('first')
 expect(query.get('current')).toBe('again')
 expect(query.get('return_to')).toBe('/issues?issue=exact')
})
