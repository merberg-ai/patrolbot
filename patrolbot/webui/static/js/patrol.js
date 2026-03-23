function patrolLog(message){
  const consoleEl = document.getElementById('patrol-console');
  if(!consoleEl) return;
  const stamp = new Date().toLocaleTimeString();
  consoleEl.textContent = `[${stamp}] ${message}
` + consoleEl.textContent;
}

function applyPatrolConfig(cfg){
  const set = (id, val) => { const el = document.getElementById(id); if(el && val !== undefined && val !== null) el.value = val; };
  set('patrol-speed', cfg.speed);
  set('patrol-reverse-speed', cfg.reverse_speed);
  set('patrol-avoid-distance', cfg.avoidance_distance_cm);
  set('patrol-reverse-time', cfg.reverse_time_sec);
  set('patrol-turn-time', cfg.turn_time_sec);
  set('patrol-turn-mode', cfg.turn_mode);
  set('patrol-pan-min', cfg.scan_pan_min);
  set('patrol-pan-max', cfg.scan_pan_max);
  set('patrol-scan-step', cfg.scan_step);
  set('patrol-scan-tilt', cfg.scan_tilt_angle);
}

function patrolPayloadFromForm(){
  return {
    speed: parseInt(document.getElementById('patrol-speed').value || '35', 10),
    reverse_speed: parseInt(document.getElementById('patrol-reverse-speed').value || '28', 10),
    avoidance_distance_cm: parseInt(document.getElementById('patrol-avoid-distance').value || '30', 10),
    reverse_time_sec: parseFloat(document.getElementById('patrol-reverse-time').value || '0.8'),
    turn_time_sec: parseFloat(document.getElementById('patrol-turn-time').value || '0.9'),
    turn_mode: document.getElementById('patrol-turn-mode').value,
    scan_pan_min: parseInt(document.getElementById('patrol-pan-min').value || '45', 10),
    scan_pan_max: parseInt(document.getElementById('patrol-pan-max').value || '135', 10),
    scan_step: parseInt(document.getElementById('patrol-scan-step').value || '2', 10),
    scan_tilt_angle: parseInt(document.getElementById('patrol-scan-tilt').value || '90', 10),
  };
}

async function loadPatrolConfig(){
  if(document.body.dataset.page !== 'patrol') return;
  const msg = document.getElementById('patrol-message');
  try{
    const data = await window.patrolbotApi.getPatrolConfig();
    applyPatrolConfig(data.config || {});
    if(msg) msg.textContent = 'Patrol config loaded.';
  }catch(err){
    if(msg) msg.textContent = 'Failed to load patrol config.';
    patrolLog('Failed to load patrol config.');
  }
}

function renderPatrolState(state){
  if(!state) return;
  setText('patrol-enabled', state.enabled ? 'ON' : 'OFF');
  setText('patrol-drive-state', state.drive_state || '--');
  setText('patrol-distance', state.metrics && state.metrics.last_distance_cm != null ? `${state.metrics.last_distance_cm} cm` : '--');
  setText('patrol-obstacles', state.metrics && state.metrics.obstacle_count != null ? String(state.metrics.obstacle_count) : '0');
  setText('patrol-last-turn', state.metrics && state.metrics.last_turn ? state.metrics.last_turn : '--');
  setText('patrol-loop-hz', state.metrics && state.metrics.loop_hz != null ? `${state.metrics.loop_hz} Hz` : '--');
  setText('patrol-disable-reason', state.disable_reason || '--');
  setText('patrol-last-error', state.last_error || '--');
}

async function refreshPatrolState(){
  if(document.body.dataset.page !== 'patrol') return;
  try{
    const data = await window.patrolbotApi.getPatrolState();
    renderPatrolState(data.state || {});
  }catch(err){
    patrolLog('Failed to refresh patrol state.');
  }
}

async function savePatrolConfig(){
  const msg = document.getElementById('patrol-message');
  try{
    const payload = patrolPayloadFromForm();
    const data = await window.patrolbotApi.savePatrolConfig(payload);
    applyPatrolConfig(data.config || payload);
    if(msg) msg.textContent = 'Patrol config saved.';
    setActionMessage('Patrol config saved.', 'success');
    patrolLog('Patrol config saved.');
  }catch(err){
    if(msg) msg.textContent = 'Failed to save patrol config.';
    setActionMessage('Failed to save patrol config.', 'error');
    patrolLog('Failed to save patrol config.');
  }
}

document.addEventListener('DOMContentLoaded', ()=>{
  if(document.body.dataset.page !== 'patrol') return;
  loadPatrolConfig();
  refreshPatrolState();
  setInterval(refreshPatrolState, 1000);

  const saveBtn = document.getElementById('patrol-save-config');
  if(saveBtn) saveBtn.addEventListener('click', savePatrolConfig);

  const enableBtn = document.getElementById('patrol-enable');
  if(enableBtn) enableBtn.addEventListener('click', async()=>{
    try{
      await window.patrolbotApi.enablePatrol();
      patrolLog('Patrol enabled.');
      setActionMessage('Patrol enabled.', 'success');
      refreshPatrolState();
      refreshStatus().catch(()=>{});
    }catch(err){
      patrolLog('Failed to enable patrol.');
      setActionMessage('Failed to enable patrol.', 'error');
    }
  });

  const disableBtn = document.getElementById('patrol-disable');
  if(disableBtn) disableBtn.addEventListener('click', async()=>{
    try{
      await window.patrolbotApi.disablePatrol();
      patrolLog('Patrol disabled.');
      setActionMessage('Patrol disabled.', 'success');
      refreshPatrolState();
      refreshStatus().catch(()=>{});
    }catch(err){
      patrolLog('Failed to disable patrol.');
      setActionMessage('Failed to disable patrol.', 'error');
    }
  });

  const clearBtn = document.getElementById('patrol-clear-estop');
  if(clearBtn) clearBtn.addEventListener('click', async()=>{
    try{
      await window.patrolbotApi.motorClearEstop();
      patrolLog('E-stop latch cleared.');
      setActionMessage('E-stop latch cleared.', 'success');
      refreshStatus().catch(()=>{});
    }catch(err){
      patrolLog('Failed to clear E-stop latch.');
      setActionMessage('Failed to clear E-stop latch.', 'error');
    }
  });
});
