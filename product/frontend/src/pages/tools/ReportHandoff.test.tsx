import {render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {currentChecksApi} from '../../entities/check/api/currentChecks'
import {ReportHandoff} from './ReportHandoff'

afterEach(()=>vi.restoreAllMocks())
it('交接事项不在原报告中时说明缺失，不替换成报告中的其他事项',async()=>{
 const read=vi.spyOn(currentChecksApi,'story').mockResolvedValue({project_id:'app',run_id:'original',actions:[{case_id:'other'}]} as never)
 render(<ReportHandoff projectId="app" runId="original" caseId="missing" href={path=>'#'+path}/>)
 expect(await screen.findByText('交接的检查事项不在这份报告中，请核对原交接位置。')).toBeVisible()
 expect(screen.getByRole('button',{name:'重新读取交接报告'})).toBeVisible()
 expect(screen.queryByRole('link',{name:'阅读这项检查与证据'})).not.toBeInTheDocument()
 await waitFor(()=>expect(read).toHaveBeenCalledOnce())
 expect(read.mock.calls[0][0]).toBe('original')
})
