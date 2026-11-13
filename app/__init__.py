import os
from datetime import datetime
from flask import Flask, render_template, request, session, redirect, url_for, flash
from app.config import config_by_name
from app.extensions import db, csrf


def create_app(config_name=None):
    """Application factory for LifeBridge."""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name.get(config_name, config_by_name['default']))

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)

    # Force password change before accessing protected features
    @app.before_request
    def check_password_change():
        from app.utils import get_current_user
        if request.endpoint and (request.endpoint.startswith('static') or request.endpoint in ('auth.profile', 'auth.logout', 'auth.set_theme', 'auth.login')):
            return
        user = get_current_user()
        if user and getattr(user, 'must_change_password', False):
            flash('You must change your default/temporary password before continuing.', 'warning')
            return redirect(url_for('auth.profile'))

    # Register blueprints
    from app.blueprints.auth import auth_bp
    from app.blueprints.main import main_bp
    from app.blueprints.patients import patients_bp
    from app.blueprints.donors import donors_bp
    from app.blueprints.hospitals import hospitals_bp
    from app.blueprints.inventory import inventory_bp
    from app.blueprints.requests import requests_bp
    from app.blueprints.transfusions import transfusions_bp
    from app.blueprints.care import care_bp
    from app.blueprints.campaigns import campaigns_bp
    from app.blueprints.admin import admin_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp, url_prefix='')
    app.register_blueprint(patients_bp, url_prefix='/patients')
    app.register_blueprint(donors_bp, url_prefix='/donors')
    app.register_blueprint(hospitals_bp, url_prefix='/hospitals')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(requests_bp, url_prefix='/requests')
    app.register_blueprint(transfusions_bp, url_prefix='/transfusions')
    app.register_blueprint(care_bp, url_prefix='/care')
    app.register_blueprint(campaigns_bp, url_prefix='/campaigns')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Register error handlers
    @app.errorhandler(403)
    def forbidden(error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def page_not_found(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    # Context processors
    @app.template_filter('reject_key')
    def reject_key_filter(d, key_to_remove):
        if not d:
            return {}
        return {k: v for k, v in d.items() if k != key_to_remove}

    @app.context_processor
    def inject_global_data():
        from app.utils import get_current_user
        from app.models.care import Notification
        
        user = get_current_user()
        unread_count = 0
        if user:
            try:
                unread_count = Notification.active_query().filter_by(
                    user_id=user.id,
                    is_read=False
                ).count()
            except Exception:
                unread_count = 0

        theme = request.cookies.get('theme', 'light')
        return {
            'current_user': user,
            'current_theme': theme,
            'unread_notifications_count': unread_count,
            'current_year': datetime.utcnow().year,
            'app_name': 'LifeBridge'
        }

    return app
