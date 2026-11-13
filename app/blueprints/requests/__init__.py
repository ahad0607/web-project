from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from sqlalchemy.orm import joinedload
from sqlalchemy import case
from app.extensions import db
from app.models import (
    BloodRequest,
    RequestStatusLog,
    EmergencyRequest,
    DonorMatch,
    Patient,
    Hospital,
    BloodGroup
)
from app.utils import (
    get_current_user,
    login_required,
    role_required,
    log_audit,
    find_and_match_donors,
    create_notification,
    expire_emergency_broadcasts
)

requests_bp = Blueprint('requests', __name__)


@requests_bp.route('/')
@login_required
def index():
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    urgency = request.args.get('urgency', '').strip()
    status = request.args.get('status', '').strip()
    blood_group_id = request.args.get('blood_group_id', type=int)

    query = BloodRequest.active_query().options(
        joinedload(BloodRequest.patient),
        joinedload(BloodRequest.hospital),
        joinedload(BloodRequest.blood_group)
    )

    # Ownership scoping
    if user.is_patient and user.patient_profile:
        query = query.filter(BloodRequest.patient_id == user.patient_profile.id)
    elif user.is_doctor and user.doctor_profile:
        doc = user.doctor_profile
        query = query.filter(
            (BloodRequest.patient.has(Patient.primary_doctor_id == doc.id)) |
            (BloodRequest.hospital_id == doc.hospital_id)
        )
    elif user.is_donor:
        # Donors only see requests that were broadcast as emergency or where they are matched
        query = query.filter(BloodRequest.urgency == 'Emergency')

    if urgency:
        query = query.filter(BloodRequest.urgency == urgency)
    if status:
        query = query.filter(BloodRequest.status == status)
    if blood_group_id:
        query = query.filter(BloodRequest.blood_group_id == blood_group_id)

    urgency_order = case(
        (BloodRequest.urgency == 'Emergency', 1),
        (BloodRequest.urgency == 'Urgent', 2),
        (BloodRequest.urgency == 'Normal', 3),
        else_=4
    )

    pagination = query.order_by(
        urgency_order.asc(),
        BloodRequest.created_at.desc()
    ).paginate(page=page, per_page=10, error_out=False)

    blood_groups = BloodGroup.active_query().order_by(BloodGroup.name).all()

    return render_template(
        'requests/index.html',
        pagination=pagination,
        requests=pagination.items,
        selected_urgency=urgency,
        selected_status=status,
        selected_bg=blood_group_id,
        blood_groups=blood_groups
    )


