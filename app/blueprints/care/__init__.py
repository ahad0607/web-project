from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models import (
    Appointment,
    Medication,
    PatientMedication,
    ChelationTherapyRecord,
    Patient,
    Doctor,
    Hospital
)
from app.utils import get_current_user, login_required, role_required, log_audit, create_notification

care_bp = Blueprint('care', __name__)


@care_bp.route('/appointments')
@login_required
def appointments():
    user = get_current_user()
    if user.is_donor:
        abort(403)

    page = request.args.get('page', 1, type=int)
    patient_id = request.args.get('patient_id', type=int)
    status = request.args.get('status', '').strip()

    query = Appointment.active_query().options(
        joinedload(Appointment.patient),
        joinedload(Appointment.doctor),
        joinedload(Appointment.hospital)
    )

    if user.is_patient and user.patient_profile:
        query = query.filter(Appointment.patient_id == user.patient_profile.id)
        patients = [user.patient_profile]
    elif user.is_doctor and user.doctor_profile:
        doc = user.doctor_profile
        query = query.filter(
            (Appointment.doctor_id == doc.id) |
            (Appointment.patient.has(Patient.primary_doctor_id == doc.id))
        )
        patients = Patient.active_query().filter_by(primary_doctor_id=doc.id).all()
    else:
        patients = Patient.active_query().all()

    if patient_id:
        query = query.filter(Appointment.patient_id == patient_id)
    if status:
        query = query.filter(Appointment.status == status)

    pagination = query.order_by(Appointment.appointment_date.desc()).paginate(page=page, per_page=10, error_out=False)

    return render_template('care/appointments.html', pagination=pagination, appointments=pagination.items, patients=patients, selected_patient=patient_id, selected_status=status)


