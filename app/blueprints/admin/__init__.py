from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models import (
    User,
    Role,
    Permission,
    RolePermission,
    LoginLog,
    AuditLog,
    City,
    Area,
    BloodGroup,
    Diagnosis,
    Feedback,
    Patient,
    Donor,
    Hospital,
    BloodUnit,
    BloodRequest
)
from app.utils import get_current_user, login_required, role_required, log_audit, validate_email_format, validate_phone

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/')
@login_required
@role_required('admin')
def index():
    stats = {
        'users_count': User.active_query().count(),
        'patients_count': Patient.active_query().count(),
        'donors_count': Donor.active_query().count(),
        'hospitals_count': Hospital.active_query().count(),
        'units_count': BloodUnit.active_query().count(),
        'requests_count': BloodRequest.active_query().count(),
    }
    recent_audits = AuditLog.active_query().options(joinedload(AuditLog.user)).order_by(AuditLog.created_at.desc()).limit(10).all()
    recent_logins = LoginLog.active_query().options(joinedload(LoginLog.user)).order_by(LoginLog.created_at.desc()).limit(10).all()

    return render_template('admin/dashboard.html', stats=stats, recent_audits=recent_audits, recent_logins=recent_logins)


# ===================== USER MANAGEMENT =====================
@admin_bp.route('/users')
@login_required
@role_required('admin')
def users():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    role_id = request.args.get('role_id', type=int)

    query = User.active_query().options(joinedload(User.role), joinedload(User.city))

    if search:
        query = query.filter(
            (User.username.ilike(f"%{search}%")) |
            (User.email.ilike(f"%{search}%")) |
            (User.full_name.ilike(f"%{search}%"))
        )
    if role_id:
        query = query.filter(User.role_id == role_id)

    pagination = query.order_by(User.id.asc()).paginate(page=page, per_page=12, error_out=False)
    roles = Role.active_query().all()

    return render_template('admin/users.html', pagination=pagination, users=pagination.items, roles=roles, search=search, selected_role=role_id)


