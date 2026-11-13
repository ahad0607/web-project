from datetime import datetime, date
import secrets
import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models import (
    Donor,
    DonorHealthScreening,
    DonorAvailability,
    Donation,
    Badge,
    DonorBadge,
    DonorMatch,
    ResponseLog,
    BloodGroup,
    City,
    Area,
    Hospital,
    User,
    Role
)
from app.utils import (
    get_current_user,
    login_required,
    role_required,
    log_audit,
    validate_donor_screening,
    check_and_award_donor_badges,
    create_notification,
    expire_emergency_broadcasts,
    validate_email_format,
    validate_phone,
    validate_cnic
)

donors_bp = Blueprint('donors', __name__)


@donors_bp.route('/')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    blood_group_id = request.args.get('blood_group_id', type=int)
    city_id = request.args.get('city_id', type=int)
    eligibility = request.args.get('eligibility', '').strip()

    query = Donor.active_query().join(Donor.user).options(
        joinedload(Donor.user),
        joinedload(Donor.blood_group),
        joinedload(Donor.city)
    )

    if search:
        safe_search = search.replace('%', r'\%').replace('_', r'\_')
        query = query.filter(
            (User.full_name.ilike(f"%{safe_search}%")) |
            (User.phone.ilike(f"%{safe_search}%"))
        )
    if blood_group_id:
        query = query.filter(Donor.blood_group_id == blood_group_id)
    if city_id:
        query = query.filter(Donor.city_id == city_id)
    if eligibility:
        query = query.filter(Donor.donation_eligibility_status == eligibility)

    pagination = query.order_by(Donor.total_donations.desc()).paginate(page=page, per_page=10, error_out=False)
    blood_groups = BloodGroup.active_query().order_by(BloodGroup.name).all()
    cities = City.active_query().order_by(City.name).all()

    return render_template(
        'donors/index.html',
        pagination=pagination,
        donors=pagination.items,
        search=search,
        selected_bg=blood_group_id,
        selected_city=city_id,
        selected_eligibility=eligibility,
        blood_groups=blood_groups,
        cities=cities
    )