@care_bp.route('/appointments/create', methods=['GET', 'POST'])
@login_required
def create_appointment():
    user = get_current_user()
    if user.is_donor:
        abort(403)

    if user.is_patient and user.patient_profile:
        patients = [user.patient_profile]
    elif user.is_doctor and user.doctor_profile:
        patients = Patient.active_query().filter_by(primary_doctor_id=user.doctor_profile.id).all()
    else:
        patients = Patient.active_query().all()

    doctors = Doctor.active_query().all()
    hospitals = Hospital.active_query().all()

    if request.method == 'POST':
        patient_id = request.form.get('patient_id', type=int)
        doctor_id = request.form.get('doctor_id', type=int)
        hospital_id = request.form.get('hospital_id', type=int)
        appt_date_str = request.form.get('appointment_date', '')
        time_slot = request.form.get('time_slot', '10:00 AM - 10:30 AM')
        reason = request.form.get('reason', 'Routine Checkup')
        appt_type = request.form.get('appointment_type', 'Regular Checkup')

        # Patients can only book for themselves
        if user.is_patient and user.patient_profile:
            patient_id = user.patient_profile.id

        if not patient_id or not doctor_id or not hospital_id or not appt_date_str:
            flash('Please complete all required fields.', 'danger')
            return render_template('care/create_appointment.html', patients=patients, doctors=doctors, hospitals=hospitals)

        try:
            appt_date = datetime.strptime(appt_date_str, '%Y-%m-%d').date()
            if appt_date < date.today():
                flash('Appointment date cannot be in the past.', 'danger')
                return render_template('care/create_appointment.html', patients=patients, doctors=doctors, hospitals=hospitals)

            # Check double-booking for doctor at same date and slot
            existing_booking = Appointment.active_query().filter(
                Appointment.doctor_id == doctor_id,
                Appointment.appointment_date == appt_date,
                Appointment.time_slot == time_slot,
                Appointment.status.notin_(['Cancelled', 'No-Show'])
            ).first()
            if existing_booking:
                flash(f'Dr. {existing_booking.doctor.full_name if existing_booking.doctor else ""} is already booked for {time_slot} on {appt_date}. Please select another time or doctor.', 'danger')
                return render_template('care/create_appointment.html', patients=patients, doctors=doctors, hospitals=hospitals)

            appointment = Appointment(
                patient_id=patient_id,
                doctor_id=doctor_id,
                hospital_id=hospital_id,
                appointment_date=appt_date,
                time_slot=time_slot,
                reason=reason,
                appointment_type=appt_type,
                status='Booked',
                created_by=user.id
            )
            db.session.add(appointment)
            db.session.commit()

            patient = Patient.get_by_id(patient_id)
            if patient and patient.user_id:
                create_notification(
                    user_id=patient.user_id,
                    title="Appointment Booked 📅",
                    message=f"You have a consultation confirmed on {appt_date} ({time_slot}).",
                    notification_type="Schedule",
                    link_url=url_for('care.appointments')
                )

            log_audit(user.id, 'CREATE', 'appointments', appointment.id)
            flash('Appointment successfully booked.', 'success')
            return redirect(url_for('care.appointments'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Failed to book appointment')
            flash('Failed to book appointment. Please check the inputs.', 'danger')

    return render_template('care/create_appointment.html', patients=patients, doctors=doctors, hospitals=hospitals)


@care_bp.route('/appointments/<int:id>/status', methods=['POST'])
@login_required
@role_required('admin', 'doctor', 'hospital_staff')
def update_appointment_status(id):
    appointment = Appointment.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()
    new_status = request.form.get('status')

    allowed_statuses = ['Booked', 'Completed', 'Cancelled', 'No-Show']
    if new_status not in allowed_statuses:
        flash(f'Invalid appointment status "{new_status}".', 'danger')
        return redirect(url_for('care.appointments'))

    # Terminal statuses cannot transition
    if appointment.status in ('Completed', 'Cancelled'):
        flash(f'Cannot change status: appointment is already {appointment.status.lower()}.', 'warning')
        return redirect(url_for('care.appointments'))

    appointment.status = new_status
    appointment.updated_by = user.id

    try:
        db.session.commit()
        log_audit(user.id, 'STATUS_UPDATE', 'appointments', appointment.id, {'status': new_status})
        flash(f'Appointment marked as {new_status}.', 'success')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Update appointment status failed')
        flash('Update failed. Please try again.', 'danger')

    return redirect(url_for('care.appointments'))


@care_bp.route('/medications')
@login_required
def medications():
    meds = Medication.active_query().order_by(Medication.name).all()
    return render_template('care/medications.html', medications=meds)


@care_bp.route('/medications/create', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'doctor')
def create_medication():
    if request.method == 'POST':
        user = get_current_user()
        name = request.form.get('name', '').strip()
        generic_name = request.form.get('generic_name', '').strip()
        drug_class = request.form.get('drug_class', 'Iron Chelator')
        form = request.form.get('form', 'Tablet')
        dosage = request.form.get('standard_dosage', '')
        desc = request.form.get('description', '')

        try:
            med = Medication(
                name=name,
                generic_name=generic_name,
                drug_class=drug_class,
                form=form,
                standard_dosage=dosage,
                description=desc,
                created_by=user.id
            )
            db.session.add(med)
            db.session.commit()
            log_audit(user.id, 'CREATE', 'medications', med.id)
            flash(f'Medication {name} added to formulary.', 'success')
            return redirect(url_for('care.medications'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error adding medication')
            flash('Error adding medication. Please try again.', 'danger')

    return render_template('care/create_medication.html')


@care_bp.route('/patient-medications/prescribe', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'doctor')
def prescribe():
    user = get_current_user()
    if user.is_doctor and user.doctor_profile:
        patients = Patient.active_query().filter_by(primary_doctor_id=user.doctor_profile.id).all()
    else:
        patients = Patient.active_query().all()

    medications = Medication.active_query().all()
    doctors = Doctor.active_query().all()

    if request.method == 'POST':
        patient_id = request.form.get('patient_id', type=int)
        medication_id = request.form.get('medication_id', type=int)
        doctor_id = user.doctor_profile.id if (user.is_doctor and user.doctor_profile) else request.form.get('doctor_id', type=int)
        dosage = request.form.get('dosage', '').strip()
        frequency = request.form.get('frequency', 'Once Daily')
        instructions = request.form.get('instructions', '')

        if not patient_id or not medication_id or not dosage:
            flash('Patient, medication, and dosage are required fields.', 'danger')
            return render_template('care/prescribe.html', patients=patients, medications=medications, doctors=doctors)

        # Prevent duplicate active prescriptions
        duplicate = PatientMedication.active_query().filter_by(
            patient_id=patient_id,
            medication_id=medication_id,
            is_active=True
        ).first()
        if duplicate:
            flash('This patient already has an active prescription for this medication.', 'warning')
            return render_template('care/prescribe.html', patients=patients, medications=medications, doctors=doctors)

        try:
            pm = PatientMedication(
                patient_id=patient_id,
                medication_id=medication_id,
                prescribed_by_doctor_id=doctor_id,
                dosage=dosage,
                frequency=frequency,
                instructions=instructions,
                start_date=date.today(),
                is_active=True,
                created_by=user.id
            )
            db.session.add(pm)
            db.session.commit()
            log_audit(user.id, 'PRESCRIBE_MEDICATION', 'patient_medications', pm.id)
            flash('Prescription added successfully.', 'success')
            return redirect(url_for('patients.view', id=patient_id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Prescription failed')
            flash('Error prescribing medication. Please try again.', 'danger')

    return render_template('care/prescribe.html', patients=patients, medications=medications, doctors=doctors)


@care_bp.route('/chelation/record', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'doctor', 'hospital_staff')
def record_chelation():
    user = get_current_user()
    if user.is_doctor and user.doctor_profile:
        patients = Patient.active_query().filter_by(primary_doctor_id=user.doctor_profile.id).all()
    else:
        patients = Patient.active_query().all()

    medications = Medication.active_query().filter_by(drug_class='Iron Chelator').all()
    doctors = Doctor.active_query().all()

    if request.method == 'POST':
        patient_id = request.form.get('patient_id', type=int)
        medication_id = request.form.get('medication_id', type=int)
        doctor_id = user.doctor_profile.id if (user.is_doctor and user.doctor_profile) else request.form.get('doctor_id', type=int)
        dosage_mg = request.form.get('dosage_mg', type=float)
        frequency = request.form.get('frequency', 'Once Daily')
        adherence = request.form.get('adherence_percentage', 95.0, type=float)
        side_effects = request.form.get('side_effects_noted', 'None reported')

        if not patient_id or not medication_id or dosage_mg is None or dosage_mg <= 0:
            flash('Patient, chelator medication, and a positive dosage in mg are required.', 'danger')
            return render_template('care/record_chelation.html', patients=patients, medications=medications, doctors=doctors)

        if adherence is not None and not (0.0 <= adherence <= 100.0):
            flash('Adherence percentage must be between 0% and 100%.', 'danger')
            return render_template('care/record_chelation.html', patients=patients, medications=medications, doctors=doctors)

        try:
            rec = ChelationTherapyRecord(
                patient_id=patient_id,
                medication_id=medication_id,
                dosage_mg=dosage_mg,
                frequency=frequency,
                start_date=date.today(),
                adherence_percentage=adherence if adherence is not None else 95.0,
                side_effects_noted=side_effects,
                prescribed_by_doctor_id=doctor_id,
                created_by=user.id
            )
            db.session.add(rec)
            db.session.commit()
            log_audit(user.id, 'RECORD_CHELATION', 'chelation_therapy_records', rec.id)
            flash('Iron chelation therapy record logged.', 'success')
            return redirect(url_for('patients.view', id=patient_id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Chelation record failed')
            flash('Error logging chelation therapy.', 'danger')

    return render_template('care/record_chelation.html', patients=patients, medications=medications, doctors=doctors)
