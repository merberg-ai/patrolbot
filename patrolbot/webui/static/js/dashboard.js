window.refreshDashboardTelemetry = function refreshDashboardTelemetry(rawData){
  const page = document.body?.dataset?.page;
  if(page !== 'dashboard') return;

  const data = normalizeStatus(rawData);
  const set = (id, value) => {
    const el = document.getElementById(id);
    if(el) el.textContent = value;
  };

  set('dash-battery-voltage', data.battery_voltage == null ? '--' : `${data.battery_voltage} V`);
  set('dash-battery-status', data.battery_status ?? '--');
  set('dash-distance-cm', data.distance_cm == null ? '--' : `${data.distance_cm} cm`);
  set('dash-steering-angle', data.steering_angle == null ? '--' : `${data.steering_angle}°`);
  set('dash-pan-angle', data.pan_angle == null ? '--' : `${data.pan_angle}°`);
  set('dash-tilt-angle', data.tilt_angle == null ? '--' : `${data.tilt_angle}°`);
  set('dash-motor-state', data.motor_state ?? '--');
  set('dash-motor-speed', data._speed_value == null ? '--' : `${data._speed_value}%`);
  set('dash-command-age', fmtSeconds(data._command_age_value, 'idle'));
  set('dash-timeout', fmtSeconds(data._timeout_value));
  set('dash-estop', data._effective_estop ? 'ON' : 'OFF');
  set('dash-motion-lock', data._effective_motion_lock ? 'ON' : 'OFF');
};

document.addEventListener('DOMContentLoaded', ()=>{
  if(document.body?.dataset?.page !== 'dashboard') return;
  document.addEventListener('patrolbot:status', (event)=>{
    window.refreshDashboardTelemetry(event.detail || {});
  });
  if(window.patrolbotState?.lastStatus){
    window.refreshDashboardTelemetry(window.patrolbotState.lastStatus);
  } else {
    refreshStatus().catch(()=>{});
  }
});