@admin_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def create_user():
    roles = Role.active_query().all()
    cities = City.active_query().all()
    hospitals = Hospital.active_query().all()

    if request.method == 'POST':
        admin_user = get_current_user()
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        role_id = request.form.get('role_id', type=int)
        city_id = request.form.get('city_id', type=int)
        hospital_id = request.form.get('hospital_id', type=int)

        errors = []
        if not username or not email or not password or not full_name or not role_id:
            errors.append('Username, email, password, full name, and role are required.')

        role = Role.get_by_id(role_id)
        if not role:
            errors.append('Selected role does not exist.')

        if email and not validate_email_format(email):
            errors.append('Please provide a valid email address.')

        if phone and not validate_phone(phone):
            errors.append('Please provide a valid Pakistani phone number.')

        if not password or len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            errors.append('Password must be at least 8 characters long and contain both letters and digits.')

        if User.query.filter((User.username == username) | (User.email == email)).first():
            errors.append('Username or email already in use.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('admin/create_user.html', roles=roles, cities=cities, hospitals=hospitals)

        try:
            new_u = User(
                username=username,
                email=email,
                full_name=full_name,
                phone=phone,
                role_id=role_id,
                city_id=city_id or None,
                hospital_id=hospital_id or None,
                created_by=admin_user.id
            )
            new_u.set_password(password)
            db.session.add(new_u)
            db.session.commit()
            log_audit(admin_user.id, 'CREATE', 'users', new_u.id, None, {'username': username, 'role_id': role_id})
            flash(f'User account {username} created.', 'success')
            return redirect(url_for('admin.users'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error creating user')
            flash('Error creating user. Please verify user inputs and try again.', 'danger')

    return render_template('admin/create_user.html', roles=roles, cities=cities, hospitals=hospitals)


@admin_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit_user(id):
    target_user = User.active_query().filter_by(id=id).first_or_404()
    admin_user = get_current_user()
    roles = Role.active_query().all()
    cities = City.active_query().all()
    hospitals = Hospital.active_query().all()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        role_id = request.form.get('role_id', type=int)
        city_id = request.form.get('city_id', type=int)
        hospital_id = request.form.get('hospital_id', type=int)

        errors = []
        if not full_name or not email or not role_id:
            errors.append('Full name, email, and role are required.')

        role = Role.get_by_id(role_id)
        if not role:
            errors.append('Selected role does not exist.')

        if email and not validate_email_format(email):
            errors.append('Please provide a valid email address.')

        if phone and not validate_phone(phone):
            errors.append('Please provide a valid Pakistani phone number.')

        existing = User.query.filter(User.email == email, User.id != target_user.id).first()
        if existing:
            errors.append('Email is already registered by another user.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('admin/edit_user.html', user=target_user, roles=roles, cities=cities, hospitals=hospitals)

        old_data = {
            'full_name': target_user.full_name,
            'role_id': target_user.role_id,
            'city_id': target_user.city_id,
            'hospital_id': target_user.hospital_id
        }

        target_user.full_name = full_name
        target_user.email = email
        target_user.phone = phone
        target_user.role_id = role_id
        target_user.city_id = city_id or None
        target_user.hospital_id = hospital_id or None
        target_user.updated_by = admin_user.id

        try:
            db.session.commit()
            log_audit(admin_user.id, 'UPDATE', 'users', target_user.id, old_data, {
                'full_name': full_name,
                'role_id': role_id,
                'city_id': city_id,
                'hospital_id': hospital_id
            })
            flash(f'User account @{target_user.username} updated successfully.', 'success')
            return redirect(url_for('admin.users'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error editing user')
            flash('Error updating user account.', 'danger')

    return render_template('admin/edit_user.html', user=target_user, roles=roles, cities=cities, hospitals=hospitals)


@admin_bp.route('/users/<int:id>/reset-password', methods=['POST'])
@login_required
@role_required('admin')
def reset_password(id):
    target_user = User.active_query().filter_by(id=id).first_or_404()
    admin_user = get_current_user()

    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    temp_pass = ''.join(secrets.choice(alphabet) for _ in range(10))

    target_user.set_password(temp_pass)
    target_user.must_change_password = True
    target_user.updated_by = admin_user.id

    try:
        db.session.commit()
        log_audit(admin_user.id, 'RESET_PASSWORD', 'users', target_user.id)
        flash(f'Password for @{target_user.username} has been reset to temporary password: "{temp_pass}". The user will be required to change it upon login.', 'warning')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Reset password failed')
        flash('Failed to reset user password.', 'danger')

    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:id>/toggle-status', methods=['POST'])
@login_required
@role_required('admin')
def toggle_user_status(id):
    admin_user = get_current_user()
    target_user = User.active_query().filter_by(id=id).first_or_404()

    if target_user.id == admin_user.id:
        flash('You cannot deactivate your own account!', 'danger')
        return redirect(url_for('admin.users'))

    target_user.is_active_account = not target_user.is_active_account
    target_user.updated_by = admin_user.id

    try:
        db.session.commit()
        status_label = 'Activated' if target_user.is_active_account else 'Deactivated'
        log_audit(admin_user.id, 'STATUS_TOGGLE', 'users', target_user.id, None, {'is_active': target_user.is_active_account})
        flash(f'User {target_user.username} {status_label}.', 'info')
    except Exception:
        db.session.rollback()
        flash('Failed to change user status.', 'danger')

    return redirect(url_for('admin.users'))


# ===================== AUDIT & SECURITY LOGS =====================
@admin_bp.route('/audit-logs')
@login_required
@role_required('admin')
def audit_logs():
    page = request.args.get('page', 1, type=int)
    table_filter = request.args.get('table', '').strip()

    query = AuditLog.active_query().options(joinedload(AuditLog.user))
    if table_filter:
        query = query.filter(AuditLog.table_name == table_filter)

    pagination = query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/audit_logs.html', pagination=pagination, logs=pagination.items, table_filter=table_filter)


@admin_bp.route('/login-logs')
@login_required
@role_required('admin')
def login_logs():
    page = request.args.get('page', 1, type=int)
    pagination = LoginLog.active_query().options(joinedload(LoginLog.user)).order_by(LoginLog.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/login_logs.html', pagination=pagination, logs=pagination.items)


# ===================== REFERENCE DATA CRUD =====================
@admin_bp.route('/reference/cities', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def cities():
    admin_user = get_current_user()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        state = request.form.get('state_province', '').strip()
        postal = request.form.get('postal_code', '').strip()
        country = request.form.get('country', 'Pakistan').strip()

        if name:
            try:
                city = City(name=name, state_province=state, postal_code=postal, country=country, created_by=admin_user.id)
                db.session.add(city)
                db.session.commit()
                flash(f'City "{name}" added.', 'success')
            except Exception:
                db.session.rollback()
                current_app.logger.exception('Failed to add city')
                flash('Failed to add city. Name may already exist.', 'danger')

    cities_list = City.active_query().order_by(City.name).all()
    return render_template('admin/cities.html', cities=cities_list)


@admin_bp.route('/reference/areas', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def areas():
    admin_user = get_current_user()
    cities_list = City.active_query().order_by(City.name).all()

    if request.method == 'POST':
        city_id = request.form.get('city_id', type=int)
        name = request.form.get('name', '').strip()
        postal = request.form.get('postal_code', '').strip()

        if city_id and name:
            try:
                area = Area(city_id=city_id, name=name, postal_code=postal, created_by=admin_user.id)
                db.session.add(area)
                db.session.commit()
                flash(f'Area "{name}" added.', 'success')
            except Exception:
                db.session.rollback()
                current_app.logger.exception('Failed to add area')
                flash('Failed to add area.', 'danger')

    areas_list = Area.active_query().options(joinedload(Area.city)).order_by(Area.name).all()
    return render_template('admin/areas.html', areas=areas_list, cities=cities_list)


@admin_bp.route('/reference/blood-groups')
@login_required
@role_required('admin')
def blood_groups():
    groups = BloodGroup.active_query().order_by(BloodGroup.name).all()
    return render_template('admin/blood_groups.html', blood_groups=groups)


@admin_bp.route('/reference/diagnoses', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def diagnoses():
    admin_user = get_current_user()
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip()
        cat = request.form.get('category', 'Hemoglobinopathy')
        desc = request.form.get('description', '').strip()

        if code and name:
            try:
                diag = Diagnosis(code=code, name=name, category=cat, description=desc, created_by=admin_user.id)
                db.session.add(diag)
                db.session.commit()
                flash(f'Diagnosis "{name}" added.', 'success')
            except Exception:
                db.session.rollback()
                current_app.logger.exception('Failed to add diagnosis')
                flash('Failed to add diagnosis.', 'danger')

    diag_list = Diagnosis.active_query().order_by(Diagnosis.code).all()
    return render_template('admin/diagnoses.html', diagnoses=diag_list)


# ===================== FEEDBACK MODERATION =====================
@admin_bp.route('/feedback')
@login_required
@role_required('admin')
def feedback():
    feedbacks = Feedback.active_query().order_by(Feedback.created_at.desc()).all()
    return render_template('admin/feedback_moderation.html', feedbacks=feedbacks)


@admin_bp.route('/feedback/<int:id>/toggle-visibility', methods=['POST'])
@login_required
@role_required('admin')
def toggle_feedback_visibility(id):
    fb = Feedback.active_query().filter_by(id=id).first_or_404()
    fb.is_public = not fb.is_public
    db.session.commit()
    status_str = "public" if fb.is_public else "hidden"
    flash(f"Feedback #{fb.id} is now {status_str}.", 'info')
    return redirect(url_for('admin.feedback'))


@admin_bp.route('/feedback/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_feedback(id):
    admin_user = get_current_user()
    fb = Feedback.active_query().filter_by(id=id).first_or_404()
    fb.soft_delete(user_id=admin_user.id)
    db.session.commit()
    flash(f"Feedback #{fb.id} soft-deleted.", 'success')
    return redirect(url_for('admin.feedback'))


# ===================== ROLES & PERMISSIONS =====================
@admin_bp.route('/roles', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def roles():
    admin_user = get_current_user()
    if request.method == 'POST':
        role_id = request.form.get('role_id', type=int)
        permission_id = request.form.get('permission_id', type=int)

        if role_id and permission_id:
            existing = RolePermission.query.filter_by(role_id=role_id, permission_id=permission_id).first()
            if not existing:
                try:
                    rp = RolePermission(role_id=role_id, permission_id=permission_id, created_by=admin_user.id)
                    db.session.add(rp)
                    db.session.commit()
                    flash('Permission assigned to role.', 'success')
                except Exception:
                    db.session.rollback()
                    current_app.logger.exception('Assign permission failed')
                    flash('Failed to assign permission.', 'danger')
            else:
                flash('Permission already assigned to this role.', 'info')
        return redirect(url_for('admin.roles'))

    roles_list = Role.active_query().order_by(Role.name).all()
    all_permissions = Permission.active_query().order_by(Permission.module, Permission.name).all()
    return render_template('admin/roles.html', roles=roles_list, permissions=all_permissions)


@admin_bp.route('/permissions')
@login_required
@role_required('admin')
def permissions():
    all_perms = Permission.active_query().order_by(Permission.module, Permission.name).all()
    return render_template('admin/permissions.html', permissions=all_perms)


# ===================== RECYCLE BIN / RESTORE =====================
@admin_bp.route('/recycle-bin')
@login_required
@role_required('admin')
def recycle_bin():
    deleted_data = {
        'users': User.deleted_query().all(),
        'patients': Patient.deleted_query().all(),
        'donors': Donor.deleted_query().all(),
        'hospitals': Hospital.deleted_query().all(),
        'units': BloodUnit.deleted_query().all(),
        'requests': BloodRequest.deleted_query().all()
    }
    return render_template('admin/recycle_bin.html', deleted=deleted_data)


@admin_bp.route('/recycle-bin/restore/<string:entity_type>/<int:id>', methods=['POST'])
@login_required
@role_required('admin')
def restore_record(entity_type, id):
    admin_user = get_current_user()
    models_map = {
        'user': User,
        'patient': Patient,
        'donor': Donor,
        'hospital': Hospital,
        'unit': BloodUnit,
        'request': BloodRequest
    }
    model = models_map.get(entity_type.lower())
    if not model:
        abort(404)

    record = model.query.filter_by(id=id, is_deleted=True).first_or_404()
    record.restore(user_id=admin_user.id)
    try:
        db.session.commit()
        log_audit(admin_user.id, 'RESTORE', model.__tablename__, record.id)
        flash(f'Record #{record.id} in {model.__tablename__} restored successfully.', 'success')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Restore record failed')
        flash('Failed to restore record.', 'danger')

    return redirect(url_for('admin.recycle_bin'))
