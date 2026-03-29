console.log("[LOADED] patrol.js initializing...");

function patrolLog(message){
  const consoleEl = document.getElementById('patrol-console');
  if(!consoleEl) return;
  const stamp = new Date().toLocaleTimeString();
  consoleEl.textContent = `[${stamp}] ${message}
` + consoleEl.textContent;
}

function applyPatrolConfig(cfg){
  const set = (id, val) => { const el = document.getElementById(id); if(el && val !== undefined && val !== null) el.value = val; };
  const setChecked = (id, val) => { const el = document.getElementById(id); if(el) el.checked = !!val; };
  set('patrol-speed', cfg.speed);
  set('patrol-reverse-speed', cfg.reverse_speed);
  set('patrol-avoid-distance', cfg.avoidance_distance_cm);
  set('patrol-reverse-time', cfg.reverse_time_sec);
  set('patrol-turn-time', cfg.turn_time_sec);
  set('patrol-turn-mode', cfg.turn_mode);
  setChecked('patrol-scan-on-boot', cfg.scan_on_boot);
  set('patrol-pan-min', cfg.scan_pan_min);
  set('patrol-pan-max', cfg.scan_pan_max);
  set('patrol-scan-step', cfg.scan_step);
  set('patrol-scan-tilt', cfg.scan_tilt_angle);
  
  if (cfg.target_classes) {
     const classes = Array.isArray(cfg.target_classes) ? cfg.target_classes.join(', ') : String(cfg.target_classes);
     set('patrol-target-classes', classes);
  }
  if (cfg.obstacle_classes) {
     const classes = Array.isArray(cfg.obstacle_classes) ? cfg.obstacle_classes.join(', ') : String(cfg.obstacle_classes);
     set('patrol-obstacle-classes', classes);
  }
  if (cfg.log_only_classes) {
     const classes = Array.isArray(cfg.log_only_classes) ? cfg.log_only_classes.join(', ') : String(cfg.log_only_classes);
     set('patrol-log-only-classes', classes);
  }
  set('patrol-action-on-detect', cfg.action_on_detect);
  setChecked('patrol-save-screenshots', cfg.save_screenshots);
  set('patrol-target-min-area', cfg.target_min_area_ratio);
  set('patrol-obstacle-min-area', cfg.obstacle_min_area_ratio);
  set('patrol-acquire-frames', cfg.acquire_confirm_frames);
  set('patrol-lost-timeout', cfg.lost_timeout_s);
  set('patrol-obstacle-hold', cfg.obstacle_hold_time_s);
  set('patrol-log-cooldown', cfg.log_cooldown_sec);
  set('patrol-reacquire-hold', cfg.follow_reacquire_hold_s);
  set('patrol-follow-obstacle-bias', cfg.follow_obstacle_steer_bias);
}

function applyVisionConfig(cfg){
  const set = (id, val) => { const el = document.getElementById(id); if(el && val !== undefined && val !== null) el.value = val; };
  const setChecked = (id, val) => { const el = document.getElementById(id); if(el) el.checked = !!val; };
  
  setChecked('vision-enable-yolo', cfg.enable_yolo);
  set('vision-detector', cfg.detector);
}

function patrolPayloadFromForm(){
  return {
    speed: parseInt(document.getElementById('patrol-speed').value || '35', 10),
    reverse_speed: parseInt(document.getElementById('patrol-reverse-speed').value || '28', 10),
    avoidance_distance_cm: parseInt(document.getElementById('patrol-avoid-distance').value || '30', 10),
    reverse_time_sec: parseFloat(document.getElementById('patrol-reverse-time').value || '0.8'),
    turn_time_sec: parseFloat(document.getElementById('patrol-turn-time').value || '0.9'),
    turn_mode: document.getElementById('patrol-turn-mode').value,
    scan_on_boot: !!document.getElementById('patrol-scan-on-boot').checked,
    scan_pan_min: parseInt(document.getElementById('patrol-pan-min').value || '45', 10),
    scan_pan_max: parseInt(document.getElementById('patrol-pan-max').value || '135', 10),
    scan_step: parseInt(document.getElementById('patrol-scan-step').value || '2', 10),
    scan_tilt_angle: parseInt(document.getElementById('patrol-scan-tilt').value || '90', 10),
    
    action_on_detect: document.getElementById('patrol-action-on-detect').value || 'follow',
    target_classes: document.getElementById('patrol-target-classes').value || '',
    obstacle_classes: document.getElementById('patrol-obstacle-classes').value || '',
    log_only_classes: document.getElementById('patrol-log-only-classes').value || '',
    save_screenshots: !!document.getElementById('patrol-save-screenshots').checked,
    target_min_area_ratio: parseFloat(document.getElementById('patrol-target-min-area').value || '0.01'),
    obstacle_min_area_ratio: parseFloat(document.getElementById('patrol-obstacle-min-area').value || '0.05'),
    acquire_confirm_frames: parseInt(document.getElementById('patrol-acquire-frames').value || '3', 10),
    lost_timeout_s: parseFloat(document.getElementById('patrol-lost-timeout').value || '1.5'),
    obstacle_hold_time_s: parseFloat(document.getElementById('patrol-obstacle-hold').value || '0.5'),
    log_cooldown_sec: parseFloat(document.getElementById('patrol-log-cooldown').value || '5'),
    follow_reacquire_hold_s: parseFloat(document.getElementById('patrol-reacquire-hold').value || '0.75'),
    follow_obstacle_steer_bias: parseFloat(document.getElementById('patrol-follow-obstacle-bias').value || '0.18'),
  };
}

function visionPayloadFromForm(){
  return {
    enable_yolo: !!document.getElementById('vision-enable-yolo').checked,
    detector: document.getElementById('vision-detector').value || 'face',
  };
}

