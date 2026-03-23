function fmtValue(value, suffix=''){
  if(value === null || value === undefined || Number.isNaN(value)) return '--';
  return `${value}${suffix}`;
}

function fmtBoolState(value){
  return value ? 'ON' : 'OFF';
}

function fmtSeconds(value, fallback='--'){
  if(value === null || value === undefined || Number.isNaN(value)) return fallback;
  return `${Number(value).toFixed(2)} s`;
}

function setText(id, value){
  const el = document.getElementById(id);
  if(el) el.textContent = value;
}

function setActionMessage(message, kind='info'){
  const el = document.getElementById('global-action-message');
  if(!el) return;
  el.textContent = message || '';
  el.classList.remove('is-error', 'is-success', 'is-info');
  if(message){
    el.classList.add(kind === 'error' ? 'is-error' : (kind === 'success' ? 'is-success' : 'is-info'));
  }
}

function setBatteryProgress(percent, status){
  const fill = document.getElementById('battery-progress-fill');
  if(!fill) return;
  const safePercent = Math.max(0, Math.min(100, Number(percent || 0)));
  fill.style.width = `${safePercent}%`;
  fill.classList.remove('is-ok', 'is-low', 'is-critical');
  if(status === 'critical') fill.classList.add('is-critical');
  else if(status === 'low') fill.classList.add('is-low');
  else fill.classList.add('is-ok');
}

function motionLockEffective(data){
  return Boolean(data.motion_lock_effective || data.motion_locked || data.motion_lock_state || data.estop_latched || data.estop_state);
}

function estopEffective(data){
  return Boolean(data.estop_latched || data.estop_state);
}

function bannerStatusText(data){
  if(estopEffective(data)) return 'E-STOP ACTIVE';
  if(motionLockEffective(data)) return 'MOTION LOCKED';
  if(data.battery_status === 'critical') return 'BATTERY CRITICAL';
  if(data.battery_status === 'low') return 'BATTERY LOW';
  if(data.motor_state && String(data.motor_state).toLowerCase() !== 'stopped') return 'MOVING';
  return 'READY';
}

function bannerStatusClass(data){
  if(estopEffective(data)) return 'status-estop';
  if(motionLockEffective(data)) return 'status-locked';
  if(data.battery_status === 'critical') return 'status-critical';
  if(data.battery_status === 'low') return 'status-low';
  if(data.motor_state && String(data.motor_state).toLowerCase() !== 'stopped') return 'status-moving';
  return 'status-ready';
}

function normalizeStatus(raw){
  const data = {...(raw || {})};
  data._effective_estop = estopEffective(data);
  data._effective_motion_lock = motionLockEffective(data);
  data._speed_value = data.motor_speed ?? data.speed ?? null;
  data._command_age_value = data.last_command_age_s ?? data.command_age ?? null;
  data._timeout_value = data.motor_timeout_s ?? data.timeout ?? null;
  data._banner_status_text = bannerStatusText(data);
  data._banner_status_class = bannerStatusClass(data);
  return data;
}

function applyStatusTheme(data){
  const banner = document.getElementById('telemetry-banner');
  const pill = document.getElementById('status-pill');
  const statusClass = data._banner_status_class || 'status-ready';
  if(banner){
    banner.classList.remove('telemetry-banner-ready', 'telemetry-banner-moving', 'telemetry-banner-low', 'telemetry-banner-critical', 'telemetry-banner-locked', 'telemetry-banner-estop');
    const bannerMap = {
      'status-ready': 'telemetry-banner-ready',
      'status-moving': 'telemetry-banner-moving',
      'status-low': 'telemetry-banner-low',
      'status-critical': 'telemetry-banner-critical',
      'status-locked': 'telemetry-banner-locked',
      'status-estop': 'telemetry-banner-estop',
    };
    banner.classList.add(bannerMap[statusClass] || 'telemetry-banner-ready');
  }
  if(pill){
    pill.classList.remove('status-ready', 'status-moving', 'status-low', 'status-critical', 'status-locked', 'status-estop');
    pill.classList.add(statusClass);
    pill.textContent = data._effective_estop ? 'E-STOP' : (data._effective_motion_lock ? 'LOCKED' : data._banner_status_text.toLowerCase());
  }
}

