function bindLightAction(actionName, handler, successMessage){
  const button = document.querySelector(`[data-action="${actionName}"]`);
  if(!button) return;
  button.addEventListener('click', async(event)=>{
    event.preventDefault();
    try{
      await invokeAndRefresh(handler, { successMessage, errorMessage: `Failed light action: ${actionName}` });
    }catch(err){
      console.error(`Light action ${actionName} failed`, err);
    }
  });
}

document.addEventListener('DOMContentLoaded', ()=>{
  bindLightAction('led-off', ()=> window.patrolbotApi.lightsOff(), 'Eyes off.');
  bindLightAction('led-ready', ()=> window.patrolbotApi.setLightState('READY'), 'Lights set to ready.');
  bindLightAction('led-error', ()=> window.patrolbotApi.setLightState('ERROR'), 'Lights set to error.');
  bindLightAction('led-police', ()=> window.patrolbotApi.setLightState('POLICE'), 'Police mode engaged.');
  bindLightAction('led-auto', ()=> window.patrolbotApi.setLightState('AUTO'), 'Lights returned to auto mode.');
  bindLightAction('led-custom-blue', ()=> window.patrolbotApi.setLightColor(0,0,255), 'Lights set to blue.');
  bindLightAction('led-custom-white', ()=> window.patrolbotApi.setLightColor(255,255,255), 'Lights set to white.');
});
