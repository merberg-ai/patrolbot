document.addEventListener('DOMContentLoaded', async () => {
  if (document.body.dataset.page !== 'system') return;
  try {
    const data = await window.patrolbotApi.getSystem();
    document.getElementById('system-ip').textContent = `IP: ${data.ip}`;
    document.getElementById('system-mode').textContent = `Mode: ${data.mode}`;
    document.getElementById('system-led').textContent = `LED state: ${data.led_state}`;

    const v = data.version || {};
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val || '--'; };

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
});
