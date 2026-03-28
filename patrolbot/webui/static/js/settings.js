async function loadServoTrimSettings(){
  if(document.body.dataset.page!=='settings') return;
  const msg = document.getElementById('settings-message');
  try{
    const data = await window.patrolbotApi.getServoTrim();
    document.getElementById('trim-steering').value = data.steering_trim ?? 0;
    document.getElementById('trim-pan').value = data.camera_pan_trim ?? 0;
    document.getElementById('trim-tilt').value = data.camera_tilt_trim ?? 0;
    if(msg) msg.textContent = 'Servo trim loaded.';
  }catch(err){
    if(msg) msg.textContent = 'Failed to load trim settings.';
  }
}

async function saveServoTrimSettings(){
  const msg = document.getElementById('settings-message');
  try{
    const payload = {
      steering_trim: parseInt(document.getElementById('trim-steering').value || '0', 10),
      camera_pan_trim: parseInt(document.getElementById('trim-pan').value || '0', 10),
      camera_tilt_trim: parseInt(document.getElementById('trim-tilt').value || '0', 10),
    };
    const data = await window.patrolbotApi.saveServoTrim(payload);
    document.getElementById('trim-steering').value = data.steering_trim ?? 0;
    document.getElementById('trim-pan').value = data.camera_pan_trim ?? 0;
    document.getElementById('trim-tilt').value = data.camera_tilt_trim ?? 0;
    if(msg) msg.textContent = 'Servo trim saved.';
    setActionMessage('Servo trim saved.', 'success');
  }catch(err){
    if(msg) msg.textContent = 'Failed to save trim settings.';
    setActionMessage('Failed to save trim settings.', 'error');
  }
}

function adjustTrimInput(id, delta){
  const el = document.getElementById(id);
  if(!el) return;
  const next = Math.max(-20, Math.min(20, parseInt(el.value || '0', 10) + delta));
  el.value = next;
}

function syncCameraSlider(id, digits=2){
  const input = document.getElementById(id);
  const label = document.getElementById(`${id}-label`);
  if(!input || !label) return;
  const value = Number(input.value || 0);
  label.textContent = digits === 0 ? String(Math.round(value)) : value.toFixed(digits);
}

function setCameraManualGainVisibility(){
  const awb = document.getElementById('camera-awb-mode');
  const red = document.getElementById('camera-manual-red-gain');
  const blue = document.getElementById('camera-manual-blue-gain');
  if(!awb || !red || !blue) return;
  const enabled = awb.value === 'custom';
  red.disabled = !enabled;
  blue.disabled = !enabled;
}

function refreshSettingsCameraPreview(){
  const img = document.getElementById('settings-camera-preview');
  if(!img) return;
  img.src = `/video_feed?view=settings&_ts=${Date.now()}`;
}

function cameraPayloadFromForm(){
  const manualRedValue = document.getElementById('camera-manual-red-gain').value;
  const manualBlueValue = document.getElementById('camera-manual-blue-gain').value;
  return {
    awb_mode: document.getElementById('camera-awb-mode').value,
    fps: parseInt(document.getElementById('camera-fps').value || '20', 10),
    brightness: parseFloat(document.getElementById('camera-brightness').value || '0'),
    contrast: parseFloat(document.getElementById('camera-contrast').value || '1'),
    saturation: parseFloat(document.getElementById('camera-saturation').value || '1'),
    sharpness: parseFloat(document.getElementById('camera-sharpness').value || '1'),
    exposure_compensation: parseFloat(document.getElementById('camera-exposure-compensation').value || '0'),
    manual_red_gain: manualRedValue === '' ? null : parseFloat(manualRedValue),
    manual_blue_gain: manualBlueValue === '' ? null : parseFloat(manualBlueValue),
  };
}

function applyCameraSettingsToForm(settings){
  document.getElementById('camera-awb-mode').value = settings.awb_mode ?? 'auto';
  document.getElementById('camera-fps').value = settings.fps ?? 20;
  document.getElementById('camera-brightness').value = settings.brightness ?? 0;
  document.getElementById('camera-contrast').value = settings.contrast ?? 1;
  document.getElementById('camera-saturation').value = settings.saturation ?? 1;
  document.getElementById('camera-sharpness').value = settings.sharpness ?? 1;
  document.getElementById('camera-exposure-compensation').value = settings.exposure_compensation ?? 0;
  document.getElementById('camera-manual-red-gain').value = settings.manual_red_gain ?? '';
  document.getElementById('camera-manual-blue-gain').value = settings.manual_blue_gain ?? '';
  ['camera-fps','camera-brightness','camera-contrast','camera-saturation','camera-sharpness','camera-exposure-compensation'].forEach(id=> syncCameraSlider(id, id === 'camera-fps' ? 0 : 2));
  setCameraManualGainVisibility();
}

