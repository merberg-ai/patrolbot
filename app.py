from patrolbot.app import app, create_app

if __name__ == '__main__':
    web_cfg = app.config['PATROLBOT_CONFIG']['web']
    app.run(host=web_cfg['host'], port=web_cfg['port'], debug=web_cfg.get('debug', False))
