import secrets
import string
import re
from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models import (
    Patient,
    Guardian,
    PatientGuardian,
    PatientMedicalHistory,
    PatientDiagnosis,
    HemoglobinRecord,
    FerritinRecord,
    BloodGroup,
    City,
    Area,
    Hospital,
    Doctor,
    Diagnosis,
    User,
    Role
)
from app.utils import (
    get_current_user,
    login_required,
    role_required,
    log_audit,
    validate_phone,
    validate_email_format,
    validate_cnic,
    create_notification
)

patients_bp = Blueprint('patients', __name__)


@patients_bp.route('/')
@login_required
def index():
    user = get_current_user()
    if user.is_donor:
        abort(403)
    if user.is_patient:
        if user.patient_profile:
            return redirect(url_for('patients.view', id=user.patient_profile.id))
        abort(403)

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    blood_group_id = request.args.get('blood_group_id', type=int)
    city_id = request.args.get('city_id', type=int)

    query = Patient.active_query().join(Patient.user).options(
        joinedload(Patient.user),
        joinedload(Patient.blood_group),
        joinedload(Patient.city),
        joinedload(Patient.primary_hospital)
    )

    # Doctor sees only their assigned patients
    if user.is_doctor and user.doctor_profile:
        query = query.filter(Patient.primary_doctor_id == user.doctor_profile.id)

    if search:
        safe_search = search.replace('%', r'\%').replace('_', r'\_')
        query = query.filter(
            (Patient.mrn.ilike(f"%{safe_search}%")) |
            (User.full_name.ilike(f"%{safe_search}%")) |
            (User.phone.ilike(f"%{safe_search}%"))
        )
    if blood_group_id:
        query = query.filter(Patient.blood_group_id == blood_group_id)
    if city_id:
        query = query.filter(Patient.city_id == city_id)

    pagination = query.order_by(Patient.created_at.desc()).paginate(page=page, per_page=10, error_out=False)
    blood_groups = BloodGroup.active_query().order_by(BloodGroup.name).all()
    cities = City.active_query().order_by(City.name).all()

    return render_template(
        'patients/index.html',
        pagination=pagination,
        patients=pagination.items,
        search=search,
        selected_bg=blood_group_id,
        selected_city=city_id,
        blood_groups=blood_groups,
        cities=cities
    )


