from __future__ import annotations
import atexit, os
from flask import Flask
from patrolbot.api.routes_motion import register_motion_routes
from patrolbot.api.routes_settings import register_settings_routes
from patrolbot.api.routes_status import register_status_routes
from patrolbot.api.routes_system import register_system_routes
from patrolbot.api.routes_patrol import register_patrol_routes
from patrolbot.config import load_config
from patrolbot.logging_setup import setup_logging
from patrolbot.services.safety import safe_shutdown
from patrolbot.services.startup import StartupManager
from patrolbot.webui.routes import register_webui_routes

def create_app() -> Flask:
    config = load_config()
    logger = setup_logging(config)
    runtime = StartupManager(config=config, logger=logger).initialize()
    app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'webui','templates'), static_folder=os.path.join(os.path.dirname(__file__), 'webui','static'))
    app.config['PATROLBOT_RUNTIME'] = runtime
    app.config['PATROLBOT_CONFIG'] = config
    register_webui_routes(app)
    register_status_routes(app)
    register_motion_routes(app)
    register_settings_routes(app)
    register_system_routes(app)
    register_patrol_routes(app)
    @app.get('/healthz')
    def healthz():
        return {'ok': True, 'service': 'patrolbot'}
    atexit.register(lambda: safe_shutdown(runtime, logger))
    runtime.status_leds.set_state('READY')
    return app
app = create_app()
if __name__ == '__main__':
    web_cfg = app.config['PATROLBOT_CONFIG']['web']
    app.run(host=web_cfg['host'], port=web_cfg['port'], debug=web_cfg.get('debug', False))
