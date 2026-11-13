from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, make_response, current_app
from app.extensions import db
from app.models.auth import User, Role
from app.models.geography import City
from app.utils import (
    get_current_user,
    login_required,
    log_login,
    log_audit,
    validate_email_format,
    validate_phone,
    validate_cnic,
    is_safe_url,
    is_login_rate_limited
)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        login_identifier = request.form.get('login_identifier', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))
        ip = request.remote_addr
        user_agent = request.headers.get('User-Agent', '')

        if not login_identifier or not password:
            flash('Please provide both username/email and password.', 'danger')
            return render_template('auth/login.html')

        # Login brute-force rate limit: 5 failed attempts in 15 mins
        if is_login_rate_limited(login_identifier, ip):
            flash('Too many failed login attempts. Please try again after 15 minutes.', 'danger')
            return render_template('auth/login.html'), 429

        # Find user by username or email
        user = User.active_query().filter(
            (User.username == login_identifier) | (User.email == login_identifier.lower())
        ).first()

        if not user or not user.check_password(password):
            log_login(user.id if user else None, ip, user_agent, 'FAILED', 'Invalid credentials')
            flash('Invalid username/email or password.', 'danger')
            return render_template('auth/login.html')

        if not user.is_active_account:
            log_login(user.id, ip, user_agent, 'FAILED', 'Account disabled')
            flash('Your account has been deactivated. Please contact an administrator.', 'warning')
            return render_template('auth/login.html')

        # Successful login
        user.last_login_at = datetime.utcnow()
        db.session.commit()

        session.clear()
        session['user_id'] = user.id
        session['user_role'] = user.role.slug if user.role else 'user'
        session['user_name'] = user.full_name
        session.permanent = remember

        log_login(user.id, ip, user_agent, 'SUCCESS')
        flash(f'Welcome back, {user.full_name}!', 'success')

        next_page = request.args.get('next')
        if next_page and is_safe_url(next_page):
            return redirect(next_page)
        return redirect(url_for('main.dashboard'))

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('main.dashboard'))

    # Public registration is strictly restricted to donor and patient
    roles = Role.active_query().filter(Role.slug.in_(['donor', 'patient'])).all()
    cities = City.active_query().order_by(City.name).all()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        cnic = request.form.get('cnic', '').strip()
        role_id = request.form.get('role_id', type=int)
        city_id = request.form.get('city_id', type=int)
        address = request.form.get('address', '').strip()

        errors = []
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters long.')
        if not validate_email_format(email):
            errors.append('Please provide a valid email address.')
        if len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            errors.append('Password must be at least 8 characters long and contain both letters and numbers.')
        if password != confirm_password:
            errors.append('Passwords do not match.')
        if not full_name:
            errors.append('Full name is required.')
        if not validate_phone(phone):
            errors.append('Please provide a valid phone number (minimum 10 digits).')
        if cnic and not validate_cnic(cnic):
            errors.append('CNIC format is invalid (expected 13 digits or XXXXX-XXXXXXX-X).')

        allowed_role_ids = [r.id for r in roles]
        if not role_id or role_id not in allowed_role_ids:
            errors.append('Invalid account type selected. Only donor and patient accounts may self-register.')

        # Uniqueness checks
        if User.query.filter_by(username=username).first():
            errors.append('Username is already taken.')
        if User.query.filter_by(email=email).first():
            errors.append('Email is already registered.')
        if cnic and User.query.filter_by(cnic=cnic).first():
            errors.append('CNIC is already registered.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('auth/register.html', roles=roles, cities=cities)

        try:
            new_user = User(
                username=username,
                email=email,
                full_name=full_name,
                phone=phone,
                cnic=cnic or None,
                role_id=role_id,
                city_id=city_id or None,
                address=address or None,
                is_active_account=True,
                status='active'
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()

            log_audit(new_user.id, 'CREATE', 'users', new_user.id, None, {'username': username, 'role_id': role_id})
            flash('Registration successful! Please sign in with your credentials.', 'success')
            return redirect(url_for('auth.login'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Registration database error')
            flash('An error occurred during registration. Please try again.', 'danger')

    return render_template('auth/register.html', roles=roles, cities=cities)


@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    # If GET, gracefully redirect; if POST, execute logout
    if request.method == 'POST':
        user = get_current_user()
        if user:
            log_audit(user.id, 'LOGOUT', 'users', user.id)
        session.clear()
        flash('You have been logged out successfully.', 'info')
        return redirect(url_for('auth.login'))
    # Direct GET fallback
    user = get_current_user()
    if user:
        log_audit(user.id, 'LOGOUT', 'users', user.id)
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = get_current_user()
    cities = City.active_query().order_by(City.name).all()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        cnic = request.form.get('cnic', '').strip()
        city_id = request.form.get('city_id', type=int)
        address = request.form.get('address', '').strip()
        new_password = request.form.get('new_password', '')

        errors = []
        if not full_name:
            errors.append('Full name is required.')
        if not validate_phone(phone):
            errors.append('Invalid phone number.')
        if cnic and not validate_cnic(cnic):
            errors.append('Invalid CNIC format.')
        if new_password:
            if len(new_password) < 8 or not any(c.isalpha() for c in new_password) or not any(c.isdigit() for c in new_password):
                errors.append('New password must be at least 8 characters long and contain letters and numbers.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('auth/profile.html', user=user, cities=cities)

        old_data = {'full_name': user.full_name, 'phone': user.phone, 'city_id': user.city_id}
        user.full_name = full_name
        user.phone = phone
        user.cnic = cnic or None
        user.city_id = city_id or None
        user.address = address or None
        if new_password:
            user.set_password(new_password)
            user.must_change_password = False

        try:
            db.session.commit()
            log_audit(user.id, 'UPDATE', 'users', user.id, old_data, {'full_name': full_name, 'phone': phone})
            flash('Your profile has been updated.', 'success')
            return redirect(url_for('auth.profile'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Profile update failed')
            flash('Could not update profile. Please try again.', 'danger')

    return render_template('auth/profile.html', user=user, cities=cities)


@auth_bp.route('/set-theme', methods=['POST'])
def set_theme():
    """Toggles theme cookie between 'light' and 'dark'."""
    theme = request.form.get('theme', 'light')
    if theme not in ('light', 'dark'):
        theme = 'light'
    
    redirect_to = request.referrer
    if not redirect_to or not is_safe_url(redirect_to):
        redirect_to = url_for('main.dashboard')
    
    response = make_response(redirect(redirect_to))
    response.set_cookie('theme', theme, max_age=30*24*60*60, samesite='Lax')
    return response
