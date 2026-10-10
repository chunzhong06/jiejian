/* 界鉴便携版的 Win32 薄入口：按自身目录启动固定程序，持有进程树，重复启动只通知原窗口。 */
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define WM_STAGE (WM_APP + 1)
static HWND window, label;
static HANDLE output, log_file;
static int no_open;
static wchar_t error_text[256];

static LRESULT CALLBACK window_proc(HWND hwnd, UINT message, WPARAM w, LPARAM l) {
    if (message == WM_STAGE) {
        if (w == 5) { ShowWindow(hwnd, SW_HIDE); MessageBoxW(hwnd, error_text, L"界鉴界面暂未打开", MB_OK | MB_ICONWARNING); return 0; }
        if (w == 3) ShowWindow(hwnd, SW_HIDE);
        else SetWindowTextW(label, w == 1 ? L"正在核对包内程序…" : w == 2 ? L"正在启动界鉴服务…" : L"服务仍在启动，请稍候…");
        return 0;
    }
    if (message == WM_CLOSE) return 0; /* 迁移或启动期间不把关闭提示窗解释成强制结束数据库进程。 */
    return DefWindowProcW(hwnd, message, w, l);
}

static void consume_line(const char *line) {
    const char *error = "__JIEJIAN_RELEASE_ERROR__:";
    DWORD written;
    int stage = 0;
    if (strcmp(line, "__JIEJIAN_RELEASE_STATUS__:validate") == 0) stage = 1;
    else if (strcmp(line, "__JIEJIAN_RELEASE_STATUS__:serve") == 0) stage = 2;
    else if (strcmp(line, "__JIEJIAN_SERVE_STATUS__:ready-browser-opened") == 0) stage = 3;
    else if (strcmp(line, "__JIEJIAN_SERVE_STATUS__:still-starting") == 0) stage = 4;
    else if (strcmp(line, "__JIEJIAN_SERVE_STATUS__:ready-browser-open-failed") == 0) {
        wcscpy(error_text, L"服务已启动，但界面窗口未能打开。请双击界鉴.exe重新打开。");
        stage = 5;
    }
    else if (strcmp(line, "__JIEJIAN_GUI_STATUS__:opened") == 0 || strcmp(line, "__JIEJIAN_GUI_STATUS__:open-failed") == 0) { /* 仅记录窗口恢复的有限结果。 */ }
    else if (strncmp(line, error, strlen(error)) == 0)
        MultiByteToWideChar(CP_UTF8, 0, line + strlen(error), -1, error_text, 255);
    else return;
    /* 只保留有限的启动状态；不复制 CLI、访问日志或异常正文到启动日志。 */
    if (log_file != INVALID_HANDLE_VALUE) {
        WriteFile(log_file, line, (DWORD)strlen(line), &written, NULL);
        WriteFile(log_file, "\r\n", 2, &written, NULL);
    }
    if (stage && window) PostMessageW(window, WM_STAGE, (WPARAM)stage, 0);
}

