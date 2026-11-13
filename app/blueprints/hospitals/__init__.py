from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models import (
    Hospital,
    Department,
    Doctor,
    DoctorSchedule,
    HospitalBloodBank,
    City,
    Area,
    User,
    Role
)
from app.utils import get_current_user, login_required, role_required, log_audit

hospitals_bp = Blueprint('hospitals', __name__)


@hospitals_bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    city_id = request.args.get('city_id', type=int)

    query = Hospital.active_query().options(
        joinedload(Hospital.city),
        joinedload(Hospital.area)
    )

    if search:
        query = query.filter(
            (Hospital.name.ilike(f"%{search}%")) |
            (Hospital.license_number.ilike(f"%{search}%")) |
            (Hospital.address.ilike(f"%{search}%"))
        )
    if city_id:
        query = query.filter(Hospital.city_id == city_id)

    pagination = query.order_by(Hospital.name).paginate(page=page, per_page=10, error_out=False)
    cities = City.active_query().order_by(City.name).all()

    return render_template(
        'hospitals/index.html',
        pagination=pagination,
        hospitals=pagination.items,
        search=search,
        selected_city=city_id,
        cities=cities
    )


@hospitals_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def create():
    cities = City.active_query().order_by(City.name).all()

    if request.method == 'POST':
        user = get_current_user()
        name = request.form.get('name', '').strip()
        license_number = request.form.get('license_number', '').strip()
        city_id = request.form.get('city_id', type=int)
        address = request.form.get('address', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        emergency_hotline = request.form.get('emergency_hotline', '').strip()
        total_beds = request.form.get('total_beds', 100, type=int)
        has_bb = bool(request.form.get('has_blood_bank'))
        has_tc = bool(request.form.get('has_thalassemia_center'))

        if not name or not license_number or not address or not phone:
            flash('Please complete all mandatory hospital fields.', 'danger')
            return render_template('hospitals/create.html', cities=cities)

        if Hospital.query.filter_by(license_number=license_number).first():
            flash('Hospital with this license number already exists.', 'danger')
            return render_template('hospitals/create.html', cities=cities)

        try:
            hospital = Hospital(
                name=name,
                license_number=license_number,
                city_id=city_id,
                address=address,
                phone=phone,
                email=email or None,
                emergency_hotline=emergency_hotline or None,
                total_beds=total_beds or 50,
                has_blood_bank=has_bb,
                has_thalassemia_center=has_tc,
                created_by=user.id
            )
            db.session.add(hospital)
            db.session.flush()

            # Create default departments
            for dept_name in ['Hematology & Oncology', 'Blood Transfusion Services', 'Pediatrics']:
                dept = Department(
                    hospital_id=hospital.id,
                    name=dept_name,
                    floor='1st Floor',
                    created_by=user.id
                )
                db.session.add(dept)

            # Auto-create blood bank if checked
            if has_bb:
                bb = HospitalBloodBank(
                    hospital_id=hospital.id,
                    license_number=f"BB-{license_number}",
                    in_charge_name="Chief Blood Bank Officer",
                    contact_phone=phone,
                    storage_capacity_units=500,
                    current_stock_units=0,
                    created_by=user.id
                )
                db.session.add(bb)

            db.session.commit()
            log_audit(user.id, 'CREATE', 'hospitals', hospital.id, None, {'name': name})
            flash(f'Hospital {name} added successfully.', 'success')
            return redirect(url_for('hospitals.view', id=hospital.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error creating hospital')
            flash('Error creating hospital. Please check details and try again.', 'danger')

    return render_template('hospitals/create.html', cities=cities)


@hospitals_bp.route('/<int:id>')
def view(id):
    hospital = Hospital.active_query().filter_by(id=id).first_or_404()
    departments = Department.active_query().filter_by(hospital_id=hospital.id).all()
    doctors = Doctor.active_query().filter_by(hospital_id=hospital.id).all()
    blood_bank = HospitalBloodBank.active_query().filter_by(hospital_id=hospital.id).first()

    return render_template(
        'hospitals/view.html',
        hospital=hospital,
        departments=departments,
        doctors=doctors,
        blood_bank=blood_bank
    )


@hospitals_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit(id):
    hospital = Hospital.active_query().filter_by(id=id).first_or_404()
    cities = City.active_query().order_by(City.name).all()

    if request.method == 'POST':
        user = get_current_user()
        hospital.name = request.form.get('name', '').strip()
        hospital.address = request.form.get('address', '').strip()
        hospital.phone = request.form.get('phone', '').strip()
        hospital.email = request.form.get('email', '').strip()
        hospital.emergency_hotline = request.form.get('emergency_hotline', '').strip()
        hospital.city_id = request.form.get('city_id', type=int)
        hospital.total_beds = request.form.get('total_beds', type=int)
        hospital.has_blood_bank = bool(request.form.get('has_blood_bank'))
        hospital.has_thalassemia_center = bool(request.form.get('has_thalassemia_center'))
        hospital.updated_by = user.id

        try:
            db.session.commit()
            log_audit(user.id, 'UPDATE', 'hospitals', hospital.id)
            flash('Hospital details updated successfully.', 'success')
            return redirect(url_for('hospitals.view', id=hospital.id))
        except Exception:
            db.session.rollback()
            flash('Error updating hospital.', 'danger')

    return render_template('hospitals/edit.html', hospital=hospital, cities=cities)


@hospitals_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete(id):
    hospital = Hospital.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()
    hospital.soft_delete(user.id)
    try:
        db.session.commit()
        log_audit(user.id, 'SOFT_DELETE', 'hospitals', hospital.id)
        flash('Hospital soft-deleted.', 'warning')
    except Exception:
        db.session.rollback()
        flash('Failed to delete hospital.', 'danger')

    return redirect(url_for('hospitals.index'))


@hospitals_bp.route('/<int:id>/doctors/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def create_doctor(id):
    hospital = Hospital.active_query().filter_by(id=id).first_or_404()
    departments = Department.active_query().filter_by(hospital_id=hospital.id).all()

    if request.method == 'POST':
        user = get_current_user()
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        specialization = request.form.get('specialization', 'Hematology')
        license_number = request.form.get('license_number', '').strip()
        dept_id = request.form.get('department_id', type=int)
        consultation_fee = request.form.get('consultation_fee', 0.0, type=float)
        experience_years = request.form.get('experience_years', 5, type=int)

        if not full_name or not email or not license_number:
            flash('Please complete mandatory doctor fields.', 'danger')
            return render_template('hospitals/create_doctor.html', hospital=hospital, departments=departments)

        try:
            doc_role = Role.query.filter_by(slug='doctor').first()
            username = email.split('@')[0] + f"_dr_{int(datetime.utcnow().timestamp()) % 1000}"

            # Temporary password for staff-created doctor
            import secrets, string
            alphabet = string.ascii_letters + string.digits
            temp_password = ''.join(secrets.choice(alphabet) for _ in range(10))

            doc_user = User(
                username=username,
                email=email,
                full_name=full_name,
                phone=phone,
                role_id=doc_role.id if doc_role else 1,
                city_id=hospital.city_id,
                must_change_password=True,
                created_by=user.id
            )
            doc_user.set_password(temp_password)
            db.session.add(doc_user)
            db.session.flush()

            doctor = Doctor(
                user_id=doc_user.id,
                hospital_id=hospital.id,
                department_id=dept_id,
                specialization=specialization,
                license_number=license_number,
                consultation_fee=consultation_fee,
                experience_years=experience_years,
                created_by=user.id
            )
            db.session.add(doctor)
            db.session.commit()

            log_audit(user.id, 'CREATE', 'doctors', doctor.id)
            flash(f"Dr. {full_name} added to {hospital.name}. Temporary login password: {temp_password}", 'success')
            return redirect(url_for('hospitals.view', id=hospital.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error adding doctor')
            flash('Error adding doctor. Please verify details.', 'danger')

    return render_template('hospitals/create_doctor.html', hospital=hospital, departments=departments)


@hospitals_bp.route('/doctors/<int:id>/schedules', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'hospital_staff', 'doctor')
def doctor_schedules(id):
    doctor = Doctor.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()
    if user.is_doctor and (not user.doctor_profile or user.doctor_profile.id != doctor.id):
        abort(403)

    if request.method == 'POST':
        day_of_week = request.form.get('day_of_week', 'Monday')
        start_time = request.form.get('start_time', '09:00')
        end_time = request.form.get('end_time', '14:00')
        max_patients = request.form.get('max_patients', 20, type=int)

        try:
            sched = DoctorSchedule(
                doctor_id=doctor.id,
                day_of_week=day_of_week,
                start_time=start_time,
                end_time=end_time,
                max_patients=max_patients,
                created_by=user.id
            )
            db.session.add(sched)
            db.session.commit()
            log_audit(user.id, 'CREATE', 'doctor_schedules', sched.id)
            flash(f'Weekly schedule for {day_of_week} ({start_time}-{end_time}) added.', 'success')
            return redirect(url_for('hospitals.doctor_schedules', id=doctor.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Failed to add doctor schedule')
            flash('Failed to add schedule. Please check inputs.', 'danger')

    schedules_list = DoctorSchedule.active_query().filter_by(doctor_id=doctor.id).all()
    return render_template('hospitals/doctor_schedules.html', doctor=doctor, schedules=schedules_list)