async function loadCameraSettings(){
  if(document.body.dataset.page!=='settings') return;
  const msg = document.getElementById('camera-settings-message');
  try{
    const data = await window.patrolbotApi.getCameraSettings();
    applyCameraSettingsToForm(data.settings || {});
    refreshSettingsCameraPreview();
    if(msg) msg.textContent = data.camera_running ? 'Camera settings loaded. Live camera is running.' : 'Camera settings loaded. Camera is currently offline.';
  }catch(err){
    if(msg) msg.textContent = 'Failed to load camera settings.';
  }
}

async function saveCameraSettings(){
  const msg = document.getElementById('camera-settings-message');
  try{
    if(msg) msg.textContent = 'Saving camera settings and restarting camera…';
    setActionMessage('Saving camera settings and restarting camera…', 'info');
    const data = await window.patrolbotApi.saveCameraSettings(cameraPayloadFromForm());
    applyCameraSettingsToForm(data.settings || {});
    refreshSettingsCameraPreview();
    const warnings = Array.isArray(data.warnings) && data.warnings.length ? ` ${data.warnings.join(' ')}` : '';
    if(msg) msg.textContent = data.camera_running ? `Camera settings saved and camera restarted.${warnings}` : `Camera settings saved, but camera is offline after restart.${warnings}`;
  }catch(err){
    if(msg) msg.textContent = 'Failed to save camera settings.';
    setActionMessage('Failed to save camera settings.', 'error');
  }
}

async function resetCameraSettings(){
  const msg = document.getElementById('camera-settings-message');
  try{
    if(msg) msg.textContent = 'Resetting camera settings to defaults and restarting camera…';
    setActionMessage('Resetting camera settings to defaults and restarting camera…', 'info');
    const data = await window.patrolbotApi.resetCameraSettings();
    applyCameraSettingsToForm(data.settings || {});
    refreshSettingsCameraPreview();
    const warnings = Array.isArray(data.warnings) && data.warnings.length ? ` ${data.warnings.join(' ')}` : '';
    if(msg) msg.textContent = data.camera_running ? `Camera defaults restored and camera restarted.${warnings}` : `Camera defaults restored, but camera is offline after restart.${warnings}`;
  }catch(err){
    if(msg) msg.textContent = 'Failed to reset camera settings.';
    setActionMessage('Failed to reset camera settings.', 'error');
  }
}

function sensorStatusText(sensor){
  if(!sensor) return '--';
  if(sensor.detected && sensor.healthy) return `Detected · ${sensor.enabled ? sensor.use_mode : 'disabled'}`;
  if(sensor.detected) return 'Detected · unhealthy';
  return 'Missing / no valid echo';
}

function sensorDetailText(sensor){
  if(!sensor) return '';
  const pinText = (sensor.trigger_pin != null && sensor.echo_pin != null) ? `Trig ${sensor.trigger_pin} / Echo ${sensor.echo_pin}` : '';
  const distText = sensor.last_distance_cm != null ? ` · ${sensor.last_distance_cm} cm` : '';
  const errText = sensor.last_error ? ` · ${sensor.last_error}` : '';
  return `${pinText}${distText}${errText}`.trim();
}

function applySensorSettings(data){
  const front = data.front_ultrasonic || data.ultrasonic || {};
  const rear = data.rear_ultrasonic || data.ultrasonic_rear || {};
  const fMode = document.getElementById('sensor-front-mode');
  const rMode = document.getElementById('sensor-rear-mode');
  if(fMode){ fMode.value = front.use_mode || 'off'; }
  if(rMode){ rMode.value = rear.use_mode || 'off'; }
  const fs = document.getElementById('sensor-front-status'); if(fs) fs.textContent = sensorStatusText(front);
  const rs = document.getElementById('sensor-rear-status'); if(rs) rs.textContent = sensorStatusText(rear);
  const fd = document.getElementById('sensor-front-detail'); if(fd) fd.textContent = sensorDetailText(front);
  const rd = document.getElementById('sensor-rear-detail'); if(rd) rd.textContent = sensorDetailText(rear);
}