static DWORD WINAPI read_output(void *unused) {
    char block[1024], line[4096]; DWORD count; size_t used = 0; int discard = 0;
    (void)unused;
    while (ReadFile(output, block, sizeof(block), &count, NULL) && count) {
        for (DWORD i = 0; i < count; ++i) {
            if (block[i] == '\n') {
                if (!discard) { if (used && line[used - 1] == '\r') --used; line[used] = 0; consume_line(line); }
                used = 0; discard = 0;
            } else if (used < sizeof(line) - 1) line[used++] = block[i];
            else discard = 1;
        }
    }
    return 0;
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command_line, int show) {
    wchar_t root[32768], lowered[32768], script[32768], shell[32768], command[65536], path[32768];
    wchar_t mutex_name[80], event_name[80];
    HANDLE mutex = NULL, reopen = NULL, job = NULL, pipe_write = NULL, reader = NULL, input = NULL;
    PROCESS_INFORMATION process = {0}; STARTUPINFOW startup = {0};
    SECURITY_ATTRIBUTES security = {sizeof(security), NULL, TRUE};
    DWORD result = 1, length, port = 8765; int argc;
    LPWSTR *argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    (void)previous; (void)command_line; (void)show;
    output = NULL; log_file = INVALID_HANDLE_VALUE;
    for (int i = 1; i < argc; ++i) {
        if (wcscmp(argv[i], L"--no-open") == 0) no_open = 1;
        else if (wcscmp(argv[i], L"--port") == 0 && i + 1 < argc) {
            wchar_t *end; unsigned long value = wcstoul(argv[++i], &end, 10);
            if (*end || value < 1 || value > 65535) goto invalid_arguments;
            port = (DWORD)value;
        } else goto invalid_arguments;
    }
    LocalFree(argv);
    length = GetModuleFileNameW(NULL, root, 32768);
    if (!length || length >= 32768) goto cleanup;
    wchar_t *last = wcsrchr(root, L'\\'); if (!last) goto cleanup; *last = 0;
    wcscpy(lowered, root); CharLowerBuffW(lowered, (DWORD)wcslen(lowered));
    uint64_t hash = UINT64_C(14695981039346656037);
    for (size_t i = 0; lowered[i]; ++i) { hash ^= (unsigned char)lowered[i]; hash *= UINT64_C(1099511628211); hash ^= (unsigned char)(lowered[i] >> 8); hash *= UINT64_C(1099511628211); }
    swprintf(mutex_name, 80, L"Local\\JieJian-Launcher-%016llx", (unsigned long long)hash);
    swprintf(event_name, 80, L"Local\\JieJian-Reopen-%016llx", (unsigned long long)hash);
    mutex = CreateMutexW(NULL, TRUE, mutex_name);
    if (!mutex) goto cleanup;
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        /* 首个入口创建事件的极短窗口内仅等待原入口，不启动第二套程序。 */
        for (int i = 0; i < 20 && !reopen; ++i) { reopen = OpenEventW(EVENT_MODIFY_STATE, FALSE, event_name); if (!reopen) Sleep(50); }
        if (reopen) { SetEvent(reopen); result = 0; }
        goto cleanup;
    }
    reopen = CreateEventW(NULL, FALSE, FALSE, event_name);
    if (!reopen) goto cleanup;
    swprintf(script, 32768, L"%ls\\app\\start.ps1", root);
    if (GetFileAttributesW(script) == INVALID_FILE_ATTRIBUTES) {
        wcscpy(error_text, L"缺少 app\\start.ps1。请先完整解压发布包，再运行界鉴.exe。"); goto cleanup;
    }
    swprintf(path, 32768, L"%ls\\var", root); if (!CreateDirectoryW(path, NULL) && GetLastError() != ERROR_ALREADY_EXISTS) goto cleanup;
    swprintf(path, 32768, L"%ls\\var\\logs", root); CreateDirectoryW(path, NULL);
    swprintf(path, 32768, L"%ls\\var\\logs\\launcher.log", root);
    log_file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (log_file == INVALID_HANDLE_VALUE) { wcscpy(error_text, L"发布目录无法写入。请把整个界鉴目录放到可写位置再启动。"); goto cleanup; }
    length = GetSystemDirectoryW(shell, 32768);
    if (!length || length + 60 >= 32768) goto cleanup;
    wcscat(shell, L"\\WindowsPowerShell\\v1.0\\powershell.exe");
    swprintf(command, 65536, L"\"%ls\" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"%ls\" -Port %lu -ReopenEvent \"%ls\" %ls", shell, script, port, event_name, no_open ? L"-NoOpen" : L"");
    if (!CreatePipe(&output, &pipe_write, &security, 0)) goto cleanup;
    SetHandleInformation(output, HANDLE_FLAG_INHERIT, 0);
    input = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, &security, OPEN_EXISTING, 0, NULL);
    job = CreateJobObjectW(NULL, NULL);
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits = {0};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!job || !SetInformationJobObject(job, JobObjectExtendedLimitInformation, &limits, sizeof(limits))) goto cleanup;
    startup.cb = sizeof(startup); startup.dwFlags = STARTF_USESTDHANDLES; startup.hStdInput = input; startup.hStdOutput = pipe_write; startup.hStdError = pipe_write;
    if (!CreateProcessW(shell, command, NULL, NULL, TRUE, CREATE_NO_WINDOW | CREATE_SUSPENDED, NULL, root, &startup, &process)) goto cleanup;
    if (!AssignProcessToJobObject(job, process.hProcess)) { TerminateProcess(process.hProcess, 1); goto cleanup; }
    if (!no_open) {
        WNDCLASSW type = {0}; type.lpfnWndProc = window_proc; type.hInstance = instance; type.lpszClassName = L"JieJianStartup"; type.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1); type.hCursor = LoadCursor(NULL, IDC_ARROW);
        RegisterClassW(&type);
        window = CreateWindowExW(WS_EX_TOOLWINDOW, type.lpszClassName, L"界鉴", WS_CAPTION | WS_OVERLAPPED, (GetSystemMetrics(SM_CXSCREEN) - 440) / 2, (GetSystemMetrics(SM_CYSCREEN) - 140) / 2, 440, 140, NULL, NULL, instance, NULL);
        label = CreateWindowW(L"STATIC", L"正在启动界鉴…", WS_CHILD | WS_VISIBLE | SS_CENTER, 20, 38, 400, 42, window, NULL, instance, NULL);
        SendMessageW(label, WM_SETFONT, (WPARAM)GetStockObject(DEFAULT_GUI_FONT), TRUE);
    }
    reader = CreateThread(NULL, 0, read_output, NULL, 0, NULL);
    if (!reader) { TerminateProcess(process.hProcess, 1); goto cleanup; }
    CloseHandle(pipe_write); pipe_write = NULL;
    ResumeThread(process.hThread);
    if (window) ShowWindow(window, SW_SHOWNORMAL);
    while (MsgWaitForMultipleObjects(1, &process.hProcess, FALSE, INFINITE, QS_ALLINPUT) != WAIT_OBJECT_0) {
        MSG message; while (PeekMessageW(&message, NULL, 0, 0, PM_REMOVE)) { TranslateMessage(&message); DispatchMessageW(&message); }
    }
    GetExitCodeProcess(process.hProcess, &result);