function renderGlobalStatus(rawData){
  const data = normalizeStatus(rawData);
  const batteryPercentText = data.battery_percent == null ? '--' : `${data.battery_percent}%`;
  setText('battery-voltage', data.battery_voltage == null ? '--' : `${data.battery_voltage} V`);
  setText('distance-cm', data.distance_cm == null ? '--' : `${data.distance_cm} cm`);
  setText('banner-battery-label', data.battery_voltage == null ? batteryPercentText : `${batteryPercentText} · ${data.battery_voltage} V`);
  setText('banner-status-text', data._banner_status_text);
  setText('banner-motor-state', data.motor_state ?? '--');
  setText('banner-motor-speed', data._speed_value == null ? '--' : `${data._speed_value}%`);
  setText('banner-estop', fmtBoolState(data._effective_estop));
  setText('banner-motion-lock', fmtBoolState(data._effective_motion_lock));
  setBatteryProgress(data.battery_percent, data.battery_status);
  applyStatusTheme(data);

  const estopButton = document.querySelector('[data-action="global-estop"]');
  if(estopButton){
    estopButton.classList.toggle('active', data._effective_estop);
    estopButton.textContent = data._effective_estop ? 'E-STOP ACTIVE' : 'E-STOP';
    estopButton.disabled = false;
  }

  const speedSlider = document.getElementById('drive-speed');
  const speedLabel = document.getElementById('drive-speed-label');
  if(speedSlider && speedLabel){
    const sliderValue = Number(speedSlider.value || 40);
    speedLabel.textContent = `${sliderValue}%`;
  }

  window.patrolbotState.lastStatus = data;
  document.dispatchEvent(new CustomEvent('patrolbot:status', {detail: data}));
}

let driveHoldTimer = null;
window.patrolbotState = window.patrolbotState || { lastStatus: null, refreshTimer: null, isRefreshing: false };

function getDriveSpeed(){
  const slider = document.getElementById('drive-speed');
  return slider ? Number(slider.value || 40) : 40;
}

function stopDriveHold(){
  if(driveHoldTimer){
    clearInterval(driveHoldTimer);
    driveHoldTimer = null;
  }
}

function bindHoldButton(actionName, handler){
  const button = document.querySelector(`[data-action="${actionName}"]`);
  if(!button) return;
  const start = async (event) => {
    event.preventDefault();
    stopDriveHold();
    await handler();
    driveHoldTimer = setInterval(handler, 250);
  };
  const stop = async (event) => {
    if(event) event.preventDefault();
    stopDriveHold();
    await window.patrolbotApi.motorStop();
    await refreshStatus();
  };
  ['mousedown','touchstart'].forEach(evt=>button.addEventListener(evt,start,{passive:false}));
  ['mouseup','mouseleave','touchend','touchcancel'].forEach(evt=>button.addEventListener(evt,stop,{passive:false}));
}

async function invokeAndRefresh(fn, options={}){
  const {pendingMessage=null, successMessage=null, errorMessage='Request failed.'} = options;
  if(pendingMessage) setActionMessage(pendingMessage, 'info');
  try{
    const result = await fn();
    await refreshStatus();
    if(successMessage) setActionMessage(successMessage, 'success');
    return result;
  }catch(err){
    setActionMessage(errorMessage, 'error');
    throw err;
  }
}

async function refreshStatus(force=false){
  if(window.patrolbotState.isRefreshing && !force){
    return window.patrolbotState.lastStatus;
  }
  window.patrolbotState.isRefreshing = true;
  try{
    const data = await window.patrolbotApi.getStatus();
    renderGlobalStatus(data);
    return window.patrolbotState.lastStatus;
  }catch(err){
    setText('banner-status-text', 'OFFLINE');
    setText('status-pill', 'offline');
    setActionMessage('Robot status is offline.', 'error');
    throw err;
  }finally{
    window.patrolbotState.isRefreshing = false;
  }
}

function startStatusPolling(intervalMs=2000){
  if(window.patrolbotState.refreshTimer){
    clearInterval(window.patrolbotState.refreshTimer);
  }
  window.patrolbotState.refreshTimer = setInterval(()=>{
    refreshStatus().catch(()=>{});
  }, intervalMs);
}

document.addEventListener('DOMContentLoaded', ()=>{
  const estopButton = document.querySelector('[data-action="global-estop"]');
  if(estopButton){
    estopButton.addEventListener('click', async()=>{
      await invokeAndRefresh(()=>window.patrolbotApi.motorEstop(), {
        pendingMessage: 'Sending E-STOP…',
        successMessage: 'E-STOP latched.',
        errorMessage: 'Failed to latch E-STOP.',
      });
    });
  }
  refreshStatus().catch(()=>{});
  startStatusPolling(2000);
});