async function loadSensorSettings(){
  const msg = document.getElementById('sensor-settings-message');
  try{
    const data = await window.patrolbotApi.getSensorSettings();
    applySensorSettings(data);
    if(msg) msg.textContent = 'Sensor status loaded.';
  }catch(err){
    if(msg) msg.textContent = 'Failed to load sensor settings.';
  }
}

async function saveSensorSettings(){
  const msg = document.getElementById('sensor-settings-message');
  try{
    const payload = {
      ultrasonic: { enabled: true, use_mode: document.getElementById('sensor-front-mode').value },
      ultrasonic_rear: { enabled: true, use_mode: document.getElementById('sensor-rear-mode').value },
    };
    const data = await window.patrolbotApi.saveSensorSettings(payload);
    applySensorSettings(data);
    if(msg) msg.textContent = 'Sensor settings saved.';
    setActionMessage('Sensor settings saved.', 'success');
    refreshStatus().catch(()=>{});
  }catch(err){
    if(msg) msg.textContent = 'Failed to save sensor settings.';
    setActionMessage('Failed to save sensor settings.', 'error');
  }
}

async function probeSensors(target='all'){
  const msg = document.getElementById('sensor-settings-message');
  try{
    if(msg) msg.textContent = `Probing ${target === 'all' ? 'sensors' : target + ' sensor'}…`;
    const data = await window.patrolbotApi.probeSensors(target);
    applySensorSettings(data);
    if(msg) msg.textContent = 'Sensor probe complete.';
    refreshStatus().catch(()=>{});
  }catch(err){
    if(msg) msg.textContent = 'Sensor probe failed.';
  }
}

async function loadSystemSettings(){
  const msg = document.getElementById('system-settings-message');
  try{
    const data = await window.patrolbotApi.getSystemSettings();
    const toggle = document.getElementById('start-patrol-on-boot');
    if(toggle) toggle.checked = !!data.start_patrol_on_boot;
    if(msg) msg.textContent = 'Boot settings loaded.';
  }catch(err){
    if(msg) msg.textContent = 'Failed to load boot settings.';
  }
}

async function saveSystemSettings(){
  const msg = document.getElementById('system-settings-message');
  try{
    const payload = { start_patrol_on_boot: !!document.getElementById('start-patrol-on-boot').checked };
    await window.patrolbotApi.saveSystemSettings(payload);
    if(msg) msg.textContent = 'Boot settings saved.';
    setActionMessage('Boot settings saved.', 'success');
  }catch(err){
    if(msg) msg.textContent = 'Failed to save boot settings.';
    setActionMessage('Failed to save boot settings.', 'error');
  }
}

async function loadWifiStatus(){
  const msg = document.getElementById('wifi-message');
  try{
    const data = await window.patrolbotApi.getNetworkStatus();
    const connected = !!data.connected;
    document.getElementById('wifi-connected').textContent = connected ? 'ON' : 'OFF';
    document.getElementById('wifi-ssid').textContent = data.ssid || '--';
    document.getElementById('wifi-ip').textContent = data.ip || '--';
    if(msg) msg.textContent = connected ? `Connected to ${data.ssid || 'Wi‑Fi'}.` : 'Wi‑Fi is currently disconnected.';
  }catch(err){
    if(msg) msg.textContent = 'Failed to load Wi‑Fi status.';
  }
}

async function scanWifiNetworks(){
  const msg = document.getElementById('wifi-message');
  const select = document.getElementById('wifi-network-select');
  try{
    if(msg) msg.textContent = 'Scanning for Wi‑Fi networks…';
    const data = await window.patrolbotApi.scanNetworks();
    const networks = data.networks || [];
    select.innerHTML = '';
    if(!networks.length){
      select.innerHTML = '<option value="">No networks found</option>';
    } else {
      networks.forEach(net => {
        const opt = document.createElement('option');
        opt.value = net.ssid;
        opt.textContent = `${net.ssid} (${net.signal}%) ${net.security || 'open'}`;
        select.appendChild(opt);
      });
    }
    if(msg) msg.textContent = `Found ${networks.length} network${networks.length === 1 ? '' : 's'}.`;
  }catch(err){
    if(msg) msg.textContent = 'Wi‑Fi scan failed.';
  }
}

