from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models import (
    TransfusionSchedule,
    TransfusionRecord,
    BloodRequest,
    BloodUnit,
    InventoryTransaction,
    Patient,
    Hospital,
    HospitalBloodBank,
    Doctor,
    BloodGroup,
    HemoglobinRecord
)
from app.utils import get_current_user, login_required, role_required, log_audit, create_notification
from app.services.transfusion_service import validate_transfusion_execution, get_compatible_blood_group_ids

transfusions_bp = Blueprint('transfusions', __name__)


@transfusions_bp.route('/schedules')
@login_required
def schedules():
    user = get_current_user()
    if user.is_donor:
        abort(403)

    page = request.args.get('page', 1, type=int)
    patient_id = request.args.get('patient_id', type=int)
    status = request.args.get('status', '').strip()

    query = TransfusionSchedule.active_query().options(
        joinedload(TransfusionSchedule.patient),
        joinedload(TransfusionSchedule.hospital),
        joinedload(TransfusionSchedule.doctor),
        joinedload(TransfusionSchedule.blood_group)
    )

    if user.is_patient and user.patient_profile:
        query = query.filter(TransfusionSchedule.patient_id == user.patient_profile.id)
        patients = [user.patient_profile]
    elif user.is_doctor and user.doctor_profile:
        doc = user.doctor_profile
        query = query.filter(
            (TransfusionSchedule.doctor_id == doc.id) |
            (TransfusionSchedule.patient.has(Patient.primary_doctor_id == doc.id))
        )
        patients = Patient.active_query().filter_by(primary_doctor_id=doc.id).all()
    else:
        patients = Patient.active_query().all()

    if patient_id:
        query = query.filter(TransfusionSchedule.patient_id == patient_id)
    if status:
        query = query.filter(TransfusionSchedule.status == status)

    pagination = query.order_by(TransfusionSchedule.scheduled_date.asc()).paginate(page=page, per_page=10, error_out=False)

    return render_template(
        'transfusions/schedules.html',
        pagination=pagination,
        schedules=pagination.items,
        selected_patient=patient_id,
        selected_status=status,
        patients=patients
    )


