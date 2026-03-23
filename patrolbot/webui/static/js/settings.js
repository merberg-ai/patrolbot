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


document.addEventListener('DOMContentLoaded', ()=>{
  if(document.body.dataset.page!=='settings') return;
  loadServoTrimSettings();
  loadCameraSettings();

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

  const saveCameraBtn = document.getElementById('save-camera-settings');
  if(saveCameraBtn) saveCameraBtn.addEventListener('click', saveCameraSettings);

  const resetCameraBtn = document.getElementById('reset-camera-settings');
  if(resetCameraBtn) resetCameraBtn.addEventListener('click', resetCameraSettings);

  const centerBtn = document.getElementById('test-steering-center');
  if(centerBtn) centerBtn.addEventListener('click', async()=>{ await window.patrolbotApi.steeringCenter(); await refreshStatus(); });

  const homeBtn = document.getElementById('test-camera-home');
  if(homeBtn) homeBtn.addEventListener('click', async()=>{ await window.patrolbotApi.cameraHome(); await refreshStatus(); });
});
