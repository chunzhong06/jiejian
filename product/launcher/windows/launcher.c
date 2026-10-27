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
#include "startup-brand.h"

#define WM_STAGE (WM_APP + 1)
#define ID_REOPEN 101
static HWND window, reopen_button;
static HANDLE output, log_file;
static HANDLE reopen_event;
static int no_open;
static wchar_t error_text[256];
static int current_stage, ready, gui_failed, animate = 1;
static ULONGLONG started_at, ready_at;
static HFONT body_font, title_font, art_font, button_font;

static void paint_text(HDC dc, const wchar_t *text, int x, int y, int width, COLORREF color, HFONT font, UINT align) {
    RECT rect = {x, y, x + width, y + 32};
    SelectObject(dc, font); SetTextColor(dc, color);
    DrawTextW(dc, text, -1, &rect, DT_SINGLELINE | DT_VCENTER | DT_NOPREFIX | align);
}

static void paint_panel(HWND hwnd) {
    PAINTSTRUCT paint; RECT client;
    HDC target = BeginPaint(hwnd, &paint);
    GetClientRect(hwnd, &client);
    if (client.right <= 0 || client.bottom <= 0) { EndPaint(hwnd, &paint); return; }
    /* 双缓冲只重绘展示；同一单调时钟计时，界面动画不延迟真实启动。 */
    HDC dc = CreateCompatibleDC(target);
    HBITMAP bitmap = CreateCompatibleBitmap(target, client.right, client.bottom);
    HGDIOBJ old_bitmap = SelectObject(dc, bitmap);
    SetMapMode(dc, MM_ANISOTROPIC); SetWindowExtEx(dc, 920, 640, NULL);
    SetViewportExtEx(dc, client.right, client.bottom, NULL);
    RECT canvas = {0, 0, 920, 640};
    HBRUSH background = CreateSolidBrush(RGB(31, 37, 53));
    FillRect(dc, &canvas, background); DeleteObject(background);
    SetBkMode(dc, TRANSPARENT);
    int art_width = 0; SIZE extent;
    SelectObject(dc, art_font);
    for (int i = 0; i < 6; ++i) {
        GetTextExtentPoint32W(dc, brand_art[i], (int)wcslen(brand_art[i]), &extent);
        if (extent.cx > art_width) art_width = extent.cx;
    }
    for (int i = 0; i < 6; ++i) {
        SetTextColor(dc, brand_colors[i]);
        TextOutW(dc, (920 - art_width) / 2, 46 + i * 22, brand_art[i], (int)wcslen(brand_art[i]));
    }
    wchar_t brand[80], elapsed[80];
    swprintf(brand, 80, L"界鉴  JIEJIAN  %ls", brand_version);
    paint_text(dc, brand, 64, 206, 590, RGB(186,196,249), title_font, DT_LEFT);
    paint_text(dc, ready ? (gui_failed ? L"界面待打开" : L"已就绪") : L"正在启动", 664, 206, 192,
               gui_failed ? RGB(237,163,169) : RGB(186,196,249), body_font, DT_RIGHT);
    paint_text(dc, L"让权限要求与实际行为对应起来", 64, 244, 792, RGB(166,173,192), body_font, DT_LEFT);
    HPEN line = CreatePen(PS_SOLID, 1, RGB(59,69,91));
    HGDIOBJ old_pen = SelectObject(dc, line);
    MoveToEx(dc, 64, 300, NULL); LineTo(dc, 856, 300);
    const wchar_t *labels[] = {L"核对发行组件", L"核对运行环境", L"启动服务与界面"};
    ULONGLONG now = GetTickCount64();
    for (int i = 0; i < 3; ++i) {
        int done = ready ? !(gui_failed && i == 2) : i < current_stage;
        int active = !ready && i == current_stage;
        COLORREF color = active ? RGB(186,196,249) : RGB(166,173,192);
        const wchar_t *mark = done ? L"✓" : active ? L"›" : L"·";
        const wchar_t *state = done ? L"已就绪" : active ? L"处理中" : gui_failed && i == 2 ? L"请重试打开" : L"等待";
        paint_text(dc, mark, 64, 334 + i * 52, 32, color, body_font, DT_CENTER);
        paint_text(dc, labels[i], 110, 334 + i * 52, 530, color, body_font, DT_LEFT);
        paint_text(dc, state, 674, 334 + i * 52, 182, color, body_font, DT_RIGHT);
        if (active && animate) {
            const wchar_t *dots[] = {L"·", L"··", L"···", L"··"};
            paint_text(dc, dots[(now / 350) % 4], 630, 334 + i * 52, 44, color, body_font, DT_LEFT);
        }
    }
    MoveToEx(dc, 64, 512, NULL); LineTo(dc, 856, 512);
    swprintf(elapsed, 80, ready ? L"启动用时 %.1f 秒" : L"启动已用 %.1f 秒", (double)((ready ? ready_at : now) - started_at) / 1000.0);
    paint_text(dc, elapsed, 64, 538, 390, RGB(186,196,249), body_font, DT_LEFT);
    paint_text(dc, ready ? L"关闭面板可收起；退出服务请使用网页入口。" : L"准备完成后自动打开界面，关闭面板不会中断启动。",
               64, 585, 792, RGB(166,173,192), body_font, DT_LEFT);
    SelectObject(dc, old_pen); DeleteObject(line);
    SetMapMode(dc, MM_TEXT);
    BitBlt(target, 0, 0, client.right, client.bottom, dc, 0, 0, SRCCOPY);
    SelectObject(dc, old_bitmap); DeleteObject(bitmap); DeleteDC(dc);
    EndPaint(hwnd, &paint);
}