@patients_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'doctor', 'hospital_staff')
def create():
    blood_groups = BloodGroup.active_query().order_by(BloodGroup.name).all()
    cities = City.active_query().order_by(City.name).all()
    hospitals = Hospital.active_query().order_by(Hospital.name).all()
    doctors = Doctor.active_query().all()
    diagnoses = Diagnosis.active_query().order_by(Diagnosis.name).all()

    if request.method == 'POST':
        user = get_current_user()
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        cnic = request.form.get('cnic', '').strip()
        blood_group_id = request.form.get('blood_group_id', type=int)
        city_id = request.form.get('city_id', type=int)
        area_id = request.form.get('area_id', type=int)
        dob_str = request.form.get('date_of_birth', '')
        gender = request.form.get('gender', 'Male')
        weight_kg = request.form.get('weight_kg', type=float)
        height_cm = request.form.get('height_cm', type=float)
        hospital_id = request.form.get('primary_hospital_id', type=int)
        doctor_id = request.form.get('primary_doctor_id', type=int)
        diagnosis_id = request.form.get('diagnosis_id', type=int)
        baseline_hb = request.form.get('baseline_hemoglobin', 7.0, type=float)
        transfusion_interval = request.form.get('transfusion_interval_days', 21, type=int)
        emergency_contact_name = request.form.get('emergency_contact_name', '').strip()
        emergency_contact_phone = request.form.get('emergency_contact_phone', '').strip()

        errors = []
        if not full_name or not email or not phone:
            errors.append('Name, email, and phone are required.')
        if email and not validate_email_format(email):
            errors.append('Please provide a valid email address.')
        if phone and not validate_phone(phone):
            errors.append('Please provide a valid Pakistani phone number (e.g. 03001234567 or +923001234567).')
        if emergency_contact_phone and not validate_phone(emergency_contact_phone):
            errors.append('Emergency contact phone must be a valid Pakistani phone number.')
        if cnic and not validate_cnic(cnic):
            errors.append('Please provide a valid 13-digit CNIC (e.g. 42101-1234567-1).')
        if not blood_group_id:
            errors.append('Blood group is required.')
        if not dob_str:
            errors.append('Date of birth is required.')
        if not emergency_contact_name or not emergency_contact_phone:
            errors.append('Emergency contact name and phone are required.')

        if weight_kg is not None and not (3.0 <= weight_kg <= 200.0):
            errors.append('Patient weight must be between 3.0 kg and 200.0 kg.')
        if baseline_hb is not None and not (2.0 <= baseline_hb <= 20.0):
            errors.append('Baseline hemoglobin must be between 2.0 and 20.0 g/dL.')
        if transfusion_interval is not None and not (7 <= transfusion_interval <= 90):
            errors.append('Transfusion interval must be between 7 and 90 days.')

        try:
            dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
        except ValueError:
            errors.append('Invalid date format for birth date.')

        # Check existing user
        if email and User.query.filter_by(email=email).first():
            errors.append('A user account with this email already exists.')
        if phone and User.query.filter_by(phone=phone).first():
            errors.append('A user account with this phone number already exists.')
        if cnic and User.query.filter_by(cnic=cnic).first():
            errors.append('A user account with this CNIC already exists.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template(
                'patients/create.html',
                blood_groups=blood_groups,
                cities=cities,
                hospitals=hospitals,
                doctors=doctors,
                diagnoses=diagnoses
            )

        try:
            patient_role = Role.query.filter_by(slug='patient').first()
            base_user = re.sub(r'[^a-zA-Z0-9]', '', email.split('@')[0]) or 'patient'
            username = f"{base_user}_{secrets.token_hex(3)}"
            
            # Generate random temporary password
            alphabet = string.ascii_letters + string.digits
            temp_password = ''.join(secrets.choice(alphabet) for _ in range(10))

            new_user = User(
                username=username,
                email=email,
                full_name=full_name,
                phone=phone,
                cnic=cnic or None,
                role_id=patient_role.id if patient_role else 1,
                city_id=city_id,
                must_change_password=True,
                created_by=user.id
            )
            new_user.set_password(temp_password)
            db.session.add(new_user)
            db.session.flush()

            # Generate unique MRN
            mrn = f"THAL-{datetime.utcnow().year}-{new_user.id:04d}"

            patient = Patient(
                user_id=new_user.id,
                mrn=mrn,
                blood_group_id=blood_group_id,
                city_id=city_id,
                area_id=area_id,
                date_of_birth=dob,
                gender=gender,
                weight_kg=weight_kg or 30.0,
                height_cm=height_cm or 120.0,
                primary_hospital_id=hospital_id,
                primary_doctor_id=doctor_id,
                diagnosis_id=diagnosis_id,
                baseline_hemoglobin=baseline_hb or 7.0,
                transfusion_interval_days=transfusion_interval or 21,
                emergency_contact_name=emergency_contact_name,
                emergency_contact_phone=emergency_contact_phone,
                created_by=user.id
            )
            db.session.add(patient)
            db.session.flush()

            # Create empty medical history
            med_history = PatientMedicalHistory(
                patient_id=patient.id,
                created_by=user.id
            )
            db.session.add(med_history)

            db.session.commit()
            log_audit(user.id, 'CREATE', 'patients', patient.id, None, {'mrn': mrn, 'name': full_name})
            flash(f"Patient {full_name} registered successfully with MRN {mrn}! Temporary login password: {temp_password} (User must change password upon first login).", 'success')
            return redirect(url_for('patients.view', id=patient.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error creating patient')
            flash("Error creating patient. Please verify the inputs and try again.", 'danger')

    return render_template(
        'patients/create.html',
        blood_groups=blood_groups,
        cities=cities,
        hospitals=hospitals,
        doctors=doctors,
        diagnoses=diagnoses
    )


@patients_bp.route('/<int:id>')
@login_required
def view(id):
    patient = Patient.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()

    # Ownership scoping
    if user.is_donor:
        abort(403)
    if user.is_patient:
        if not user.patient_profile or user.patient_profile.id != patient.id:
            abort(403)
    elif user.is_doctor:
        if not user.doctor_profile or patient.primary_doctor_id != user.doctor_profile.id:
            abort(403)

    med_history = PatientMedicalHistory.active_query().filter_by(patient_id=patient.id).first()
    hb_records = HemoglobinRecord.active_query().filter_by(patient_id=patient.id).order_by(HemoglobinRecord.test_date.desc()).limit(10).all()
    ferritin_records = FerritinRecord.active_query().filter_by(patient_id=patient.id).order_by(FerritinRecord.test_date.desc()).limit(10).all()
    all_diagnoses = Diagnosis.active_query().order_by(Diagnosis.name).all()

    return render_template(
        'patients/view.html',
        patient=patient,
        medical_history=med_history,
        hb_records=hb_records,
        ferritin_records=ferritin_records,
        all_diagnoses=all_diagnoses
    )


@patients_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'doctor', 'hospital_staff')
def edit(id):
    patient = Patient.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()
    if user.is_doctor:
        if not user.doctor_profile or patient.primary_doctor_id != user.doctor_profile.id:
            abort(403)

    blood_groups = BloodGroup.active_query().order_by(BloodGroup.name).all()
    cities = City.active_query().order_by(City.name).all()
    hospitals = Hospital.active_query().order_by(Hospital.name).all()
    doctors = Doctor.active_query().all()
    diagnoses = Diagnosis.active_query().order_by(Diagnosis.name).all()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        weight_kg = request.form.get('weight_kg', type=float)
        height_cm = request.form.get('height_cm', type=float)
        primary_hospital_id = request.form.get('primary_hospital_id', type=int)
        primary_doctor_id = request.form.get('primary_doctor_id', type=int)
        diagnosis_id = request.form.get('diagnosis_id', type=int)
        baseline_hb = request.form.get('baseline_hemoglobin', type=float)
        interval = request.form.get('transfusion_interval_days', type=int)
        emergency_contact_name = request.form.get('emergency_contact_name', '').strip()
        emergency_contact_phone = request.form.get('emergency_contact_phone', '').strip()

        old_data = {'full_name': patient.full_name, 'weight_kg': patient.weight_kg}

        if patient.user:
            patient.user.full_name = full_name
            patient.user.phone = phone
        patient.weight_kg = weight_kg or patient.weight_kg
        patient.height_cm = height_cm or patient.height_cm
        patient.primary_hospital_id = primary_hospital_id
        patient.primary_doctor_id = primary_doctor_id
        patient.diagnosis_id = diagnosis_id
        patient.baseline_hemoglobin = baseline_hb or patient.baseline_hemoglobin
        patient.transfusion_interval_days = interval or patient.transfusion_interval_days
        patient.emergency_contact_name = emergency_contact_name or patient.emergency_contact_name
        patient.emergency_contact_phone = emergency_contact_phone or patient.emergency_contact_phone
        patient.updated_by = user.id

        try:
            db.session.commit()
            log_audit(user.id, 'UPDATE', 'patients', patient.id, old_data, {'full_name': full_name})
            flash('Patient record updated successfully.', 'success')
            return redirect(url_for('patients.view', id=patient.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Patient update failed')
            flash('Failed to update patient record.', 'danger')

    return render_template(
        'patients/edit.html',
        patient=patient,
        blood_groups=blood_groups,
        cities=cities,
        hospitals=hospitals,
        doctors=doctors,
        diagnoses=diagnoses
    )


@patients_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete(id):
    patient = Patient.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()
    patient.soft_delete(user.id)
    if patient.user:
        patient.user.soft_delete(user.id)
    
    try:
        db.session.commit()
        log_audit(user.id, 'SOFT_DELETE', 'patients', patient.id)
        flash(f'Patient {patient.mrn} has been soft-deleted.', 'warning')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Patient deletion failed')
        flash('Failed to delete patient.', 'danger')

    return redirect(url_for('patients.index'))


@patients_bp.route('/<int:id>/hemoglobin/add', methods=['POST'])
@login_required
@role_required('admin', 'doctor', 'hospital_staff')
def add_hemoglobin(id):
    patient = Patient.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()
    if user.is_doctor and (not user.doctor_profile or patient.primary_doctor_id != user.doctor_profile.id):
        abort(403)

    hb_level = request.form.get('hb_level', type=float)
    rbc_count = request.form.get('rbc_count', type=float)
    test_date_str = request.form.get('test_date', '')
    lab_name = request.form.get('lab_name', 'Central Diagnostic Lab')
    notes = request.form.get('notes', '')

    if hb_level is None or not (2.0 <= hb_level <= 20.0):
        flash('Hemoglobin level must be clinically valid (between 2.0 and 20.0 g/dL).', 'danger')
        return redirect(url_for('patients.view', id=patient.id))

    try:
        test_date = datetime.strptime(test_date_str, '%Y-%m-%d').date() if test_date_str else date.today()
        record = HemoglobinRecord(
            patient_id=patient.id,
            test_date=test_date,
            hb_level=hb_level,
            rbc_count=rbc_count,
            lab_name=lab_name,
            notes=notes,
            recorded_by_user_id=user.id,
            created_by=user.id
        )
        db.session.add(record)
        db.session.commit()

        log_audit(user.id, 'CREATE', 'hemoglobin_records', record.id, None, {'hb_level': hb_level})

        # Clinical alert if Hb is critically low (< 7.0 g/dL)
        if hb_level < 7.0:
            if patient.user_id:
                create_notification(
                    patient.user_id,
                    'Critical Alert: Low Hemoglobin',
                    f'Your latest hemoglobin test result is critically low ({hb_level} g/dL). Please consult your doctor for a transfusion review.',
                    notification_type='Alert'
                )
            if patient.primary_doctor and patient.primary_doctor.user_id:
                create_notification(
                    patient.primary_doctor.user_id,
                    f'Critical Alert: Patient {patient.full_name} Hb Low',
                    f'Patient {patient.full_name} (MRN: {patient.mrn}) recorded critical Hb of {hb_level} g/dL.',
                    notification_type='Alert'
                )

        flash(f'Hemoglobin test record ({hb_level} g/dL) logged.', 'success')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Add hemoglobin failed')
        flash('Error adding hemoglobin record.', 'danger')

    return redirect(url_for('patients.view', id=patient.id))


@patients_bp.route('/<int:id>/ferritin/add', methods=['POST'])
@login_required
@role_required('admin', 'doctor', 'hospital_staff')
def add_ferritin(id):
    patient = Patient.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()
    if user.is_doctor and (not user.doctor_profile or patient.primary_doctor_id != user.doctor_profile.id):
        abort(403)

    ferritin_level = request.form.get('ferritin_level', type=float)
    target_level = request.form.get('target_level', 1000.0, type=float)
    test_date_str = request.form.get('test_date', '')
    lab_name = request.form.get('lab_name', 'Central Diagnostic Lab')
    notes = request.form.get('notes', '')

    if ferritin_level is None or not (0.0 <= ferritin_level <= 10000.0):
        flash('Ferritin level must be clinically valid (between 0 and 10,000 ng/mL).', 'danger')
        return redirect(url_for('patients.view', id=patient.id))

    try:
        test_date = datetime.strptime(test_date_str, '%Y-%m-%d').date() if test_date_str else date.today()
        record = FerritinRecord(
            patient_id=patient.id,
            test_date=test_date,
            ferritin_level=ferritin_level,
            target_level=target_level,
            lab_name=lab_name,
            notes=notes,
            recorded_by_user_id=user.id,
            created_by=user.id
        )
        db.session.add(record)
        db.session.commit()

        log_audit(user.id, 'CREATE', 'ferritin_records', record.id, None, {'ferritin_level': ferritin_level})

        # Clinical alert if Ferritin exceeds target
        if ferritin_level > (target_level or 1000.0):
            if patient.user_id:
                create_notification(
                    patient.user_id,
                    'Clinical Alert: Elevated Ferritin',
                    f'Your latest serum ferritin is {ferritin_level} ng/mL (target: {target_level} ng/mL). Please consult your doctor for chelation adjustment.',
                    notification_type='Alert'
                )
            if patient.primary_doctor and patient.primary_doctor.user_id:
                create_notification(
                    patient.primary_doctor.user_id,
                    f'Elevated Ferritin: Patient {patient.full_name}',
                    f'Patient {patient.full_name} (MRN: {patient.mrn}) recorded serum ferritin of {ferritin_level} ng/mL (target: {target_level} ng/mL).',
                    notification_type='Alert'
                )

        flash(f'Serum ferritin record ({ferritin_level} ng/mL) logged.', 'success')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Add ferritin failed')
        flash('Error adding ferritin record.', 'danger')

    return redirect(url_for('patients.view', id=patient.id))


@patients_bp.route('/<int:id>/guardians/add', methods=['POST'])
@login_required
def add_guardian(id):
    patient = Patient.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()

    # Restricted to staff/doctor/admin, or the patient for their own record
    if user.is_patient:
        if not user.patient_profile or user.patient_profile.id != patient.id:
            abort(403)
    elif user.is_doctor:
        if not user.doctor_profile or patient.primary_doctor_id != user.doctor_profile.id:
            abort(403)
    elif not (user.is_admin or user.role.slug in ('hospital_staff', 'admin')):
        abort(403)

    full_name = request.form.get('full_name', '').strip()
    relationship_to_patient = request.form.get('relationship_to_patient', 'Parent')
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    cnic = request.form.get('cnic', '').strip()
    is_primary = bool(request.form.get('is_primary'))

    errors = []
    if not full_name or not phone:
        errors.append('Guardian name and phone are required.')
    if phone and not validate_phone(phone):
        errors.append('Please provide a valid Pakistani phone number.')
    if email and not validate_email_format(email):
        errors.append('Please provide a valid email address.')
    if cnic and not validate_cnic(cnic):
        errors.append('Please provide a valid 13-digit CNIC.')

    if errors:
        for err in errors:
            flash(err, 'danger')
        return redirect(url_for('patients.view', id=patient.id))

    try:
        guardian = Guardian(
            full_name=full_name,
            relationship_to_patient=relationship_to_patient,
            phone=phone,
            email=email or None,
            cnic=cnic or None,
            created_by=user.id
        )
        db.session.add(guardian)
        db.session.flush()

        link = PatientGuardian(
            patient_id=patient.id,
            guardian_id=guardian.id,
            is_primary=is_primary,
            created_by=user.id
        )
        db.session.add(link)
        db.session.commit()
        log_audit(user.id, 'CREATE', 'guardians', guardian.id, None, {'full_name': full_name})
        flash(f'Guardian {full_name} added to patient profile.', 'success')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Add guardian failed')
        flash('Failed to add guardian. Please check inputs and try again.', 'danger')

    return redirect(url_for('patients.view', id=patient.id))


@patients_bp.route('/<int:id>/diagnoses/add', methods=['POST'])
@login_required
@role_required('admin', 'doctor', 'hospital_staff')
def add_diagnosis(id):
    patient = Patient.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()
    if user.is_doctor and (not user.doctor_profile or patient.primary_doctor_id != user.doctor_profile.id):
        abort(403)

    diagnosis_id = request.form.get('diagnosis_id', type=int)
    diag_date_str = request.form.get('diagnosed_date', '')
    severity = request.form.get('severity', 'Moderate')
    notes = request.form.get('notes', '')

    if not diagnosis_id:
        flash('Diagnosis selection is required.', 'danger')
        return redirect(url_for('patients.view', id=patient.id))

    try:
        diag_date = datetime.strptime(diag_date_str, '%Y-%m-%d').date() if diag_date_str else date.today()
        doctor_id = user.doctor_profile.id if (user.is_doctor and user.doctor_profile) else patient.primary_doctor_id
        pd = PatientDiagnosis(
            patient_id=patient.id,
            diagnosis_id=diagnosis_id,
            diagnosed_date=diag_date,
            diagnosed_by_doctor_id=doctor_id,
            severity=severity,
            notes=notes,
            created_by=user.id
        )
        db.session.add(pd)
        db.session.commit()
        log_audit(user.id, 'ADD_DIAGNOSIS', 'patient_diagnoses', pd.id)
        flash('Clinical diagnosis linked to patient medical record.', 'success')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Add diagnosis failed')
        flash('Failed to add diagnosis.', 'danger')

    return redirect(url_for('patients.view', id=patient.id))
