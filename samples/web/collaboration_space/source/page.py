# 协作空间 Sample 的无构建 Web 产品页。
# 页面只呈现项目协作与资料导出业务，不展示观察来源、测试模式或界鉴结论。

from __future__ import annotations


APPLICATION_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>协作空间 · 校园数字展馆</title>
  <style>
    :root {
      color-scheme: light;
      --paper: #f7f8fa;
      --surface: #ffffff;
      --surface-soft: #f1f4f7;
      --ink: #17202a;
      --muted: #66717e;
      --line: #dce2e8;
      --brand: #155e75;
      --brand-dark: #0f4758;
      --brand-soft: #e8f4f6;
      --success: #2d6a4f;
      --warning: #955f13;
      --danger: #a33a3a;
      --shadow: 0 18px 48px rgba(31, 45, 61, 0.08);
      font-family: Inter, "Segoe UI", "Microsoft YaHei UI", sans-serif;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        radial-gradient(circle at 8% 0%, rgba(21, 94, 117, 0.09), transparent 29rem),
        var(--paper);
    }
    button { font: inherit; }
    button:focus-visible { outline: 3px solid rgba(21, 94, 117, 0.28); outline-offset: 2px; }
    [hidden] { display: none !important; }

    .shell { width: min(1120px, calc(100% - 40px)); margin: 0 auto; }
    .topbar {
      min-height: 68px;
      border-bottom: 1px solid rgba(220, 226, 232, 0.85);
      background: rgba(255, 255, 255, 0.9);
      backdrop-filter: blur(14px);
    }
    .topbar .shell { min-height: 68px; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-mark {
      width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center;
      color: white; background: var(--brand); font-weight: 760; letter-spacing: -0.04em;
    }
    .brand-copy strong { display: block; font-size: 15px; }
    .brand-copy span { display: block; margin-top: 2px; color: var(--muted); font-size: 12px; }
    .session-tools { display: flex; align-items: center; gap: 10px; }
    .session-label { color: var(--muted); font-size: 13px; }

    main { padding: 48px 0 72px; }
    .eyebrow { margin: 0 0 12px; color: var(--brand); font-size: 13px; font-weight: 720; letter-spacing: 0.08em; }
    h1, h2, h3, p { margin-top: 0; }
    h1 { margin-bottom: 14px; font-size: clamp(32px, 5vw, 52px); line-height: 1.08; letter-spacing: -0.045em; }
    h2 { margin-bottom: 10px; font-size: 24px; letter-spacing: -0.025em; }
    h3 { margin-bottom: 8px; font-size: 16px; }
    .lead { max-width: 680px; margin-bottom: 0; color: var(--muted); font-size: 16px; line-height: 1.75; }

    .login-layout { display: grid; grid-template-columns: minmax(0, 1.06fr) minmax(360px, 0.94fr); gap: 42px; align-items: center; }
    .identity-panel { padding: 26px; border: 1px solid var(--line); border-radius: 20px; background: var(--surface); box-shadow: var(--shadow); }
    .identity-panel > p { color: var(--muted); line-height: 1.6; }
    .identity-list { display: grid; gap: 10px; margin-top: 18px; }
    .identity-card {
      width: 100%; display: grid; grid-template-columns: 44px 1fr auto; gap: 13px; align-items: center;
      padding: 14px; text-align: left; color: inherit; border: 1px solid var(--line); border-radius: 13px;
      background: var(--surface); cursor: pointer; transition: border-color 150ms ease, transform 150ms ease, background 150ms ease;
    }
    .identity-card:hover { transform: translateY(-1px); border-color: #9fb8c2; background: #fbfdfd; }
    .avatar { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center; background: var(--surface-soft); color: var(--brand); font-weight: 760; }
    .identity-name { display: block; font-weight: 700; }
    .identity-description { display: block; margin-top: 3px; color: var(--muted); font-size: 12px; }
    .identity-arrow { color: var(--muted); font-size: 19px; }

    .workspace-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; margin-bottom: 26px; }
    .workspace-head h1 { font-size: clamp(30px, 4vw, 44px); }
    .catalog-card { display: grid; grid-template-columns: 64px minmax(0, 1fr) auto; gap: 18px; align-items: center; margin-top: 26px; }
    .catalog-icon { width: 64px; height: 64px; display: grid; place-items: center; border-radius: 16px; color: var(--brand); background: var(--brand-soft); font-size: 24px; font-weight: 760; }
    .catalog-copy h2 { margin-bottom: 6px; }
    .catalog-copy p { margin-bottom: 0; color: var(--muted); line-height: 1.6; }
    .project-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
    .role-chip, .status-chip {
      display: inline-flex; align-items: center; min-height: 28px; padding: 5px 10px;
      border-radius: 999px; background: var(--brand-soft); color: var(--brand-dark); font-size: 12px; font-weight: 700;
    }
    .status-chip[data-tone="success"] { color: var(--success); background: #eaf5ef; }
    .status-chip[data-tone="warning"] { color: var(--warning); background: #fff5df; }
    .status-chip[data-tone="neutral"] { color: var(--muted); background: var(--surface-soft); }
    .status-chip[data-tone="danger"] { color: var(--danger); background: #faecec; }

    .grid { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(290px, 0.75fr); gap: 20px; }
    .stack { display: grid; gap: 20px; }
    .card { padding: 24px; border: 1px solid var(--line); border-radius: 18px; background: var(--surface); box-shadow: 0 8px 28px rgba(31, 45, 61, 0.045); }
    .card-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
    .card-kicker { margin-bottom: 6px; color: var(--muted); font-size: 12px; }
    .project-description { margin-bottom: 22px; color: var(--muted); line-height: 1.7; }
    .metadata { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
    .metadata-item { padding: 14px; border-radius: 12px; background: var(--surface-soft); }
    .metadata-item span { display: block; color: var(--muted); font-size: 12px; }
    .metadata-item strong { display: block; margin-top: 5px; font-size: 14px; }
    .member-list, .material-list { display: grid; gap: 10px; margin-top: 16px; }
    .member, .material { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 0; border-top: 1px solid var(--line); }
    .member:first-child, .material:first-child { border-top: 0; }
    .member small, .material small { color: var(--muted); }

    .export-card { color: #f8fbfc; border-color: transparent; background: linear-gradient(145deg, #164e63, #0f3342); }
    .export-card .card-kicker, .export-card p { color: rgba(248, 251, 252, 0.72); }
    .export-card h2 { max-width: 260px; }
    .export-state { margin: 22px 0; padding: 14px; border: 1px solid rgba(255, 255, 255, 0.16); border-radius: 12px; background: rgba(255, 255, 255, 0.08); }
    .export-state span { display: block; color: rgba(248, 251, 252, 0.67); font-size: 12px; }
    .export-state strong { display: block; margin-top: 5px; }
    .notice { margin-top: 14px; min-height: 21px; color: rgba(248, 251, 252, 0.82); font-size: 13px; line-height: 1.55; }
    .notice[data-tone="danger"] { color: #ffd8d8; }
    .notice[data-tone="success"] { color: #c7f2d8; }

    .button { border: 0; border-radius: 10px; padding: 10px 15px; color: white; background: var(--brand); font-weight: 700; cursor: pointer; }
    .button:hover { background: var(--brand-dark); }
    .button:disabled { opacity: 0.55; cursor: wait; }
    .button-secondary { color: var(--ink); border: 1px solid var(--line); background: var(--surface); }
    .button-secondary:hover { background: var(--surface-soft); }
    .button-light { width: 100%; color: var(--brand-dark); background: white; }
    .button-light:hover { background: #eaf4f6; }

    .revoke-dialog { width: min(100% - 32px, 480px); padding: 0; border: 0; border-radius: 18px; color: var(--ink); background: var(--surface); box-shadow: 0 22px 70px rgba(15, 51, 66, 0.28); }
    .revoke-dialog::backdrop { background: rgba(15, 35, 45, 0.48); }
    .revoke-dialog-body { padding: 26px; }
    .revoke-dialog-body h2 { margin-bottom: 10px; }
    .revoke-dialog-body p { color: var(--muted); line-height: 1.7; }
    .revoke-dialog-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 24px; }

    .empty-state { padding: 52px 24px; text-align: center; }
    .empty-state p { max-width: 520px; margin: 8px auto 22px; color: var(--muted); line-height: 1.65; }
    .error-banner { margin-bottom: 20px; padding: 14px 16px; border: 1px solid #efcaca; border-radius: 12px; color: #7d2b2b; background: #fff5f5; }
    .footer-note { margin-top: 28px; color: var(--muted); font-size: 12px; text-align: center; }

    @media (max-width: 820px) {
      .login-layout, .grid { grid-template-columns: 1fr; }
      .login-layout { gap: 28px; }
      .workspace-head { align-items: flex-start; flex-direction: column; }
      .catalog-card { grid-template-columns: 52px 1fr; }
      .catalog-icon { width: 52px; height: 52px; }
      .catalog-card .button { grid-column: 1 / -1; width: 100%; }
      .metadata { grid-template-columns: 1fr; }
    }
    @media (max-width: 520px) {
      .shell { width: min(100% - 24px, 1120px); }
      main { padding-top: 30px; }
      .topbar .shell { align-items: flex-start; padding-top: 14px; padding-bottom: 14px; }
      .session-tools { align-items: flex-end; flex-direction: column; }
      .session-label { display: none; }
      .identity-panel, .card { padding: 19px; }
      .identity-card { grid-template-columns: 40px 1fr auto; }
      .avatar { width: 40px; height: 40px; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="shell">
      <div class="brand" aria-label="协作空间">
        <div class="brand-mark">协</div>
        <div class="brand-copy"><strong>协作空间</strong><span>项目资料管理</span></div>
      </div>
      <div class="session-tools" id="session-tools" hidden>
        <span class="session-label" id="session-label"></span>
        <button class="button button-secondary" id="logout-button" type="button">切换身份</button>
      </div>
    </div>
  </header>

  <main class="shell">
    <section id="login-view" class="login-layout" hidden>
      <div>
        <p class="eyebrow">LOCAL COLLABORATION WORKSPACE</p>
        <h1>让项目资料始终清楚、完整、可交付。</h1>
        <p class="lead">这里是“校园数字展馆”的协作空间。选择一个演示身份进入，查看日常协作资料和完整项目交付包导出流程。</p>
      </div>
      <div class="identity-panel">
        <h2>选择演示身份</h2>
        <p>每个身份都会建立独立会话，并按项目中的真实成员关系访问资料。</p>
        <div class="identity-list">
          <button class="identity-card" type="button" data-account="alice">
            <span class="avatar">A</span><span><span class="identity-name">Alice</span><span class="identity-description">项目负责人 · 管理并导出项目资料</span></span><span class="identity-arrow">→</span>
          </button>
          <button class="identity-card" type="button" data-account="bob">
            <span class="avatar">B</span><span><span class="identity-name">Bob</span><span class="identity-description">普通成员 · 查看项目协作内容</span></span><span class="identity-arrow">→</span>
          </button>
        </div>
      </div>
    </section>

    <section id="workspace-view" hidden>
      <div id="catalog-view">
        <div class="workspace-head">
          <div><p class="eyebrow">项目目录</p><h1>我的协作项目</h1><p class="lead">选择一个项目，查看成员、资料和交付进度。</p></div>
          <span class="role-chip" id="role-chip"></span>
        </div>
        <article class="card catalog-card">
          <div class="catalog-icon">展</div>
          <div class="catalog-copy"><p class="card-kicker">CAMPUS EXHIBITION</p><h2>校园数字展馆</h2><p>校园历史、科研成果与师生记忆数字展馆</p></div>
          <button class="button" id="open-project-button" type="button">进入项目</button>
        </article>
        <p class="footer-note">共 1 个项目 · 本地演示应用</p>
      </div>
      <div id="project-view" hidden>
        <div class="project-toolbar"><button class="button button-secondary" id="back-button" type="button">← 返回项目目录</button><span class="role-chip" id="project-role-chip"></span></div>
        <div class="workspace-head">
          <div><p class="eyebrow">项目工作台</p><h1>校园数字展馆</h1><p class="lead">集中整理展馆说明、展陈设计、预算与评审记录，形成完整项目交付包。</p></div>
        </div>
        <div class="error-banner" id="error-banner" hidden></div>
        <div id="member-workspace" class="grid" hidden>
          <div class="stack">
            <article class="card">
              <div class="card-header"><div><p class="card-kicker">PROJECT OVERVIEW</p><h2>校园数字展馆</h2></div><span class="status-chip" id="project-status" data-tone="neutral">尚未导出</span></div>
              <p class="project-description">围绕校园历史、科研成果与师生记忆建设数字展馆，当前资料已进入集中整理阶段。</p>
              <div class="metadata">
                <div class="metadata-item"><span>项目编号</span><strong>campus-digital-museum</strong></div>
                <div class="metadata-item"><span>项目负责人</span><strong>Alice</strong></div>
                <div class="metadata-item"><span>协作状态</span><strong>资料整理中</strong></div>
              </div>
            </article>
            <article class="card"><p class="card-kicker">PROJECT MEMBERS</p><h2>项目成员</h2><div class="member-list" id="member-list"></div></article>
            <article class="card"><p class="card-kicker">MATERIALS</p><h2>项目资料</h2><div class="material-list" id="material-list"></div></article>
          </div>
          <aside class="card export-card">
            <p class="card-kicker">DELIVERY CENTER</p><h2>导出完整项目交付包</h2>
            <p>汇总项目申报书、完整预算、成员信息、设计源文件和评审记录，生成一个 ZIP 交付包。</p>
            <div class="export-state"><span>当前导出状态</span><strong id="export-state">尚未创建</strong></div>
            <button class="button button-light" id="export-button" type="button">生成完整交付包</button>
            <button class="button button-secondary" id="revoke-export-button" type="button" hidden>撤销本次导出</button>
            <div class="notice" id="export-notice" role="status" aria-live="polite"></div>
          </aside>
        </div>
        <p class="footer-note">本地演示应用 · 所有业务数据仅保存在当前运行目录</p>
      </div>
    </section>
  </main>

  <dialog class="revoke-dialog" id="revoke-dialog" aria-labelledby="revoke-dialog-title" aria-describedby="revoke-dialog-description">
    <div class="revoke-dialog-body">
      <h2 id="revoke-dialog-title">撤销当前资料包？</h2>
      <p id="revoke-dialog-description">撤销后，这个资料包将不再作为当前交付物使用。本次导出的历史记录会继续保留，你可以之后重新生成新的资料包。</p>
      <div class="revoke-dialog-actions">
        <button class="button button-secondary" id="cancel-revoke-button" type="button">取消</button>
        <button class="button" id="confirm-revoke-button" type="button">确认撤销</button>
      </div>
    </div>
  </dialog>

  <script>
    (function () {
      'use strict';
      var projectId = 'campus-digital-museum';
      var session = null;
      var loginView = document.getElementById('login-view');
      var workspaceView = document.getElementById('workspace-view');
      var catalogView = document.getElementById('catalog-view');
      var projectView = document.getElementById('project-view');
      var sessionTools = document.getElementById('session-tools');
      var errorBanner = document.getElementById('error-banner');
      var memberWorkspace = document.getElementById('member-workspace');
      var visitorWorkspace = document.getElementById('visitor-workspace');
      var exportButton = document.getElementById('export-button');
      var revokeExportButton = document.getElementById('revoke-export-button');
      var revokeDialog = document.getElementById('revoke-dialog');
      var confirmRevokeButton = document.getElementById('confirm-revoke-button');
      var exportNotice = document.getElementById('export-notice');
      var exportMarker = null;

      function show(element, visible) { element.hidden = !visible; }
      function setError(message) { errorBanner.textContent = message || ''; show(errorBanner, Boolean(message)); }
      function messageFor(code) {
        var messages = {
          PROJECT_MEMBER_REQUIRED: '当前身份尚未加入该项目，无法访问项目资料。',
          EXPORT_PERMISSION_REQUIRED: '当前账号没有导出完整项目交付包的权限。',
          EXPORT_NOT_READY_FOR_REVOKE: '资料包仍在生成，完成后才能撤销。',
          LOGIN_FAILED: '身份会话建立失败，请重新选择。',
          SESSION_REQUIRED: '会话已结束，请重新选择身份。'
        };
        return messages[code] || '操作暂时无法完成，请稍后重试。';
      }

      async function request(path, options) {
        var response = await fetch(path, Object.assign({ cache: 'no-store' }, options || {}));
        var data = null;
        try { data = await response.json(); } catch (_error) { data = {}; }
        return { ok: response.ok, status: response.status, data: data || {} };
      }

      function renderLogin() {
        session = null;
        show(loginView, true); show(workspaceView, false); show(sessionTools, false);
      }

      function renderSession() {
        show(loginView, false); show(workspaceView, true); show(sessionTools, true);
        document.getElementById('session-label').textContent = session.account.toUpperCase() + ' · ' + session.role;
        document.getElementById('role-chip').textContent = session.role;
        document.getElementById('project-role-chip').textContent = session.role;
      }

      function renderMembers(members) {
        var labels = { alice: 'Alice', bob: 'Bob' };
        var roles = { PROJECT_OWNER: '项目负责人', MEMBER: '普通成员' };
        var root = document.getElementById('member-list');
        root.replaceChildren();
        members.forEach(function (member) {
          var row = document.createElement('div'); row.className = 'member';
          var name = document.createElement('strong'); name.textContent = labels[member.user_id] || member.user_id;
          var role = document.createElement('small'); role.textContent = roles[member.role] || member.role;
          row.append(name, role); root.append(row);
        });
      }

      function renderMaterials(materials) {
        var kinds = { PROJECT_NOTE: '项目说明', DESIGN_PLACEHOLDER: '展陈设计', BUDGET_SUMMARY: '预算摘要' };
        var root = document.getElementById('material-list'); root.replaceChildren();
        materials.forEach(function (material) {
          var row = document.createElement('div'); row.className = 'material';
          var name = document.createElement('strong'); name.textContent = material.name;
          var kind = document.createElement('small'); kind.textContent = kinds[material.kind] || material.kind;
          row.append(name, kind); root.append(row);
        });
      }

      function renderExportState(state) {
        var labels = { NOT_CREATED: '尚未创建', PROCESSING: '正在生成', READY: '资料包已就绪', FAILED: '生成失败', REVOKED: '已撤销' };
        var tones = { NOT_CREATED: 'neutral', PROCESSING: 'warning', READY: 'success', FAILED: 'danger', REVOKED: 'neutral' };
        document.getElementById('export-state').textContent = labels[state] || state;
        var status = document.getElementById('project-status');
        status.textContent = labels[state] || state; status.dataset.tone = tones[state] || 'neutral';
        exportButton.textContent = state === 'REVOKED' ? '重新生成交付包' : '生成完整交付包';
        show(exportButton, state !== 'READY' && state !== 'PROCESSING');
        show(revokeExportButton, state === 'READY' && Boolean(exportMarker));
      }

      async function loadProject() {
        show(catalogView, false); show(projectView, true);
        setError(''); exportNotice.textContent = '';
        var result = await request('/api/projects/' + projectId + '/collaboration');
        if (result.status === 403) {
          show(memberWorkspace, false); setError(messageFor(result.data.code)); return;
        }
        if (!result.ok) { show(memberWorkspace, false); setError(messageFor(result.data.code)); return; }
        show(memberWorkspace, true);
        var status = await request('/api/projects/' + projectId);
        if (!status.ok) { show(memberWorkspace, false); setError(messageFor(status.data.code)); return; }
        var activeExport = status.data.active_export;
        exportMarker = activeExport && typeof activeExport.request_marker === 'string' ? activeExport.request_marker : null;
        renderMembers(result.data.members || []); renderMaterials(result.data.materials || []); renderExportState(status.data.export_state);
      }

      async function loadCatalog() {
        var result = await request('/api/projects');
        if (!result.ok || !result.data.projects || result.data.projects.length !== 1) {
          window.alert(messageFor(result.data.code)); return;
        }
        show(catalogView, true); show(projectView, false);
      }

      async function beginSession(account) {
        document.querySelectorAll('[data-account]').forEach(function (button) { button.disabled = true; });
        try {
          var result = await request('/api/demo-session', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ account: account })
          });
          if (!result.ok) { throw new Error(messageFor(result.data.code)); }
          session = result.data; renderSession(); await loadCatalog();
        } catch (error) {
          window.alert(error.message || '身份会话建立失败。');
        } finally {
          document.querySelectorAll('[data-account]').forEach(function (button) { button.disabled = false; });
        }
      }

      async function createExport() {
        exportButton.disabled = true; exportNotice.dataset.tone = ''; exportNotice.textContent = '正在提交导出请求…';
        try {
          var result = await request('/api/projects/' + projectId + '/exports', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ resource_id: 'campus-digital-museum-package' })
          });
          if (!result.ok) { exportNotice.dataset.tone = 'danger'; exportNotice.textContent = messageFor(result.data.code); return; }
          exportMarker = result.data.request_marker;
          exportNotice.textContent = '请求已提交，正在生成资料包…'; renderExportState('PROCESSING');
          for (var attempt = 0; attempt < 40; attempt += 1) {
            await new Promise(function (resolve) { window.setTimeout(resolve, 125); });
            var status = await request(
              '/api/projects/' + projectId + '/exports/' + encodeURIComponent(result.data.request_marker)
              + '?resource_id=' + encodeURIComponent('campus-digital-museum-package')
            );
            if (status.ok && status.data.export && status.data.export.state === 'SUCCESS') {
              renderExportState('READY'); exportNotice.dataset.tone = 'success'; exportNotice.textContent = '完整项目交付包已生成。'; return;
            }
            if (status.ok && status.data.export && status.data.export.state === 'FAILED') {
              renderExportState('FAILED'); exportNotice.dataset.tone = 'danger'; exportNotice.textContent = '资料包生成失败，请重新尝试。'; return;
            }
          }
          exportNotice.textContent = '任务仍在处理中，可稍后刷新项目状态。';
        } catch (_error) {
          exportNotice.dataset.tone = 'danger'; exportNotice.textContent = '无法连接本地服务，请稍后重试。';
        } finally { exportButton.disabled = false; }
      }

      function openRevokeDialog() {
        if (!exportMarker) { return; }
        revokeDialog.showModal();
      }

      async function revokeExport() {
        if (!exportMarker) { return; }
        revokeExportButton.disabled = true; confirmRevokeButton.disabled = true;
        exportNotice.dataset.tone = ''; exportNotice.textContent = '正在撤销本次导出…';
        try {
          var result = await request('/api/projects/' + projectId + '/exports', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json', 'X-Jiejian-Case-ID': exportMarker },
            body: JSON.stringify({ resource_id: 'campus-digital-museum-package' })
          });
          if (!result.ok) { exportNotice.dataset.tone = 'danger'; exportNotice.textContent = messageFor(result.data.code); return; }
          revokeDialog.close(); exportMarker = null; renderExportState('REVOKED');
          exportNotice.dataset.tone = 'success'; exportNotice.textContent = '这次资料包已撤销，可以重新生成新的交付包。';
        } catch (_error) {
          exportNotice.dataset.tone = 'danger'; exportNotice.textContent = '无法连接本地服务，请稍后重试。';
        } finally { revokeExportButton.disabled = false; confirmRevokeButton.disabled = false; }
      }

      document.querySelectorAll('[data-account]').forEach(function (button) {
        button.addEventListener('click', function () { beginSession(button.dataset.account); });
      });
      document.getElementById('logout-button').addEventListener('click', async function () {
        await request('/api/session', { method: 'DELETE' }); renderLogin();
      });
      document.getElementById('open-project-button').addEventListener('click', loadProject);
      document.getElementById('back-button').addEventListener('click', loadCatalog);
      exportButton.addEventListener('click', createExport);
      revokeExportButton.addEventListener('click', openRevokeDialog);
      document.getElementById('cancel-revoke-button').addEventListener('click', function () { revokeDialog.close(); });
      confirmRevokeButton.addEventListener('click', revokeExport);

      request('/api/session').then(function (result) {
        if (result.ok) { session = result.data; renderSession(); loadCatalog(); } else { renderLogin(); }
      }).catch(renderLogin);
    }());
  </script>
</body>
</html>
"""
