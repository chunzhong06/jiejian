import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {SourceConfiguration} from './SourceConfiguration'
import {projectsApi} from '../../../entities/application/api/projects'
import {proofSourcesApi,type ProofContext} from '../../../entities/preparation/api/proofSources'

const context:ProofContext={project_id:'app',basis_id:'basis',runtime_available:false,runtime_origin:null,sqlite:[],actions:[],identities:[],resources:[],sources:[],read_scopes:[]}
afterEach(()=>vi.restoreAllMocks())

it.each([true,false])('无可用数据库时根据已有配置恢复，并保留返回证明设置的位置：%s',async(configured)=>{
    location.hash='/preparation?project_id=app&proof_sources=1&source_id=source'
    vi.spyOn(projectsApi,'runtime').mockResolvedValue({project_id:'app',running:false,source_matches:false,operation:null,configuration:configured?{entry:'app.mjs',port:9000,sqlite:[{relative_path:'store.sqlite',tables:[{table:'tickets',resource_column:'id',owner_column:'owner',fields:['title']}]} ]}:null})
    const save=vi.fn(),candidate=vi.spyOn(proofSourcesApi,'sqliteCandidate'),closed=vi.fn()
    render(<SourceConfiguration projectId="app" context={context} onClose={closed} onSave={save}/> )
    expect(await screen.findByText(configured?'先启动已配置的测试应用':'先准备应用的测试数据库')).toBeVisible()
    expect(screen.queryByRole('button',{name:'保存判断方式'})).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'核对应用运行'}))
    await waitFor(()=>expect(location.hash.startsWith('#/application?')).toBe(true))
    const destination=new URLSearchParams(location.hash.split('?')[1]).get('return_to')
    expect(new URLSearchParams(location.hash.split('?')[1]).get('runtime_method')).toBe('managed')
    expect(destination).toBe('/preparation?project_id=app&proof_sources=1&source_id=source')
    expect(closed).toHaveBeenCalledOnce()
    expect(candidate).not.toHaveBeenCalled()
    expect(save).not.toHaveBeenCalled()
})

it('运行设置读取失败时展示重试，不把未知状态说成缺少配置',async()=>{
    vi.spyOn(projectsApi,'runtime').mockRejectedValue(new Error('运行设置暂时不可达'))
    render(<SourceConfiguration projectId="app" context={context} onClose={()=>{}} onSave={vi.fn()}/> )
    expect(await screen.findByText('运行设置暂时不可达')).toBeVisible()
    expect(screen.queryByRole('button',{name:'核对应用运行'})).not.toBeInTheDocument()
})
