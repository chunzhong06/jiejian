import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { RuntimeConnection } from './RuntimeConnection';
import { projectsApi as api } from '../../entities/application/api/projects';

const idle = { project_id: 'app', running: false, source_matches: false, configuration: { entry: 'app.mjs', port: 3000 }, operation: null };
const preview = { project_id: 'app', entry: 'app.mjs', port: 3000, revision: 1, preview_fingerprint: 'preview', files: [{ relative_path: 'app.mjs' }] };
const props = { projectId: 'app', revision: 1, confirmedEndpoint: 'http://127.0.0.1:4000', canStart: true, onChanged: vi.fn(), onError: vi.fn() };

afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); });

it('切换运行方式保留草稿，不提交地址或启动进程', async () => {
    vi.spyOn(api, 'runtime').mockResolvedValue(idle);
    const confirm = vi.spyOn(api, 'confirmEndpoint');
    const start = vi.spyOn(api, 'runtimeStart');
    render(<RuntimeConnection {...props}/>);
    fireEvent.change(screen.getByRole('textbox', { name: '应用地址' }), { target: { value: 'http://127.0.0.1:5000' } });
    fireEvent.click(screen.getByRole('radio', { name: '由界鉴启动' }));
    const entry = await screen.findByRole('textbox', { name: 'Node 入口文件' });
    fireEvent.change(entry, { target: { value: 'server.mjs' } });
    fireEvent.click(screen.getByRole('radio', { name: '连接已有应用' }));
    expect(screen.getByRole('textbox', { name: '应用地址' })).toHaveValue('http://127.0.0.1:5000');
    fireEvent.click(screen.getByRole('radio', { name: '由界鉴启动' }));
    expect(screen.getByRole('textbox', { name: 'Node 入口文件' })).toHaveValue('server.mjs');
    expect(confirm).not.toHaveBeenCalled();
    expect(start).not.toHaveBeenCalled();
});

it('连接已有应用只提交指定地址，不取得启动进程的权限', async () => {
    const confirm = vi.spyOn(api, 'confirmEndpoint').mockResolvedValue({} as never);
    const runtime = vi.spyOn(api, 'runtime');
    const start = vi.spyOn(api, 'runtimeStart');
    const changed = vi.fn();
    render(<RuntimeConnection {...props} canStart={false} onChanged={changed}/>);
    fireEvent.change(screen.getByRole('textbox', { name: '应用地址' }), { target: { value: 'http://127.0.0.1:5000' } });
    fireEvent.click(screen.getByRole('button', { name: '使用此地址' }));
    await waitFor(() => expect(confirm).toHaveBeenCalledWith('app', 'http://127.0.0.1:5000', 1));
    expect(changed).toHaveBeenCalledTimes(1);
    expect(runtime).not.toHaveBeenCalled();
    expect(start).not.toHaveBeenCalled();
    expect(screen.queryByRole('radio', { name: '由界鉴启动' })).not.toBeInTheDocument();
});

it('启动完成后展示实例，采用为检查目标仍由用户明确提交', async () => {
    let running = false;
    const operation = { project_id: 'app', operation_id: 'start', instance_id: 'instance', state: 'SUCCEEDED' };
    vi.spyOn(api, 'runtime').mockImplementation(async () => ({ ...idle, running, source_matches: running, operation: running ? operation : null }));
    vi.spyOn(api, 'runtimePreview').mockResolvedValue(preview);
    const start = vi.spyOn(api, 'runtimeStart').mockImplementation(async () => { running = true; return operation; });
    vi.spyOn(api, 'runtimeOperation').mockResolvedValue(operation);
    const confirm = vi.spyOn(api, 'confirmEndpoint').mockResolvedValue({} as never);
    render(<RuntimeConnection {...props}/>);
    fireEvent.click(screen.getByRole('radio', { name: '由界鉴启动' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '预览启动' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '预览启动' }));
    const consent = await screen.findByRole('checkbox', { name: '允许执行这份源码并使用上述端口' });
    expect(consent).not.toBeChecked();
    expect(screen.getByRole('button', { name: '启动应用' })).toBeDisabled();
    fireEvent.click(consent);
    fireEvent.click(screen.getByRole('button', { name: '启动应用' }));
    expect(await screen.findByRole('button', { name: '停止应用' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: '启动应用' })).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: '允许执行这份源码并使用上述端口' })).not.toBeInTheDocument();
    expect(start).toHaveBeenCalledTimes(1);
    expect(confirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('radio', { name: '连接已有应用' }));
    expect(screen.getByRole('button', { name: '管理运行实例' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '管理运行实例' }));
    fireEvent.click(screen.getByRole('button', { name: '使用此应用' }));
    await waitFor(() => expect(confirm).toHaveBeenCalledWith('app', 'http://127.0.0.1:3000', 1));
});

it('恢复未确认启动时查询原请求，不能因切换方式再次启动', async () => {
    sessionStorage.setItem('jiejian.studio.start-runtime:app', JSON.stringify({ preview, operation: 'pending-start' }));
    vi.spyOn(api, 'runtime').mockResolvedValue(idle);
    const read = vi.spyOn(api, 'runtimeOperation').mockResolvedValue({ project_id: 'app', operation_id: 'pending-start', instance_id: 'instance', state: 'RUNNING' });
    const start = vi.spyOn(api, 'runtimeStart');
    render(<RuntimeConnection {...props}/>);
    await waitFor(() => expect(read).toHaveBeenCalledWith('app', 'pending-start'));
    expect(screen.getByRole('radio', { name: '由界鉴启动' })).toBeChecked();
    expect(screen.getByRole('radio', { name: '连接已有应用' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '查询启动结果' }));
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    expect(start).not.toHaveBeenCalled();
});

it.each(['FAILED', 'CANCELLED'])('启动终态 %s 清除旧确认，不改变检查地址', async state => {
    sessionStorage.setItem('jiejian.studio.start-runtime:app', JSON.stringify({ preview, operation: 'pending-start' }));
    vi.spyOn(api, 'runtime').mockResolvedValue(idle);
    vi.spyOn(api, 'runtimeOperation').mockResolvedValue({ project_id: 'app', operation_id: 'pending-start', instance_id: 'instance', state });
    const confirm = vi.spyOn(api, 'confirmEndpoint');
    render(<RuntimeConnection {...props}/>);
    expect(await screen.findByText(state === 'FAILED' ? /本次启动未完成/ : '本次启动已取消。')).toBeVisible();
    expect(screen.queryByRole('button', { name: '启动应用' })).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: '允许执行这份源码并使用上述端口' })).not.toBeInTheDocument();
    expect(sessionStorage.getItem('jiejian.studio.start-runtime:app')).toBeNull();
    expect(confirm).not.toHaveBeenCalled();
});
