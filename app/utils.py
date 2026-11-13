import re
import json
from datetime import datetime, date, timedelta
from functools import wraps
from flask import session, redirect, url_for, flash, request, abort, g, has_request_context
from app.extensions import db


def get_current_user():
    """Returns the currently logged in User model instance or None."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    from app.models.auth import User
    user = User.active_query().filter_by(id=user_id).first()
    if not user or not user.is_active_account:
        session.clear()
        return None
    return user


def login_required(view_func):
    """Decorator ensuring the user is authenticated via session."""
    @wraps(view_func)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        return view_func(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    """Decorator ensuring current user has one of the specified roles."""
    def decorator(view_func):
        @wraps(view_func)
        def decorated_function(*args, **kwargs):
            if not session.get('user_id'):
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login', next=request.url))
            
            user = get_current_user()
            if not user or not user.role:
                abort(403)
            
            user_role = user.role.slug.lower()
            allowed = [r.lower() for r in allowed_roles]
            # Admin always bypasses role checks; otherwise role must be explicitly allowed
            if user.is_admin or user_role in allowed:
                return view_func(*args, **kwargs)
            abort(403)
        return decorated_function
    return decorator


def is_safe_url(target):
    """Checks that target URL is a safe internal relative redirect path or same-origin URL."""
    if not target:
        return False
    from urllib.parse import urlsplit
    from flask import has_request_context
    if target.startswith('//') or target.startswith('/\\') or target.startswith('\\'):
        return False
    if target.startswith('/'):
        return True
    if has_request_context():
        try:
            target_parts = urlsplit(target)
            req_parts = urlsplit(request.base_url)
            if target_parts.netloc and target_parts.netloc == req_parts.netloc:
                return True
        except Exception:
            return False
    return False


def is_login_rate_limited(username_or_email, ip_address):
    """Checks if there have been >= 5 failed login attempts for this username/email or IP in the last 15 minutes."""
    from app.models.auth import LoginLog, User
    fifteen_mins_ago = datetime.utcnow() - timedelta(minutes=15)
    
    # Check by IP
    if ip_address:
        failed_ip_count = LoginLog.query.filter(
            LoginLog.ip_address == ip_address,
            LoginLog.login_status == 'FAILED',
            LoginLog.created_at >= fifteen_mins_ago
        ).count()
        if failed_ip_count >= 5:
            return True
            
    # Check by user
    if username_or_email:
        user = User.active_query().filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()
        if user:
            failed_user_count = LoginLog.query.filter(
                LoginLog.user_id == user.id,
                LoginLog.login_status == 'FAILED',
                LoginLog.created_at >= fifteen_mins_ago
            ).count()
            if failed_user_count >= 5:
                return True
    return False


def log_login(user_id, ip_address, user_agent, status, failure_reason=None):
    """Records authentication attempts in login_logs."""
    from app.models.auth import LoginLog
    try:
        log = LoginLog(
            user_id=user_id,
            ip_address=ip_address,
            user_agent=(user_agent or '')[:250],
            login_status=status,
            failure_reason=failure_reason
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()


def log_audit(user_id, action, table_name, record_id=None, old_values=None, new_values=None, ip_address=None):
    """Audit trails all significant database mutations."""
    from app.models.auth import AuditLog
    from flask import has_request_context
    try:
        req_ip = None
        if has_request_context():
            req_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            if req_ip and ',' in req_ip:
                req_ip = req_ip.split(',')[0].strip()
        log = AuditLog(
            user_id=user_id,
            action=action,
            table_name=table_name,
            record_id=record_id,
            old_values=json.dumps(old_values) if isinstance(old_values, dict) else (str(old_values) if old_values else None),
            new_values=json.dumps(new_values) if isinstance(new_values, dict) else (str(new_values) if new_values else None),
            ip_address=ip_address or req_ip,
            created_by=user_id
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()


def create_notification(user_id, title, message, notification_type='System', link_url=None, commit=True):
    """Creates a notification record for a specific user."""
    from app.models.care import Notification
    try:
        notif = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            link_url=link_url,
            is_read=False
        )
        db.session.add(notif)
        if commit:
            db.session.commit()
        return notif
    except Exception:
        if commit:
            db.session.rollback()
        return None


def validate_email_format(email):
    """Validate RFC-compliant email string."""
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return bool(re.match(pattern, email or ''))


def validate_phone(phone):
    """Validate phone format (Pakistani mobile/landline: 03XX-XXXXXXX, +923XXXXXXXXX, 0XX-XXXXXXX)."""
    if not phone:
        return False
    clean = re.sub(r'[\s\-()]', '', phone)
    if clean.startswith('+92'):
        clean = '0' + clean[3:]
    elif clean.startswith('92') and len(clean) == 12:
        clean = '0' + clean[2:]
    
    # Must be 10 or 11 digits and numeric starting with 0
    return bool(clean.isdigit() and len(clean) in (10, 11) and clean.startswith('0'))


def validate_cnic(cnic):
    """Validate 13-digit National ID (XXXXX-XXXXXXX-X or 13 contiguous digits)."""
    if not cnic:
        return True  # Optional unless required
    pattern = r'^\d{5}-?\d{7}-?\d{1}$'
    if not re.match(pattern, cnic):
        return False
    clean = re.sub(r'[\s\-]', '', cnic)
    # Reject dummy identical digits (e.g. 0000000000000 or 1111111111111)
    if len(set(clean)) == 1:
        return False
    return True


def validate_donor_screening(weight_kg, systolic_bp, diastolic_bp, pulse_bpm, hemoglobin_level):
    """
    Validates clinical health screening rules for safe blood donation:
    - Weight >= 50 kg
    - Systolic BP: 90 - 180 mmHg
    - Diastolic BP: 50 - 100 mmHg
    - Pulse: 50 - 100 bpm
    - Hemoglobin >= 12.5 g/dL
    """
    errors = []
    if (weight_kg or 0) < 50.0:
        errors.append("Donor weight must be at least 50 kg.")
    if not (90 <= (systolic_bp or 0) <= 180):
        errors.append("Systolic blood pressure must be between 90 and 180 mmHg.")
    if not (50 <= (diastolic_bp or 0) <= 100):
        errors.append("Diastolic blood pressure must be between 50 and 100 mmHg.")
    if not (50 <= (pulse_bpm or 0) <= 100):
        errors.append("Pulse rate must be between 50 and 100 bpm.")
    if (hemoglobin_level or 0) < 12.5:
        errors.append("Hemoglobin must be at least 12.5 g/dL for safe blood donation.")
    return errors


# Core Services Integration
from app.services.matching_service import find_and_match_donors, expire_emergency_broadcasts
from app.services.inventory_service import check_and_expire_units, sync_blood_bank_stock, generate_unit_number
from app.services.transfusion_service import validate_transfusion_execution, get_compatible_blood_group_ids
from app.services.donation_service import check_and_award_donor_badges, validate_donor_eligibility
