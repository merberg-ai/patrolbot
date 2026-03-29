document.addEventListener('DOMContentLoaded', async () => {
  if (document.body.dataset.page !== 'system') return;
  try {
    const data = await window.patrolbotApi.getSystem();
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val || '--'; };
    set('system-ip', data.ip);
    set('system-mode', data.mode);
    set('system-led', data.led_state);
    set('system-wifi', data.network?.connected ? `${data.network.ssid || 'connected'} · ${data.network.ip || '--'}` : 'offline');
    set('system-camera', data.services?.camera_running ? 'running' : 'offline');
    set('system-vision-service', data.services?.vision_service ? 'loaded' : 'not initialized');

    const v = data.version || {};
    set('ver-string', v.version_string);
    set('ver-app', v.app_version);
    set('ver-branch', v.git_branch);
    set('ver-commit', v.git_commit);
    set('ver-tag', v.git_tag);
    set('ver-date', v.git_commit_date ? v.git_commit_date.substring(0, 16) : null);

    const dirtyEl = document.getElementById('ver-dirty');
    if (dirtyEl) {
      if (v.git_commit == null) {
        dirtyEl.textContent = 'no git repository';
        dirtyEl.style.color = 'var(--muted)';
      } else {
        dirtyEl.textContent = v.git_dirty ? 'modified (uncommitted changes)' : 'clean';
        dirtyEl.style.color = v.git_dirty ? '#ffcc55' : '#22dd88';
      }
    }

    const msgEl = document.getElementById('ver-message');
    if (msgEl && v.git_commit_message) {
      msgEl.textContent = `Last commit: ${v.git_commit_message}`;
      msgEl.style.display = '';
    }
  } catch (err) {
    console.warn('system info load failed:', err);
  }
});

async function loadLogs() {
  if (document.body.dataset.page !== 'system') return;
  const viewer = document.getElementById('system-log-viewer');
  const msg = document.getElementById('logs-message');
  const limit = Number(document.getElementById('log-line-limit')?.value || 250);
  try {
    const data = await window.patrolbotApi.getLogs(limit);
    if (viewer) viewer.textContent = (data.lines || []).join('\n');
    if (msg) msg.textContent = `Showing ${data.line_count || 0} lines from ${data.path}`;
  } catch (err) {
    if (msg) msg.textContent = 'Failed to load logs.';
  }
}

async function loadSnapshots() {
  const container = document.getElementById('snapshot-list');
  const msg = document.getElementById('snapshots-message');
  const preview = document.getElementById('snapshot-preview');
  if (!container) return;
  try {
    const data = await window.patrolbotApi.getSnapshots();
    container.innerHTML = '';
    const items = data.items || [];
    if (!items.length) {
      container.innerHTML = '<div class="muted">No snapshots saved yet.</div>';
      if (preview) preview.style.display = 'none';
      if (msg) msg.textContent = 'No snapshots found.';
      return;
    }
    items.forEach(item => {
      const wrap = document.createElement('div');
      wrap.className = 'card';
      wrap.style.padding = '10px';
      wrap.innerHTML = `<div style="display:flex; justify-content:space-between; gap:12px; align-items:flex-start;">
        <div>
          <strong>${item.label || item.name}</strong>
          <div class="muted">${item.timestamp}</div>
          <div class="muted">${item.name}</div>
        </div>
        <div style="display:flex; gap:8px;">
          <button data-preview="${item.url}">View</button>
          <button class="danger" data-delete="${item.name}">Delete</button>
        </div>
      </div>`;
      container.appendChild(wrap);
    });
    container.querySelectorAll('[data-preview]').forEach(btn => btn.addEventListener('click', () => {
      if (!preview) return;
      preview.src = `${btn.dataset.preview}?_ts=${Date.now()}`;
      preview.style.display = '';
    }));
    container.querySelectorAll('[data-delete]').forEach(btn => btn.addEventListener('click', async () => {
      await window.patrolbotApi.deleteSnapshot(btn.dataset.delete);
      loadSnapshots();
      refreshStatus().catch(()=>{});
    }));
    if (msg) msg.textContent = `Loaded ${items.length} snapshot${items.length === 1 ? '' : 's'}.`;
  } catch (err) {
    if (msg) msg.textContent = 'Failed to load snapshots.';
  }
}

let logAutoRefresh = true;
let logTimer = null;
function startLogAutoRefresh() {
  if (logTimer) clearInterval(logTimer);
  logTimer = setInterval(() => { if (logAutoRefresh) loadLogs(); }, 3000);
}

document.addEventListener('DOMContentLoaded', () => {
  if (document.body.dataset.page !== 'system') return;
  const actionMsg = document.getElementById('system-action-message');
  const postAction = async (url, label) => {
    try {
      if (actionMsg) actionMsg.textContent = `${label} requested…`;
      await fetch(url, { method: 'POST' });
      if (actionMsg) actionMsg.textContent = `${label} requested.`;
    } catch (err) {
      if (actionMsg) actionMsg.textContent = `${label} failed.`;
    }
  };
  const rebootBtn = document.getElementById('reboot-btn');
  const shutdownBtn = document.getElementById('shutdown-btn');
  if (rebootBtn) rebootBtn.addEventListener('click', () => postAction('/api/system/reboot', 'Reboot'));
  if (shutdownBtn) shutdownBtn.addEventListener('click', () => postAction('/api/system/shutdown', 'Shutdown'));

  const refreshBtn = document.getElementById('logs-refresh');
  const copyBtn = document.getElementById('logs-copy');
  const toggleBtn = document.getElementById('logs-toggle-auto');
  const limitSel = document.getElementById('log-line-limit');
  if (refreshBtn) refreshBtn.addEventListener('click', loadLogs);
  if (limitSel) limitSel.addEventListener('change', loadLogs);
  if (copyBtn) copyBtn.addEventListener('click', async () => {
    const viewer = document.getElementById('system-log-viewer');
    if (!viewer) return;
    await navigator.clipboard.writeText(viewer.textContent || '');
  });
  if (toggleBtn) toggleBtn.addEventListener('click', () => {
    logAutoRefresh = !logAutoRefresh;
    toggleBtn.textContent = logAutoRefresh ? 'Pause Auto Refresh' : 'Resume Auto Refresh';
  });

  const snapRefresh = document.getElementById('snapshots-refresh');
  const snapDeleteAll = document.getElementById('snapshots-delete-all');
  if (snapRefresh) snapRefresh.addEventListener('click', loadSnapshots);
  if (snapDeleteAll) snapDeleteAll.addEventListener('click', async () => {
    await window.patrolbotApi.deleteAllSnapshots();
    loadSnapshots();
    refreshStatus().catch(()=>{});
  });

  loadLogs();
  loadSnapshots();
  startLogAutoRefresh();
});
