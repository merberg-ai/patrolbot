from __future__ import annotations
from flask import Flask, redirect, render_template

def register_webui_routes(app: Flask) -> None:
    @app.get('/')
    def home():
        return redirect('/patrol')

    @app.get('/patrol')
    def patrol():
        return render_template('patrol.html', page='patrol')

    @app.get('/settings')
    def settings():
        return render_template('settings.html', page='settings')

    @app.get('/system')
    def system():
        return render_template('system.html', page='system')
