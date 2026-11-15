import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {Changes} from './Changes';
import {sourceChangesApi, type SourceChangeViewDto} from '../../entities/source-change/api/sourceChanges';
import {developmentApi} from '../../entities/source-change/api/development';
import {refreshCurrentPage} from '../../shared/lib/pageRefresh';

vi.mock('../../entities/permission/ui/DiscoveryCoverage', () => ({CurrentDiscoveryCoverage:() => null}));
vi.mock('../../entities/source-change/ui/RuntimeActivation', () => ({RuntimeActivation:() => <p>原运行加载工作面</p>}));
const record = (id:string, reason='修正订单读取范围'):SourceChangeViewDto => ({
  manifest:{change_id:id, project_id:'app', reason, submitted_by:'LOCAL_GUI', created_at_us:1, claimed_paths:[], repair_reference:null},
  change_set:{status:'COMPARABLE', added_paths:[], modified_paths:['orders.py'], removed_paths:[]},
  assessment:{payload:{policy_epoch:1, permission_refs:[], action_impacts:[]}},
  revalidation:{status:'READY', can_execute:true, preparation_gaps:[]},
});
const props = {projectId:'app', name:'订单', official:false, refresh:vi.fn(), onError:vi.fn()};
const page = (query='') => <Changes {...props} route={{path:'/changes', query:new URLSearchParams(query)}}/>;
beforeEach(() => {
  sessionStorage.clear();
  location.hash = '#/apps/app/changes';
  vi.spyOn(sourceChangesApi, 'list').mockResolvedValue([record('recent')]);
  vi.spyOn(sourceChangesApi, 'show').mockResolvedValue(record('older'));
  vi.spyOn(developmentApi, 'details').mockResolvedValue(null);
});
afterEach(() => {vi.restoreAllMocks(); sessionStorage.clear();});

it('准确深链接读取窗口之外的原记录，不先读取最近列表', async () => {
  render(page('change_id=older'));
  expect(await screen.findByRole('heading', {name:'修正订单读取范围'})).toBeVisible();
  expect(sourceChangesApi.show).toHaveBeenCalledWith('app', 'older');
  expect(sourceChangesApi.list).not.toHaveBeenCalled();
  const preview = screen.getByRole('link', {name:'预览修改后检查'});
  expect(preview.getAttribute('href')).toContain('change_id=older');
  expect(preview.getAttribute('href')).toContain('return_to=');
});

it('运行版本尚未核对时，先完成原加载任务，保留历史报告而不并列推进材料',async()=>{
  vi.mocked(sourceChangesApi.show).mockResolvedValue({...record('older'),revalidation:{status:'READY',can_execute:false,preparation_gaps:[{reason:'TEST_IDENTITY_LOGIN_REQUIRED'}]}})
  vi.mocked(developmentApi.details).mockResolvedValue({project_id:'app',verification:{run_id:'historical',verdict:'PASS'},delivery:{change_id:'older'}} as never)
  render(page('change_id=older'))
  expect(await screen.findByRole('heading',{name:'先核对这批代码的运行版本'})).toBeVisible()
  expect(screen.getByText('原运行加载工作面')).toBeVisible()
  expect(screen.queryByRole('link',{name:'核对准备材料'})).not.toBeInTheDocument()
  expect(screen.getByRole('link',{name:'阅读本批报告'})).toHaveAttribute('href',expect.stringContaining('run_id=historical'))
})

it('缺失或错配记录保持准确入口，不显示别的记录或执行入口', async () => {
  vi.mocked(sourceChangesApi.show).mockResolvedValue(record('other'));
  render(page('change_id=missing'));
  expect(await screen.findByText('修改记录与所选对象不一致。')).toBeVisible();
  expect(screen.getByRole('button', {name:'全部修改记录'})).toBeEnabled();
  expect(screen.queryByRole('link', {name:'预览修改后检查'})).not.toBeInTheDocument();
  expect(screen.queryByText('尚未登记源码修改')).not.toBeInTheDocument();
});

it('筛选无结果可以恢复，按文件路径查询仍保留准确记录', async () => {
  render(page());
  const input = await screen.findByRole('searchbox', {name:'查找修改记录'});
  fireEvent.change(input, {target:{value:'unmatched'}});
  expect(await screen.findByText('没有匹配的修改记录')).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name:'清除查找'}));
  fireEvent.change(input, {target:{value:'orders.py'}});
  await waitFor(() => expect(screen.getByRole('button', {name:/修正订单读取范围/})).toBeVisible());
  fireEvent.click(screen.getByRole('button', {name:/修正订单读取范围/}));
  expect(location.hash).toContain('change_id=recent');
});