static LRESULT CALLBACK window_proc(HWND hwnd, UINT message, WPARAM w, LPARAM l) {
    if (message == WM_STAGE) {
        if (w == 1) current_stage = 0;
        if (w == 6) current_stage = 1;
        if (w == 2 || w == 4) current_stage = 2;
        if (w == 3 || w == 5) {
            if (!ready) ready_at = GetTickCount64();
            ready = 1; gui_failed = w == 5;
            ShowWindow(reopen_button, SW_SHOW);
            SetWindowTextW(hwnd, gui_failed ? L"界鉴 · 界面待打开" : L"界鉴 · 已就绪");
        }
        InvalidateRect(hwnd, NULL, FALSE);
        return 0;
    }
    if (message == WM_PAINT) { paint_panel(hwnd); return 0; }
    if (message == WM_ERASEBKGND) return 1;
    if (message == WM_TIMER) { if (!ready) InvalidateRect(hwnd, NULL, FALSE); return 0; }
    if (message == WM_SIZE && reopen_button) {
        MoveWindow(reopen_button, LOWORD(l) * 636 / 920, HIWORD(l) * 532 / 640, LOWORD(l) * 220 / 920, HIWORD(l) * 48 / 640, TRUE);
        return 0;
    }
    if (message == WM_COMMAND && LOWORD(w) == ID_REOPEN) {
        if (ready && reopen_event) SetEvent(reopen_event);
        return 0;
    }
    if (message == WM_DRAWITEM && w == ID_REOPEN) {
        DRAWITEMSTRUCT *item = (DRAWITEMSTRUCT *)l;
        int saved_dc = SaveDC(item->hDC);
        HBRUSH background = CreateSolidBrush(RGB(31,37,53));
        FillRect(item->hDC, &item->rcItem, background); DeleteObject(background);
        COLORREF fill = item->itemState & ODS_SELECTED ? RGB(143,157,224) : RGB(186,196,249);
        HBRUSH brush = CreateSolidBrush(fill); HPEN pen = CreatePen(PS_SOLID, 1, fill);
        HGDIOBJ old_brush = SelectObject(item->hDC, brush), old_pen = SelectObject(item->hDC, pen);
        int corner = (item->rcItem.bottom - item->rcItem.top) * 3 / 4;
        RoundRect(item->hDC, item->rcItem.left, item->rcItem.top, item->rcItem.right, item->rcItem.bottom, corner, corner);
        SetBkMode(item->hDC, TRANSPARENT); SetTextColor(item->hDC, RGB(31,37,53));
        SelectObject(item->hDC, button_font);
        DrawTextW(item->hDC, L"重新打开界面", -1, &item->rcItem, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        if (item->itemState & ODS_FOCUS) { RECT focus = item->rcItem; InflateRect(&focus, -5, -5); DrawFocusRect(item->hDC, &focus); }
        SelectObject(item->hDC, old_brush); SelectObject(item->hDC, old_pen); DeleteObject(brush); DeleteObject(pen);
        RestoreDC(item->hDC, saved_dc);
        return TRUE;
    }
    if (message == WM_CLOSE) { ShowWindow(hwnd, SW_HIDE); return 0; } /* 收起展示不等于关闭服务或中断迁移。 */
    return DefWindowProcW(hwnd, message, w, l);
}

static void consume_line(const char *line) {
    const char *error = "__JIEJIAN_RELEASE_ERROR__:";
    DWORD written;
    int stage = 0;
    if (strcmp(line, "__JIEJIAN_RELEASE_STATUS__:validate") == 0) stage = 1;
    else if (strcmp(line, "__JIEJIAN_RELEASE_STATUS__:identity") == 0) stage = 6;
    else if (strcmp(line, "__JIEJIAN_RELEASE_STATUS__:serve") == 0) stage = 2;
    else if (strcmp(line, "__JIEJIAN_SERVE_STATUS__:ready-browser-opened") == 0) stage = 3;
    else if (strcmp(line, "__JIEJIAN_SERVE_STATUS__:still-starting") == 0) stage = 4;
    else if (strcmp(line, "__JIEJIAN_SERVE_STATUS__:ready-browser-open-failed") == 0) {
        wcscpy(error_text, L"服务已启动，但界面窗口未能打开。请双击界鉴.exe重新打开。");
        stage = 5;
    }
    else if (strcmp(line, "__JIEJIAN_GUI_STATUS__:opened") == 0) stage = 3;
    else if (strcmp(line, "__JIEJIAN_GUI_STATUS__:open-failed") == 0) stage = 5;
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
    started_at = GetTickCount64();
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
    reopen_event = reopen;
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
        SetProcessDPIAware();
        BOOL client_animation = TRUE;
        if (SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, &client_animation, 0)) animate = client_animation;
        body_font = CreateFontW(-18, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH, L"Microsoft YaHei UI");
        title_font = CreateFontW(-22, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH, L"Microsoft YaHei UI");
        art_font = CreateFontW(-20, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, FIXED_PITCH, L"Consolas");
        HDC screen = GetDC(NULL); int dpi = GetDeviceCaps(screen, LOGPIXELSY); ReleaseDC(NULL, screen);
        RECT work; SystemParametersInfoW(SPI_GETWORKAREA, 0, &work, 0);
        int width = MulDiv(920, dpi, 96), height = MulDiv(640, dpi, 96);
        if (width > work.right - work.left - 60) width = work.right - work.left - 60;
        if (height > work.bottom - work.top - 80) { height = work.bottom - work.top - 80; width = height * 920 / 640; }
        button_font = CreateFontW(-MulDiv(18, width, 920), 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH, L"Microsoft YaHei UI");
        WNDCLASSW type = {0}; type.lpfnWndProc = window_proc; type.hInstance = instance; type.lpszClassName = L"JieJianStartup"; type.hCursor = LoadCursor(NULL, IDC_ARROW);
        type.hIcon = LoadIconW(instance, MAKEINTRESOURCEW(1));
        RegisterClassW(&type);
        DWORD style = WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX | WS_CLIPCHILDREN;
        RECT outer = {0, 0, width, height}; AdjustWindowRectEx(&outer, style, FALSE, 0);
        width = outer.right - outer.left; height = outer.bottom - outer.top;
        window = CreateWindowExW(0, type.lpszClassName, L"界鉴 · 启动状态", style, work.left + (work.right - work.left - width) / 2, work.top + (work.bottom - work.top - height) / 2, width, height, NULL, NULL, instance, NULL);
        if (!window) { TerminateProcess(process.hProcess, 1); goto cleanup; }
        reopen_button = CreateWindowW(L"BUTTON", L"重新打开界面", WS_CHILD | WS_TABSTOP | BS_OWNERDRAW, 0, 0, 0, 0, window, (HMENU)(INT_PTR)ID_REOPEN, instance, NULL);
        RECT client; GetClientRect(window, &client);
        SendMessageW(window, WM_SIZE, 0, MAKELPARAM(client.right, client.bottom));
        SetTimer(window, 1, 250, NULL);
    }
    reader = CreateThread(NULL, 0, read_output, NULL, 0, NULL);
    if (!reader) { TerminateProcess(process.hProcess, 1); goto cleanup; }
    CloseHandle(pipe_write); pipe_write = NULL;
    ResumeThread(process.hThread);
    if (window) ShowWindow(window, SW_SHOWNORMAL);
    while (MsgWaitForMultipleObjects(1, &process.hProcess, FALSE, INFINITE, QS_ALLINPUT) != WAIT_OBJECT_0) {
        MSG message; while (PeekMessageW(&message, NULL, 0, 0, PM_REMOVE)) { if (!window || !IsDialogMessageW(window, &message)) { TranslateMessage(&message); DispatchMessageW(&message); } }
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
    if (body_font) DeleteObject(body_font);
    if (title_font) DeleteObject(title_font);
    if (art_font) DeleteObject(art_font);
    if (button_font) DeleteObject(button_font);
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