cleanup:
    if (pipe_write) CloseHandle(pipe_write);
    if (job) CloseHandle(job); /* 正常退出已沿原服务收口；异常退出回收本入口拥有的残留后代。 */
    if (reader) { WaitForSingleObject(reader, 5000); CloseHandle(reader); }
    if (output) CloseHandle(output);
    if (input && input != INVALID_HANDLE_VALUE) CloseHandle(input);
    if (process.hThread) CloseHandle(process.hThread);
    if (process.hProcess) CloseHandle(process.hProcess);
    if (window) DestroyWindow(window);
    if (log_file != INVALID_HANDLE_VALUE) { char code[64]; DWORD written; int n = snprintf(code, sizeof(code), "launcher_exit=%lu\r\n", result); WriteFile(log_file, code, n, &written, NULL); CloseHandle(log_file); }
    if (result && !no_open) MessageBoxW(NULL, error_text[0] ? error_text : L"界鉴未能启动。请确认发布包已完整解压且目录可写，查看 var\\logs\\launcher.log 和 README.txt。", L"界鉴启动未完成", MB_OK | MB_ICONERROR);
    if (reopen) CloseHandle(reopen);
    if (mutex) { ReleaseMutex(mutex); CloseHandle(mutex); }
    return (int)result;
invalid_arguments:
    LocalFree(argv);
    MessageBoxW(NULL, L"直接双击即可启动。命令行仅支持 --no-open 和 --port 端口号。", L"界鉴", MB_OK | MB_ICONINFORMATION);
    return 2;
}