@transfusions_bp.route('/schedules/create', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'doctor', 'hospital_staff')
def create_schedule():
    user = get_current_user()
    if user.is_doctor and user.doctor_profile:
        patients = Patient.active_query().filter_by(primary_doctor_id=user.doctor_profile.id).all()
    else:
        patients = Patient.active_query().all()

    hospitals = Hospital.active_query().all()
    doctors = Doctor.active_query().all()
    blood_groups = BloodGroup.active_query().all()

    if request.method == 'POST':
        patient_id = request.form.get('patient_id', type=int)
        hospital_id = request.form.get('hospital_id', type=int)
        doctor_id = request.form.get('doctor_id', type=int)
        sched_date_str = request.form.get('scheduled_date', '')
        target_hb = request.form.get('target_hemoglobin', 9.5, type=float)
        required_units = request.form.get('required_units', 1, type=int)
        notes = request.form.get('notes', '')
        auto_request_blood = bool(request.form.get('auto_request_blood'))

        if not patient or not hospital_id or not sched_date_str:
            flash('Patient, hospital, and scheduled date are required.', 'danger')
            return render_template('transfusions/create_schedule.html', patients=patients, hospitals=hospitals, doctors=doctors, blood_groups=blood_groups)

        if not (1 <= required_units <= 4):
            flash('Required units must be between 1 and 4.', 'danger')
            return render_template('transfusions/create_schedule.html', patients=patients, hospitals=hospitals, doctors=doctors, blood_groups=blood_groups)

        if not Hospital.get_by_id(hospital_id):
            flash('Selected hospital does not exist.', 'danger')
            return render_template('transfusions/create_schedule.html', patients=patients, hospitals=hospitals, doctors=doctors, blood_groups=blood_groups)

        if doctor_id and not Doctor.get_by_id(doctor_id):
            flash('Selected doctor does not exist.', 'danger')
            return render_template('transfusions/create_schedule.html', patients=patients, hospitals=hospitals, doctors=doctors, blood_groups=blood_groups)

        try:
            today = date.today()
            sched_date = datetime.strptime(sched_date_str, '%Y-%m-%d').date()
            if sched_date < today:
                flash('Scheduled date cannot be in the past.', 'danger')
                return render_template('transfusions/create_schedule.html', patients=patients, hospitals=hospitals, doctors=doctors, blood_groups=blood_groups)

            # Optional: auto-link a blood request
            linked_req = None
            if auto_request_blood:
                linked_req = BloodRequest(
                    patient_id=patient.id,
                    hospital_id=hospital_id,
                    blood_group_id=patient.blood_group_id,
                    component_type='PRBC',
                    units_requested=required_units,
                    units_fulfilled=0,
                    urgency='Normal',
                    needed_by_date=sched_date,
                    reason=f"Scheduled transfusion on {sched_date} for MRN {patient.mrn}",
                    status='Pending',
                    created_by=user.id
                )
                db.session.add(linked_req)
                db.session.flush()

            schedule = TransfusionSchedule(
                patient_id=patient.id,
                hospital_id=hospital_id,
                doctor_id=doctor_id or patient.primary_doctor_id,
                scheduled_date=sched_date,
                target_hemoglobin=target_hb,
                required_units=required_units,
                blood_group_id=patient.blood_group_id,
                linked_blood_request_id=linked_req.id if linked_req else None,
                status='Scheduled',
                notes=notes,
                created_by=user.id
            )
            db.session.add(schedule)
            db.session.commit()

            # Notify patient user
            if patient.user_id:
                create_notification(
                    user_id=patient.user_id,
                    title="Upcoming Transfusion Scheduled 🩸",
                    message=f"Your regular blood transfusion is booked for {sched_date.strftime('%B %d, %Y')}.",
                    notification_type="Schedule",
                    link_url=url_for('transfusions.schedules')
                )

            log_audit(user.id, 'CREATE', 'transfusion_schedules', schedule.id)
            flash(f"Transfusion scheduled for {patient.full_name} on {sched_date}.", 'success')
            return redirect(url_for('transfusions.schedules'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Create schedule failed')
            flash("Error creating schedule. Please check inputs and try again.", 'danger')

    return render_template('transfusions/create_schedule.html', patients=patients, hospitals=hospitals, doctors=doctors, blood_groups=blood_groups)


@transfusions_bp.route('/schedules/<int:id>/execute', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'doctor', 'hospital_staff')
def execute(id):
    schedule = TransfusionSchedule.active_query().filter_by(id=id).first_or_404()
    patient = schedule.patient
    today = date.today()

    # Enforce that schedule.status == 'Scheduled'
    if schedule.status != 'Scheduled':
        flash('This transfusion schedule has already been executed or cancelled.', 'warning')
        return redirect(url_for('transfusions.schedules'))

    # Compatible blood groups for patient via domain service
    compatible_groups = get_compatible_blood_group_ids(patient.blood_group_id)

    available_units = BloodUnit.active_query().join(HospitalBloodBank).filter(
        HospitalBloodBank.hospital_id == schedule.hospital_id,
        BloodUnit.blood_group_id.in_(compatible_groups if compatible_groups else [patient.blood_group_id]),
        BloodUnit.status == 'Available',
        BloodUnit.expiry_date >= today
    ).all()

    if request.method == 'POST':
        user = get_current_user()
        blood_unit_id = request.form.get('blood_unit_id', type=int)
        pre_hb = request.form.get('pre_transfusion_hb', type=float)
        post_hb = request.form.get('post_transfusion_hb', type=float)
        start_time = request.form.get('start_time', '10:00')
        end_time = request.form.get('end_time', '13:30')
        adverse_rx = bool(request.form.get('adverse_reaction_observed'))
        reaction_details = request.form.get('reaction_details', 'None')
        schedule_next = bool(request.form.get('schedule_next_transfusion'))

        blood_unit = BloodUnit.get_by_id(blood_unit_id)
        if not blood_unit or pre_hb is None or post_hb is None:
            flash('Please select an active blood unit and provide pre/post hemoglobin levels.', 'danger')
            return render_template('transfusions/execute.html', schedule=schedule, available_units=available_units)

        # Enforce clinical hemoglobin safety limits: 2.0 to 20.0 g/dL
        if not (2.0 <= pre_hb <= 20.0):
            flash('Pre-transfusion hemoglobin must be clinically valid (between 2.0 and 20.0 g/dL).', 'danger')
            return render_template('transfusions/execute.html', schedule=schedule, available_units=available_units)

        if not (2.0 <= post_hb <= 20.0):
            flash('Post-transfusion hemoglobin must be clinically valid (between 2.0 and 20.0 g/dL).', 'danger')
            return render_template('transfusions/execute.html', schedule=schedule, available_units=available_units)

        # Validate start and end time (HH:MM and end > start)
        try:
            t_start = datetime.strptime(start_time, '%H:%M').time()
            t_end = datetime.strptime(end_time, '%H:%M').time()
            if t_end <= t_start:
                flash('Transfusion end time must be later than start time.', 'danger')
                return render_template('transfusions/execute.html', schedule=schedule, available_units=available_units)
        except ValueError:
            flash('Invalid time format (expected HH:MM format).', 'danger')
            return render_template('transfusions/execute.html', schedule=schedule, available_units=available_units)

        # Enforce unit availability
        if blood_unit.status != 'Available':
            flash(f"Blood unit {blood_unit.unit_number} is not available (current status: {blood_unit.status}).", 'danger')
            return render_template('transfusions/execute.html', schedule=schedule, available_units=available_units)

        # Check unit not already linked to an existing transfusion
        if blood_unit.transfusion_record:
            flash(f"Blood unit {blood_unit.unit_number} has already been transfused.", 'danger')
            return render_template('transfusions/execute.html', schedule=schedule, available_units=available_units)

        # Check unit belongs to the schedule's hospital blood bank
        if blood_unit.blood_bank and blood_unit.blood_bank.hospital_id != schedule.hospital_id:
            flash(f"Blood unit {blood_unit.unit_number} belongs to a different hospital blood bank.", 'danger')
            return render_template('transfusions/execute.html', schedule=schedule, available_units=available_units)

        # Enforce unit expiry
        if blood_unit.expiry_date < today:
            blood_unit.status = 'Expired'
            db.session.commit()
            flash(f"Blood unit {blood_unit.unit_number} is expired (expired on {blood_unit.expiry_date}) and cannot be transfused.", 'danger')
            return render_template('transfusions/execute.html', schedule=schedule, available_units=available_units)

        # Enforce ABO/Rh compatibility
        if patient.blood_group and not patient.blood_group.is_compatible_recipient(blood_unit.blood_group.name):
            flash(f"Incompatible blood group! Patient is {patient.blood_group.name} but unit {blood_unit.unit_number} is {blood_unit.blood_group.name}.", 'danger')
            return render_template('transfusions/execute.html', schedule=schedule, available_units=available_units)

        try:
            today = date.today()
            # 1. Create clinical transfusion record
            record = TransfusionRecord(
                patient_id=patient.id,
                schedule_id=schedule.id,
                blood_unit_id=blood_unit.id,
                hospital_id=schedule.hospital_id,
                doctor_id=schedule.doctor_id,
                transfusion_date=today,
                start_time=start_time,
                end_time=end_time,
                pre_transfusion_hb=pre_hb,
                post_transfusion_hb=post_hb,
                adverse_reaction_observed=adverse_rx,
                reaction_details=reaction_details if adverse_rx else 'None reported',
                created_by=user.id
            )
            db.session.add(record)

            # 2. Mark unit as Transfused and record inventory transaction
            blood_unit.status = 'Transfused'
            blood_unit.updated_by = user.id
            if blood_unit.blood_bank:
                blood_unit.blood_bank.current_stock_units = max(0, blood_unit.blood_bank.current_stock_units - 1)

            tx = InventoryTransaction(
                blood_bank_id=blood_unit.blood_bank_id,
                blood_unit_id=blood_unit.id,
                transaction_type='OUT_TRANSFUSION',
                quantity=1,
                reason=f"Transfused into Patient {patient.mrn}",
                performed_by_user_id=user.id,
                created_by=user.id
            )
            db.session.add(tx)

            # 3. Add to patient hemoglobin tracking log
            hb_entry = HemoglobinRecord(
                patient_id=patient.id,
                test_date=today,
                hb_level=post_hb,
                lab_name="Transfusion Day Post-Hb",
                notes=f"Post-transfusion gain: +{round(post_hb - pre_hb, 2)} g/dL",
                recorded_by_user_id=user.id,
                created_by=user.id
            )
            db.session.add(hb_entry)

            # 4. Mark schedule as Completed
            schedule.status = 'Completed'
            schedule.updated_by = user.id

            # 5. Automatically calculate and schedule next transfusion if requested
            if schedule_next:
                future_exists = TransfusionSchedule.active_query().filter(
                    TransfusionSchedule.patient_id == patient.id,
                    TransfusionSchedule.status == 'Scheduled',
                    TransfusionSchedule.scheduled_date > today
                ).first()
                if not future_exists:
                    interval_days = patient.transfusion_interval_days or 21
                    next_date = today + timedelta(days=interval_days)
                    next_sched = TransfusionSchedule(
                        patient_id=patient.id,
                        hospital_id=schedule.hospital_id,
                        doctor_id=schedule.doctor_id,
                        scheduled_date=next_date,
                        target_hemoglobin=schedule.target_hemoglobin,
                        required_units=schedule.required_units,
                        blood_group_id=patient.blood_group_id,
                        status='Scheduled',
                        notes=f"Auto-scheduled ({interval_days} day interval)",
                        created_by=user.id
                    )
                    db.session.add(next_sched)

            db.session.commit()
            log_audit(user.id, 'EXECUTE_TRANSFUSION', 'transfusion_records', record.id)
            flash(f"Transfusion completed successfully! Patient gained +{record.hb_gain} g/dL Hb.", 'success')
            return redirect(url_for('transfusions.records'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Transfusion execution failed')
            flash("Transfusion execution failed. Please verify the unit and clinical inputs.", 'danger')

    return render_template('transfusions/execute.html', schedule=schedule, available_units=available_units)


@transfusions_bp.route('/records')
@login_required
def records():
    user = get_current_user()
    if user.is_donor:
        abort(403)

    page = request.args.get('page', 1, type=int)
    patient_id = request.args.get('patient_id', type=int)

    query = TransfusionRecord.active_query().options(
        joinedload(TransfusionRecord.patient),
        joinedload(TransfusionRecord.blood_unit),
        joinedload(TransfusionRecord.hospital),
        joinedload(TransfusionRecord.doctor)
    )

    if user.is_patient and user.patient_profile:
        query = query.filter(TransfusionRecord.patient_id == user.patient_profile.id)
        patients = [user.patient_profile]
    elif user.is_doctor and user.doctor_profile:
        doc = user.doctor_profile
        query = query.filter(
            (TransfusionRecord.doctor_id == doc.id) |
            (TransfusionRecord.patient.has(Patient.primary_doctor_id == doc.id))
        )
        patients = Patient.active_query().filter_by(primary_doctor_id=doc.id).all()
    else:
        patients = Patient.active_query().all()

    if patient_id:
        query = query.filter(TransfusionRecord.patient_id == patient_id)

    pagination = query.order_by(TransfusionRecord.transfusion_date.desc()).paginate(page=page, per_page=10, error_out=False)

    return render_template('transfusions/records.html', pagination=pagination, records=pagination.items, patients=patients, selected_patient=patient_id)