@requests_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    user = get_current_user()
    if user.is_donor:
        abort(403)

    hospitals = Hospital.active_query().order_by(Hospital.name).all()
    blood_groups = BloodGroup.active_query().order_by(BloodGroup.name).all()
    
    # Scope patient options
    if user.is_patient and user.patient_profile:
        patients = [user.patient_profile]
    elif user.is_doctor and user.doctor_profile:
        patients = Patient.active_query().filter_by(primary_doctor_id=user.doctor_profile.id).all()
    else:
        patients = Patient.active_query().all()

    if request.method == 'POST':
        patient_id = request.form.get('patient_id', type=int)
        hospital_id = request.form.get('hospital_id', type=int)
        blood_group_id = request.form.get('blood_group_id', type=int)
        component_type = request.form.get('component_type', 'PRBC')
        units_requested = request.form.get('units_requested', 1, type=int)
        urgency = request.form.get('urgency', 'Normal')
        needed_by_str = request.form.get('needed_by_date', '')
        reason = request.form.get('reason', '').strip()

        # Patient can only create for self and cannot trigger emergency
        if user.is_patient and user.patient_profile:
            patient_id = user.patient_profile.id
            if urgency == 'Emergency':
                urgency = 'Urgent'
                flash('Emergency SOS requests require hospital or doctor authorization. Urgency set to Urgent.', 'info')

        if urgency not in ('Normal', 'Urgent', 'Emergency'):
            urgency = 'Normal'

        if not hospital_id or not blood_group_id or not units_requested:
            flash('Hospital, blood group, and units are required.', 'danger')
            return render_template('requests/create.html', hospitals=hospitals, blood_groups=blood_groups, patients=patients)

        if not (1 <= units_requested <= 20):
            flash('Units requested must be between 1 and 20.', 'danger')
            return render_template('requests/create.html', hospitals=hospitals, blood_groups=blood_groups, patients=patients)

        hospital = Hospital.get_by_id(hospital_id)
        if not hospital:
            flash('Selected hospital does not exist.', 'danger')
            return render_template('requests/create.html', hospitals=hospitals, blood_groups=blood_groups, patients=patients)

        bg = BloodGroup.get_by_id(blood_group_id)
        if not bg:
            flash('Selected blood group does not exist.', 'danger')
            return render_template('requests/create.html', hospitals=hospitals, blood_groups=blood_groups, patients=patients)

        if patient_id and not Patient.get_by_id(patient_id):
            flash('Selected patient does not exist.', 'danger')
            return render_template('requests/create.html', hospitals=hospitals, blood_groups=blood_groups, patients=patients)

        try:
            today = date.today()
            needed_by = datetime.strptime(needed_by_str, '%Y-%m-%d').date() if needed_by_str else today
            if needed_by < today:
                flash('Needed-by date cannot be in the past.', 'danger')
                return render_template('requests/create.html', hospitals=hospitals, blood_groups=blood_groups, patients=patients)

            blood_req = BloodRequest(
                patient_id=patient_id or None,
                hospital_id=hospital_id,
                blood_group_id=blood_group_id,
                component_type=component_type,
                units_requested=units_requested,
                units_fulfilled=0,
                urgency=urgency,
                needed_by_date=needed_by,
                reason=reason or 'Blood Request',
                status='Pending',
                created_by=user.id
            )
            db.session.add(blood_req)
            db.session.flush()

            # Record initial status log
            status_log = RequestStatusLog(
                request_id=blood_req.id,
                previous_status='None',
                new_status='Pending',
                changed_by_user_id=user.id,
                notes='Initial blood request submission'
            )
            db.session.add(status_log)

            # If marked Emergency, auto-create EmergencyRequest & match donors!
            if urgency == 'Emergency':
                emergency = EmergencyRequest(
                    request_id=blood_req.id,
                    patient_id=patient_id or None,
                    hospital_id=hospital_id,
                    blood_group_id=blood_group_id,
                    units_needed=units_requested,
                    severity_level='Critical',
                    broadcast_radius_km=30,
                    is_broadcast_active=True,
                    broadcast_time=datetime.utcnow(),
                    created_by=user.id
                )
                db.session.add(emergency)
                db.session.flush()

                # Trigger algorithmic matching
                matches_count = find_and_match_donors(emergency)
                flash(f'🚨 Emergency SOS broadcast active! Found and notified {matches_count} matching donors.', 'warning')

            db.session.commit()
            log_audit(user.id, 'CREATE', 'blood_requests', blood_req.id, None, {'urgency': urgency, 'units': units_requested})
            flash('Blood request submitted successfully.', 'success')
            return redirect(url_for('requests.view', id=blood_req.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Request creation failed')
            flash('An error occurred while submitting the blood request. Please check inputs and try again.', 'danger')

    return render_template('requests/create.html', hospitals=hospitals, blood_groups=blood_groups, patients=patients)


@requests_bp.route('/<int:id>')
@login_required
def view(id):
    blood_req = BloodRequest.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()

    # Scope permissions
    if user.is_patient and user.patient_profile:
        if blood_req.patient_id and blood_req.patient_id != user.patient_profile.id:
            abort(403)
    elif user.is_doctor and user.doctor_profile:
        doc = user.doctor_profile
        is_assigned_patient = blood_req.patient and blood_req.patient.primary_doctor_id == doc.id
        is_hospital_match = blood_req.hospital_id == doc.hospital_id
        if not (is_assigned_patient or is_hospital_match):
            abort(403)
    elif user.is_donor:
        if blood_req.urgency != 'Emergency':
            abort(403)

    status_logs = RequestStatusLog.active_query().filter_by(request_id=blood_req.id).order_by(RequestStatusLog.created_at.desc()).all()
    emergency = EmergencyRequest.active_query().filter_by(request_id=blood_req.id).first()
    matches = emergency.donor_matches if emergency else []

    return render_template(
        'requests/view.html',
        request_obj=blood_req,
        status_logs=status_logs,
        emergency=emergency,
        matches=matches
    )


@requests_bp.route('/<int:id>/status', methods=['POST'])
@login_required
@role_required('admin', 'hospital_staff', 'doctor')
def update_status(id):
    blood_req = BloodRequest.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()

    # Hospital staff can only update requests for their assigned hospital
    if user.is_hospital_staff and user.hospital_id and blood_req.hospital_id != user.hospital_id:
        abort(403)

    new_status = request.form.get('status')
    units_fulfilled = request.form.get('units_fulfilled', type=int)
    notes = request.form.get('notes', 'Status updated by medical staff')

    old_status = blood_req.status

    ALLOWED_TRANSITIONS = {
        'Pending': ['Approved', 'Cancelled'],
        'Approved': ['In Progress', 'Cancelled'],
        'In Progress': ['Fulfilled', 'Partially Fulfilled', 'Cancelled'],
        'Partially Fulfilled': ['In Progress', 'Fulfilled', 'Cancelled'],
        'Fulfilled': [],
        'Cancelled': []
    }

    if new_status != old_status:
        allowed_next = ALLOWED_TRANSITIONS.get(old_status, [])
        if new_status not in allowed_next and not user.is_admin:
            flash(f"Invalid status transition from '{old_status}' to '{new_status}'. Allowed transitions: {', '.join(allowed_next) if allowed_next else 'None (Terminal state)'}.", 'danger')
            return redirect(url_for('requests.view', id=blood_req.id))

    if units_fulfilled is not None:
        if not (0 <= units_fulfilled <= blood_req.units_requested):
            flash(f"Units fulfilled must be between 0 and requested units ({blood_req.units_requested}).", 'danger')
            return redirect(url_for('requests.view', id=blood_req.id))
        blood_req.units_fulfilled = units_fulfilled
        if units_fulfilled == blood_req.units_requested and new_status != 'Cancelled':
            new_status = 'Fulfilled'
        elif 0 < units_fulfilled < blood_req.units_requested and new_status not in ('In Progress', 'Cancelled'):
            new_status = 'Partially Fulfilled'
    elif new_status == 'Fulfilled' and blood_req.units_fulfilled < blood_req.units_requested:
        blood_req.units_fulfilled = blood_req.units_requested

    blood_req.status = new_status

    blood_req.updated_by = user.id

    # If fulfilled or cancelled, close active emergency broadcast
    if new_status in ('Fulfilled', 'Cancelled') and blood_req.emergency_request:
        blood_req.emergency_request.is_broadcast_active = False
        blood_req.emergency_request.status = new_status

    status_log = RequestStatusLog(
        request_id=blood_req.id,
        previous_status=old_status,
        new_status=new_status,
        changed_by_user_id=user.id,
        notes=notes,
        created_by=user.id
    )
    db.session.add(status_log)

    try:
        db.session.commit()
        log_audit(user.id, 'STATUS_UPDATE', 'blood_requests', blood_req.id, {'status': old_status}, {'status': new_status})
        flash(f'Request #{blood_req.id} updated to {new_status}.', 'success')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Status update failed')
        flash('Status update failed. Please try again.', 'danger')

    return redirect(url_for('requests.view', id=blood_req.id))


@requests_bp.route('/<int:id>/emergency', methods=['POST'])
@login_required
@role_required('admin', 'hospital_staff', 'doctor')
def trigger_emergency(id):
    blood_req = BloodRequest.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()

    # Hospital staff can only trigger emergency for their assigned hospital
    if user.is_hospital_staff and user.hospital_id and blood_req.hospital_id != user.hospital_id:
        abort(403)

    if not blood_req.emergency_request:
        emergency = EmergencyRequest(
            request_id=blood_req.id,
            patient_id=blood_req.patient_id,
            hospital_id=blood_req.hospital_id,
            blood_group_id=blood_req.blood_group_id,
            units_needed=blood_req.units_requested - blood_req.units_fulfilled,
            severity_level='Life-Threatening',
            broadcast_radius_km=30,
            is_broadcast_active=True,
            broadcast_time=datetime.utcnow(),
            created_by=user.id
        )
        db.session.add(emergency)
        db.session.flush()
    else:
        emergency = blood_req.emergency_request
        emergency.is_broadcast_active = True
        emergency.broadcast_time = datetime.utcnow()

    blood_req.urgency = 'Emergency'
    matches_count = find_and_match_donors(emergency)

    try:
        db.session.commit()
        log_audit(user.id, 'EMERGENCY_BROADCAST', 'emergency_requests', emergency.id)
        flash(f'🚨 Emergency Broadcast sent! Notified {matches_count} matching donors.', 'warning')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Emergency broadcast failed')
        flash('Failed to broadcast emergency. Please try again.', 'danger')

    return redirect(url_for('requests.view', id=blood_req.id))


@requests_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete(id):
    blood_req = BloodRequest.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()
    blood_req.soft_delete(user.id)
    try:
        db.session.commit()
        log_audit(user.id, 'SOFT_DELETE', 'blood_requests', blood_req.id)
        flash('Blood request soft-deleted.', 'warning')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Delete request failed')
        flash('Failed to delete request.', 'danger')

    return redirect(url_for('requests.index'))


@requests_bp.route('/emergency/active')
@login_required
def emergency_active():
    expire_emergency_broadcasts()
    emergencies = EmergencyRequest.active_query().filter_by(is_broadcast_active=True).options(
        joinedload(EmergencyRequest.blood_request),
        joinedload(EmergencyRequest.hospital),
        joinedload(EmergencyRequest.blood_group),
        joinedload(EmergencyRequest.patient)
    ).order_by(EmergencyRequest.broadcast_time.desc()).all()

    return render_template('requests/emergency_active.html', emergencies=emergencies)
