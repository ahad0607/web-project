from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.extensions import db
from app.utils import get_current_user, login_required
from app.models import (
    Patient,
    Donor,
    Hospital,
    HospitalBloodBank,
    BloodUnit,
    BloodRequest,
    EmergencyRequest,
    TransfusionSchedule,
    Appointment,
    Campaign,
    Notification,
    AuditLog,
    HemoglobinRecord,
    FerritinRecord
)

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def dashboard():
    user = get_current_user()
    today = date.today()

    # Aggregate common statistics
    total_patients = Patient.active_query().count()
    total_donors = Donor.active_query().count()
    total_units_available = BloodUnit.active_query().filter_by(status='Available').count()
    active_emergencies_count = EmergencyRequest.active_query().filter_by(is_broadcast_active=True).count()
    recent_campaigns = Campaign.active_query().filter(Campaign.end_date >= today).order_by(Campaign.start_date.asc()).limit(3).all()

    role_data = {}

    if user:
        if user.is_admin:
            role_data['total_hospitals'] = Hospital.active_query().count()
            role_data['pending_requests'] = BloodRequest.active_query().filter(BloodRequest.status.in_(['Pending', 'In Progress'])).count()
            role_data['recent_logs'] = AuditLog.active_query().order_by(AuditLog.created_at.desc()).limit(6).all()
            role_data['recent_requests'] = BloodRequest.active_query().order_by(BloodRequest.created_at.desc()).limit(5).all()

        elif user.is_doctor and user.doctor_profile:
            doc = user.doctor_profile
            role_data['my_patients'] = Patient.active_query().filter_by(primary_doctor_id=doc.id).limit(10).all()
            role_data['today_appointments'] = Appointment.active_query().filter_by(doctor_id=doc.id, appointment_date=today).all()
            role_data['upcoming_transfusions'] = TransfusionSchedule.active_query().filter_by(doctor_id=doc.id).filter(TransfusionSchedule.scheduled_date >= today).order_by(TransfusionSchedule.scheduled_date.asc()).limit(5).all()

        elif user.is_donor and user.donor_profile:
            donor = user.donor_profile
            role_data['donor'] = donor
            role_data['recent_matches'] = [m for m in donor.matches if not m.is_deleted and m.status == 'Notified'][:5]
            role_data['earned_badges'] = [b.badge for b in donor.badges if not b.is_deleted]

        elif user.is_patient and user.patient_profile:
            patient = user.patient_profile
            role_data['patient'] = patient
            role_data['next_schedule'] = TransfusionSchedule.active_query().filter_by(patient_id=patient.id).filter(TransfusionSchedule.scheduled_date >= today).order_by(TransfusionSchedule.scheduled_date.asc()).first()
            role_data['latest_hb'] = HemoglobinRecord.active_query().filter_by(patient_id=patient.id).order_by(HemoglobinRecord.test_date.desc()).first()
            role_data['latest_ferritin'] = FerritinRecord.active_query().filter_by(patient_id=patient.id).order_by(FerritinRecord.test_date.desc()).first()
            role_data['active_meds'] = [m for m in patient.patient_medications if not m.is_deleted and m.is_active]

        elif user.is_hospital_staff:
            req_q = BloodRequest.active_query().filter(BloodRequest.status.in_(['Pending', 'In Progress']))
            if user.hospital_id:
                req_q = req_q.filter(BloodRequest.hospital_id == user.hospital_id)
            role_data['pending_requests'] = req_q.order_by(BloodRequest.created_at.desc()).limit(5).all()

            exp_q = BloodUnit.active_query().filter(
                BloodUnit.status == 'Available',
                BloodUnit.expiry_date >= today,
                BloodUnit.expiry_date <= today + timedelta(days=7)
            )
            if user.hospital_id:
                exp_q = exp_q.join(HospitalBloodBank).filter(HospitalBloodBank.hospital_id == user.hospital_id)
            role_data['expiring_soon_units'] = exp_q.order_by(BloodUnit.expiry_date.asc()).limit(5).all()

    return render_template(
        'main/dashboard.html',
        total_patients=total_patients,
        total_donors=total_donors,
        total_units_available=total_units_available,
        active_emergencies_count=active_emergencies_count,
        recent_campaigns=recent_campaigns,
        role_data=role_data
    )


@main_bp.route('/notifications')
@login_required
def notifications():
    user = get_current_user()
    notifs = Notification.active_query().filter_by(user_id=user.id).order_by(Notification.created_at.desc()).all()
    return render_template('main/notifications.html', notifications=notifs)


@main_bp.route('/notifications/<int:id>/read', methods=['POST'])
@login_required
def mark_notification_read(id):
    user = get_current_user()
    notif = Notification.active_query().filter_by(id=id, user_id=user.id).first_or_404()
    notif.is_read = True
    db.session.commit()
    flash('Notification marked as read.', 'info')
    return redirect(url_for('main.notifications'))


@main_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    user = get_current_user()
    Notification.active_query().filter_by(user_id=user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    flash('All notifications marked as read.', 'info')
    return redirect(url_for('main.notifications'))


@main_bp.route('/about')
def about():
    return render_template('main/about.html')


@main_bp.route('/feedback', methods=['GET', 'POST'])
def feedback():
    from app.models.other import Feedback
    user = get_current_user()
    if request.method == 'POST':
        category = request.form.get('category', 'General')
        rating = request.form.get('rating', 5, type=int)
        comment = request.form.get('comment', '').strip()

        if not comment:
            flash('Comment cannot be empty.', 'danger')
        else:
            try:
                fb = Feedback(
                    user_id=user.id if user else None,
                    category=category,
                    rating=min(5, max(1, rating)),
                    comment=comment,
                    is_public=True,
                    created_by=user.id if user else None
                )
                db.session.add(fb)
                db.session.commit()
                flash('Thank you for your valuable feedback!', 'success')
                return redirect(url_for('main.feedback'))
            except Exception:
                db.session.rollback()
                current_app.logger.exception('Error submitting feedback')
                flash('Error submitting feedback. Please try again.', 'danger')

    feedbacks = Feedback.active_query().filter_by(is_public=True).order_by(Feedback.created_at.desc()).limit(30).all()
    return render_template('main/feedback.html', feedbacks=feedbacks)