async function loadConfigs(){
  if(document.body.dataset.page !== 'patrol') return;
  const pmsg = document.getElementById('patrol-message');
  const vmsg = document.getElementById('vision-message');
  try{
    const pdata = await window.patrolbotApi.getPatrolConfig();
    applyPatrolConfig(pdata.config || {});
    if(pmsg) pmsg.textContent = 'Patrol config loaded.';
    
    // Use the central API wrapper
    const vdata = await window.patrolbotApi.getVisionConfig();
    applyVisionConfig(vdata.config || {});
    if(vmsg) vmsg.textContent = 'Vision config loaded.';
  }catch(err){
    if(pmsg) pmsg.textContent = 'Failed to load config.';
    patrolLog('Failed to load configs: ' + err);
  }
}

function updatePatrolToggleButton(enabled){
  const btn = document.getElementById('patrol-toggle');
  if(!btn) return;
  btn.textContent = enabled ? 'Stop Patrol' : 'Start Patrol';
  btn.classList.toggle('danger', !!enabled);
  btn.classList.toggle('primary', !enabled);
}

function renderPatrolState(state){
  if(!state) return;
  setText('patrol-enabled', state.enabled ? 'ON' : 'OFF');
  updatePatrolToggleButton(!!state.enabled);
  setText('patrol-drive-state', state.drive_state || '--');
  setText('patrol-distance', state.metrics && state.metrics.last_distance_cm != null ? `${state.metrics.last_distance_cm} cm` : '--');
  setText('patrol-rear-distance', state.metrics && state.metrics.last_rear_distance_cm != null ? `${state.metrics.last_rear_distance_cm} cm` : '--');
  setText('patrol-obstacles', state.metrics && state.metrics.obstacle_count != null ? String(state.metrics.obstacle_count) : '0');
  
  setText('patrol-detect-count', state.detect_count != null ? String(state.detect_count) : '0');
  setText('patrol-last-target', state.last_detected || '--');
  setText('patrol-current-obstacle', state.metrics && state.metrics.current_obstacle_label ? String(state.metrics.current_obstacle_label) : '--');
  
  setText('patrol-disable-reason', state.disable_reason || '--');
  setText('patrol-last-error', state.last_error || '--');
}

async function refreshPatrolState(){
  if(document.body.dataset.page !== 'patrol') return;
  try{
    const data = await window.patrolbotApi.getPatrolState();
    renderPatrolState(data.state || {});
  }catch(err){
      // silence
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

async function saveVisionConfig(){
  const msg = document.getElementById('vision-message');
  try{
    const visionPayload = visionPayloadFromForm();
    const patrolPayload = {
      action_on_detect: document.getElementById('patrol-action-on-detect').value || 'follow',
      target_classes: document.getElementById('patrol-target-classes').value || '',
      obstacle_classes: document.getElementById('patrol-obstacle-classes').value || '',
      log_only_classes: document.getElementById('patrol-log-only-classes').value || '',
      save_screenshots: !!document.getElementById('patrol-save-screenshots').checked,
      target_min_area_ratio: parseFloat(document.getElementById('patrol-target-min-area').value || '0.01'),
      obstacle_min_area_ratio: parseFloat(document.getElementById('patrol-obstacle-min-area').value || '0.05'),
    };
    await Promise.all([
      window.patrolbotApi.saveVisionConfig(visionPayload),
      window.patrolbotApi.savePatrolConfig(patrolPayload),
    ]);
    if(msg) msg.textContent = 'Vision & targeting config saved.';
    setActionMessage('Vision & targeting config saved.', 'success');
    patrolLog('Vision & targeting config saved.');
  }catch(err){
    if(msg) msg.textContent = 'Failed to save vision config.';
    setActionMessage('Failed to save vision config.', 'error');
    patrolLog('Failed to save vision config.');
  }
}

document.addEventListener('DOMContentLoaded', ()=>{
  if(document.body.dataset.page !== 'patrol') return;
  loadConfigs();
  refreshPatrolState();
  setInterval(refreshPatrolState, 1000);

  const savePatrolBtn = document.getElementById('patrol-save-config');
  if(savePatrolBtn) savePatrolBtn.addEventListener('click', savePatrolConfig);
  
  const saveVisionBtn = document.getElementById('vision-save-config');
  if(saveVisionBtn) saveVisionBtn.addEventListener('click', saveVisionConfig);

  const toggleBtn = document.getElementById('patrol-toggle');
  if(toggleBtn) toggleBtn.addEventListener('click', async()=>{
    const statusEl = document.getElementById('patrol-enabled');
    const enabledNow = (statusEl ? (statusEl.textContent || '') : '').trim() === 'ON';
    try{
      if(enabledNow){
        await window.patrolbotApi.disablePatrol();
        patrolLog('Patrol disabled.');
        setActionMessage('Patrol disabled.', 'success');
      }else{
        await window.patrolbotApi.enablePatrol();
        patrolLog('Patrol enabled.');
        setActionMessage('Patrol enabled.', 'success');
        
        // Ensure vision stream gets started if not on
        if (window.patrolbotState && window.patrolbotState.refreshTimer) {
             window.patrolbotApi.enableVision().catch(()=>{});
        }
      }
      refreshPatrolState();
      refreshStatus().catch(()=>{});
    }catch(err){
      patrolLog((enabledNow ? 'Failed to disable patrol.' : 'Failed to enable patrol.') + ' Error: ' + err);
      setActionMessage(enabledNow ? 'Failed to disable patrol.' : 'Failed to enable patrol.', 'error');
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
  patrolLog('Patrol Console script initialized.');
});