async function connectWifi(){
  const msg = document.getElementById('wifi-message');
  try{
    const ssid = document.getElementById('wifi-network-select').value;
    const password = document.getElementById('wifi-password').value;
    if(!ssid){
      if(msg) msg.textContent = 'Select a network first.';
      return;
    }
    if(msg) msg.textContent = `Connecting to ${ssid}…`;
    const data = await window.patrolbotApi.connectNetwork({ ssid, password });
    if(data.ok){
      if(msg) msg.textContent = data.message || `Connected to ${ssid}.`;
      loadWifiStatus();
      refreshStatus().catch(()=>{});
    }else{
      if(msg) msg.textContent = data.error || 'Failed to connect.';
    }
  }catch(err){
    if(msg) msg.textContent = 'Failed to connect to Wi‑Fi.';
  }
}

document.addEventListener('DOMContentLoaded', ()=>{
  if(document.body.dataset.page!=='settings') return;
  loadServoTrimSettings();
  loadCameraSettings();
  loadSystemSettings();
  loadSensorSettings();
  loadWifiStatus();
  scanWifiNetworks();

  document.querySelectorAll('[data-trim-target]').forEach(btn=>{
    btn.addEventListener('click', ()=> adjustTrimInput(btn.dataset.trimTarget, parseInt(btn.dataset.delta || '0', 10)));
  });

  ['camera-fps','camera-brightness','camera-contrast','camera-saturation','camera-sharpness','camera-exposure-compensation'].forEach(id=>{
    const input = document.getElementById(id);
    if(input) input.addEventListener('input', ()=> syncCameraSlider(id, id === 'camera-fps' ? 0 : 2));
  });

  const awb = document.getElementById('camera-awb-mode');
  if(awb) awb.addEventListener('change', setCameraManualGainVisibility);

  const saveBtn = document.getElementById('save-servo-trims');
  if(saveBtn) saveBtn.addEventListener('click', saveServoTrimSettings);
  const saveSystemBtn = document.getElementById('save-system-settings');
  if(saveSystemBtn) saveSystemBtn.addEventListener('click', saveSystemSettings);
  const saveSensorBtn = document.getElementById('save-sensor-settings');
  if(saveSensorBtn) saveSensorBtn.addEventListener('click', saveSensorSettings);
  const probeFrontBtn = document.getElementById('probe-front-sensor');
  if(probeFrontBtn) probeFrontBtn.addEventListener('click', ()=> probeSensors('front'));
  const probeRearBtn = document.getElementById('probe-rear-sensor');
  if(probeRearBtn) probeRearBtn.addEventListener('click', ()=> probeSensors('rear'));
  const probeAllBtn = document.getElementById('probe-all-sensors');
  if(probeAllBtn) probeAllBtn.addEventListener('click', ()=> probeSensors('all'));
  const wifiRefreshBtn = document.getElementById('wifi-refresh');
  if(wifiRefreshBtn) wifiRefreshBtn.addEventListener('click', loadWifiStatus);
  const wifiScanBtn = document.getElementById('wifi-scan');
  if(wifiScanBtn) wifiScanBtn.addEventListener('click', scanWifiNetworks);
  const wifiConnectBtn = document.getElementById('wifi-connect');
  if(wifiConnectBtn) wifiConnectBtn.addEventListener('click', connectWifi);

  const saveCameraBtn = document.getElementById('save-camera-settings');
  if(saveCameraBtn) saveCameraBtn.addEventListener('click', saveCameraSettings);
  const resetCameraBtn = document.getElementById('reset-camera-settings');
  if(resetCameraBtn) resetCameraBtn.addEventListener('click', resetCameraSettings);

  const centerBtn = document.getElementById('test-steering-center');
  if(centerBtn) centerBtn.addEventListener('click', async()=>{ await window.patrolbotApi.steeringCenter(); await refreshStatus(); });

  const homeBtn = document.getElementById('test-camera-home');
  if(homeBtn) homeBtn.addEventListener('click', async()=>{ await window.patrolbotApi.cameraHome(); await refreshStatus(); });
});