it('登记事实与当前核对分开，已有成功结果不被源码过期覆盖', async () => {
  vi.mocked(sourceChangesApi.show).mockResolvedValue({...record('older'),revalidation:{status:'SOURCE_STALE',can_execute:false,preparation_gaps:[]}});
  vi.mocked(developmentApi.details).mockResolvedValue({project_id:'app', delivery:{change_id:'older'}, verification:{run_id:'original-run', verdict:'PASS', repair_status:'VERIFIED'}} as never);
  render(page('change_id=older'));
  expect(await screen.findByText('原问题修复已验证')).toBeVisible();
  expect(screen.getByRole('heading',{name:'当前源码已有变化，先登记这次修改'})).toBeVisible();
  expect(screen.getByRole('link', {name:'阅读本批报告'}).getAttribute('href')).toContain('run_id=original-run');
  expect(screen.getByText('登记时的文件变化 · 1 个文件')).toBeVisible();
  expect(screen.getByRole('link',{name:'登记当前源码修改'}).getAttribute('href')).toContain('view=register');
  expect(screen.queryByRole('link',{name:'预览修改后检查'})).not.toBeInTheDocument();
});

it('没有数据与读取失败各自表达，不用空态掩盖错误', async () => {
  vi.mocked(sourceChangesApi.list).mockRejectedValue(new Error('读取修改记录失败'));
  render(page());
  expect(await screen.findByText('读取修改记录失败')).toBeVisible();
  expect(screen.queryByText('尚未登记源码修改')).not.toBeInTheDocument();
});

it('历史页保留游标、准确回程和读取范围，末页不冒充从未登记',async()=>{
  vi.mocked(sourceChangesApi.list).mockResolvedValue([]);
  render(page('before_change_id=anchor'));
  expect(await screen.findByText('没有更早的修改记录')).toBeVisible();
  expect(sourceChangesApi.list).toHaveBeenCalledWith('app',50,'anchor');
  expect(screen.getByRole('link',{name:'返回最近记录'})).toBeVisible();
  expect(screen.queryByText('尚未登记源码修改')).not.toBeInTheDocument();
});

it('当前核对刷新失败保留原登记与已关联报告，重新读取前不推进旧状态',async()=>{
  vi.mocked(developmentApi.details).mockResolvedValue({project_id:'app',delivery:{change_id:'older'},verification:{run_id:'original-run',verdict:'PASS'}} as never);
  render(page('change_id=older'));
  expect(await screen.findByRole('link',{name:'阅读本批报告'})).toBeVisible();
  vi.mocked(sourceChangesApi.show).mockRejectedValueOnce(new Error('离线'));
  await refreshCurrentPage();
  expect(await screen.findByText('当前状态待重核')).toBeVisible();
  expect(screen.getByText('登记时的文件变化 · 1 个文件')).toBeVisible();
  expect(screen.getByRole('link',{name:'阅读本批报告'})).toBeVisible();
  expect(screen.queryByRole('link',{name:'预览修改后检查'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'重新读取当前核对'}));
  expect(await screen.findByRole('link',{name:'预览修改后检查'})).toBeVisible();
});

it.each([
  ['POLICY_STALE','核对变更要求','/permissions'],
  ['MAPPING_REVIEW_REQUIRED','核对业务实现','view=business'],
  ['NO_BASELINE','核对源码与运行','view=source'],
] as const)('当前状态 %s 先回到对应前置任务，保留准确回程',async(status,label,target)=>{
  vi.mocked(sourceChangesApi.show).mockResolvedValue({...record('older'),revalidation:{status,can_execute:false,preparation_gaps:[]}});
  render(page('change_id=older'));
  const action=await screen.findByRole('link',{name:label});
  expect(action.getAttribute('href')).toContain(target);
  expect(action.getAttribute('href')).toContain('return_to=');
  expect(screen.queryByRole('link',{name:'预览修改后检查'})).not.toBeInTheDocument();
});

it('材料缺口保留本次修改定位，读历史报告不代替新检查',async()=>{
  vi.mocked(sourceChangesApi.show).mockResolvedValue({...record('older'),revalidation:{status:'READY',can_execute:false,preparation_gaps:[{reason:'IDENTITY_REQUIRED'}]}});
  render(page('change_id=older'));
  expect((await screen.findByRole('link',{name:'核对准备材料'})).getAttribute('href')).toContain('change_id=older');
  expect(screen.queryByRole('link',{name:'预览修改后检查'})).not.toBeInTheDocument();
});