@donors_bp.route('/register', methods=['GET', 'POST'])
def register():
    blood_groups = BloodGroup.active_query().order_by(BloodGroup.name).all()
    cities = City.active_query().order_by(City.name).all()
    hospitals = Hospital.active_query().order_by(Hospital.name).all()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        phone = request.form.get('phone', '').strip()
        cnic = request.form.get('cnic', '').strip()
        blood_group_id = request.form.get('blood_group_id', type=int)
        city_id = request.form.get('city_id', type=int)
        dob_str = request.form.get('date_of_birth', '')
        gender = request.form.get('gender', 'Male')
        weight_kg = request.form.get('weight_kg', 65.0, type=float)
        preferred_center_id = request.form.get('preferred_donation_center_id', type=int)

        errors = []
        if not full_name or not email or not phone or not blood_group_id or not dob_str:
            errors.append('Please fill in all mandatory fields.')

        if email and not validate_email_format(email):
            errors.append('Please provide a valid email address.')

        if phone and not validate_phone(phone):
            errors.append('Please provide a valid Pakistani phone number (e.g. 03001234567 or +923001234567).')

        if cnic and not validate_cnic(cnic):
            errors.append('Please provide a valid 13-digit CNIC (e.g. 42101-1234567-1).')

        if not password or len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            errors.append('Password is required, must be at least 8 characters long, and contain letters and numbers.')

        try:
            dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if not (18 <= age <= 60):
                errors.append(f'Donor must be between 18 and 60 years of age (calculated age: {age}).')
        except ValueError:
            errors.append('Invalid date format for birth date.')

        if not (50.0 <= weight_kg <= 200.0):
            errors.append('Donors must weigh between 50 kg and 200 kg to donate blood safely.')

        if email and User.query.filter_by(email=email).first():
            errors.append('Email is already registered.')
        if phone and User.query.filter_by(phone=phone).first():
            errors.append('Phone number is already registered.')
        if cnic and User.query.filter_by(cnic=cnic).first():
            errors.append('CNIC is already registered.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template('donors/register.html', blood_groups=blood_groups, cities=cities, hospitals=hospitals)

        try:
            donor_role = Role.query.filter_by(slug='donor').first()
            base_user = re.sub(r'[^a-zA-Z0-9]', '', email.split('@')[0]) or 'donor'
            username = f"{base_user}_{secrets.token_hex(3)}"

            new_user = User(
                username=username,
                email=email,
                full_name=full_name,
                phone=phone,
                cnic=cnic or None,
                role_id=donor_role.id if donor_role else 2,
                city_id=city_id
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()

            donor = Donor(
                user_id=new_user.id,
                blood_group_id=blood_group_id,
                city_id=city_id,
                date_of_birth=dob,
                gender=gender,
                weight_kg=weight_kg,
                preferred_donation_center_id=preferred_center_id,
                donation_eligibility_status='Eligible'
            )
            db.session.add(donor)
            db.session.flush()

            # Set default emergency availability
            availability = DonorAvailability(
                donor_id=donor.id,
                is_available_for_emergency=True,
                available_days='All Days',
                preferred_time_slot='Anytime',
                travel_radius_km=30
            )
            db.session.add(availability)

            db.session.commit()
            flash('Donor registered successfully! You are now part of LifeBridge life-savers. Please log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Donor registration failed')
            flash('Registration failed. Please check your details and try again.', 'danger')

    return render_template('donors/register.html', blood_groups=blood_groups, cities=cities, hospitals=hospitals)


@donors_bp.route('/<int:id>')
@login_required
def view(id):
    donor = Donor.active_query().filter_by(id=id).first_or_404()
    screenings = DonorHealthScreening.active_query().filter_by(donor_id=donor.id).order_by(DonorHealthScreening.screening_date.desc()).limit(5).all()
    donations = Donation.active_query().filter_by(donor_id=donor.id).order_by(Donation.donation_date.desc()).limit(10).all()
    badges = [b.badge for b in donor.badges if not b.is_deleted]

    return render_template(
        'donors/view.html',
        donor=donor,
        screenings=screenings,
        donations=donations,
        badges=badges
    )


@donors_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    donor = Donor.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()
    if not (user.is_admin or user.id == donor.user_id):
        abort(403)

    blood_groups = BloodGroup.active_query().order_by(BloodGroup.name).all()
    cities = City.active_query().order_by(City.name).all()
    hospitals = Hospital.active_query().order_by(Hospital.name).all()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        weight_kg = request.form.get('weight_kg', type=float)
        preferred_center_id = request.form.get('preferred_donation_center_id', type=int)

        if donor.user:
            donor.user.full_name = full_name
            donor.user.phone = phone
        donor.weight_kg = weight_kg or donor.weight_kg
        donor.preferred_donation_center_id = preferred_center_id
        donor.updated_by = user.id

        try:
            db.session.commit()
            log_audit(user.id, 'UPDATE', 'donors', donor.id)
            flash('Donor profile updated successfully.', 'success')
            return redirect(url_for('donors.view', id=donor.id))
        except Exception:
            db.session.rollback()
            flash('Failed to update donor.', 'danger')

    return render_template('donors/edit.html', donor=donor, blood_groups=blood_groups, cities=cities, hospitals=hospitals)


@donors_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete(id):
    donor = Donor.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()
    donor.soft_delete(user.id)
    if donor.user:
        donor.user.soft_delete(user.id)
    try:
        db.session.commit()
        log_audit(user.id, 'SOFT_DELETE', 'donors', donor.id)
        flash('Donor record has been soft-deleted.', 'warning')
    except Exception:
        db.session.rollback()
        flash('Failed to delete donor.', 'danger')

    return redirect(url_for('donors.index'))


@donors_bp.route('/<int:id>/screen', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'doctor', 'hospital_staff')
def screen(id):
    donor = Donor.active_query().filter_by(id=id).first_or_404()

    if request.method == 'POST':
        user = get_current_user()
        weight_kg = request.form.get('weight_kg', type=float)
        systolic_bp = request.form.get('systolic_bp', type=int)
        diastolic_bp = request.form.get('diastolic_bp', type=int)
        pulse_bpm = request.form.get('pulse_bpm', type=int)
        hemoglobin_level = request.form.get('hemoglobin_level', type=float)

        screening_errors = validate_donor_screening(weight_kg, systolic_bp, diastolic_bp, pulse_bpm, hemoglobin_level)
        is_eligible = len(screening_errors) == 0
        disqualification_reason = '; '.join(screening_errors) if screening_errors else None

        try:
            screening = DonorHealthScreening(
                donor_id=donor.id,
                screening_date=date.today(),
                weight_kg=weight_kg,
                systolic_bp=systolic_bp,
                diastolic_bp=diastolic_bp,
                pulse_bpm=pulse_bpm,
                hemoglobin_level=hemoglobin_level,
                is_eligible=is_eligible,
                disqualification_reason=disqualification_reason,
                screened_by_user_id=user.id,
                created_by=user.id
            )
            db.session.add(screening)

            # Update donor's status
            donor.weight_kg = weight_kg
            donor.donation_eligibility_status = 'Eligible' if is_eligible else 'Deferred'
            donor.updated_by = user.id

            db.session.commit()
            if is_eligible:
                flash(f'Donor passed screening! Status set to Eligible (Hb: {hemoglobin_level} g/dL).', 'success')
            else:
                flash(f'Donor deferred from donation: {disqualification_reason}', 'warning')
            return redirect(url_for('donors.view', id=donor.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error saving screening')
            flash('Error saving screening. Please check inputs and try again.', 'danger')

    return render_template('donors/screen.html', donor=donor)


@donors_bp.route('/<int:id>/availability', methods=['POST'])
@login_required
def update_availability(id):
    donor = Donor.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()
    if not (user.is_admin or user.id == donor.user_id):
        abort(403)

    is_emergency = bool(request.form.get('is_available_for_emergency'))
    radius = request.form.get('travel_radius_km', 25, type=int)
    time_slot = request.form.get('preferred_time_slot', 'Anytime')

    if not donor.availability:
        donor.availability = DonorAvailability(donor_id=donor.id)

    donor.availability.is_available_for_emergency = is_emergency
    donor.availability.travel_radius_km = radius
    donor.availability.preferred_time_slot = time_slot
    donor.availability.updated_by = user.id

    try:
        db.session.commit()
        flash('Availability settings updated.', 'success')
    except Exception:
        db.session.rollback()
        flash('Failed to update availability.', 'danger')

    return redirect(url_for('donors.view', id=donor.id))


@donors_bp.route('/badges')
def badges_view():
    badges = Badge.active_query().order_by(Badge.min_donations_required.asc()).all()
    top_donors = Donor.active_query().filter(Donor.total_donations > 0).order_by(Donor.total_donations.desc()).limit(10).all()
    return render_template('donors/badges.html', badges=badges, top_donors=top_donors)


@donors_bp.route('/emergency-matches')
@login_required
def emergency_matches():
    expire_emergency_broadcasts()
    user = get_current_user()
    if not user.is_donor or not user.donor_profile:
        flash('Only registered donors can access matched emergency requests.', 'warning')
        return redirect(url_for('main.dashboard'))

    donor = user.donor_profile
    matches = DonorMatch.active_query().filter_by(donor_id=donor.id).order_by(DonorMatch.notified_at.desc()).all()
    return render_template('donors/emergency_matches.html', matches=matches, donor=donor)


@donors_bp.route('/matches/<int:match_id>/respond', methods=['POST'])
@login_required
def respond_match(match_id):
    user = get_current_user()
    match = DonorMatch.active_query().filter_by(id=match_id).first_or_404()
    if not user.is_admin and (not user.donor_profile or match.donor_id != user.donor_profile.id):
        abort(403)

    action = request.form.get('action')  # 'Accepted' or 'Declined'
    remarks = request.form.get('remarks', '').strip()

    if action not in ('Accepted', 'Declined'):
        flash('Invalid response action.', 'danger')
        return redirect(url_for('donors.emergency_matches'))

    if match.status in ('Accepted', 'Declined', 'Timed Out'):
        flash('You have already submitted a final response for this emergency match.', 'info')
        return redirect(url_for('donors.emergency_matches'))

    em = match.emergency_request
    if not em or not em.is_broadcast_active or em.status in ('Fulfilled', 'Cancelled', 'Expired') or match.is_expired:
        flash('This emergency broadcast has expired or is no longer active.', 'warning')
        return redirect(url_for('donors.emergency_matches'))

    match.status = action
    match.responded_at = datetime.utcnow()
    match.updated_by = user.id

    response_log = ResponseLog(
        donor_match_id=match.id,
        donor_id=match.donor_id,
        action=action,
        remarks=remarks,
        created_by=user.id
    )
    db.session.add(response_log)

    try:
        db.session.commit()
        log_audit(user.id, f'MATCH_{action.upper()}', 'donor_matches', match.id)
        if action == 'Accepted':
            # Notify the request creator and hospital staff
            target_user_id = match.emergency_request.created_by if match.emergency_request else None
            if not target_user_id and match.emergency_request and match.emergency_request.blood_request:
                target_user_id = match.emergency_request.blood_request.created_by

            if target_user_id:
                bg_name = match.emergency_request.blood_group.name if (match.emergency_request and match.emergency_request.blood_group) else 'Blood'
                hosp_name = match.emergency_request.hospital.name if (match.emergency_request and match.emergency_request.hospital) else 'Hospital'
                create_notification(
                    user_id=target_user_id,
                    title="Donor Accepted Emergency Request! 🩸",
                    message=f"Donor {user.full_name} ({user.phone}) has accepted emergency request #{match.emergency_request_id} ({bg_name}) for {hosp_name}.",
                    notification_type="Emergency",
                    link_url=url_for('requests.emergency_view', id=match.emergency_request_id)
                )
            flash('Thank you for accepting! The hospital staff has been notified of your availability.', 'success')
        else:
            flash('Response recorded. Thank you for notifying us.', 'info')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Error recording match response')
        flash('Error recording response. Please try again.', 'danger')

    return redirect(url_for('donors.emergency_matches'))
