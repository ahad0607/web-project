from datetime import datetime, date, timedelta
import secrets
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models import (
    Campaign,
    CampaignParticipant,
    Donation,
    Hospital,
    City,
    Area,
    Donor,
    BloodGroup,
    BloodUnit,
    InventoryTransaction
)
from app.utils import (
    get_current_user,
    login_required,
    role_required,
    log_audit
)
from app.services.inventory_service import sync_blood_bank_stock, generate_unit_number
from app.services.donation_service import validate_donor_eligibility, check_and_award_donor_badges

campaigns_bp = Blueprint('campaigns', __name__)


@campaigns_bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '').strip()

    query = Campaign.active_query().options(
        joinedload(Campaign.hospital),
        joinedload(Campaign.city)
    )

    if status:
        query = query.filter(Campaign.status == status)

    pagination = query.order_by(Campaign.start_date.desc()).paginate(page=page, per_page=9, error_out=False)

    return render_template('campaigns/index.html', pagination=pagination, campaigns=pagination.items, selected_status=status)


@campaigns_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'hospital_staff')
def create():
    hospitals = Hospital.active_query().all()
    cities = City.active_query().all()

    if request.method == 'POST':
        user = get_current_user()
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        hospital_id = request.form.get('hospital_id', type=int)
        city_id = request.form.get('city_id', type=int)
        venue = request.form.get('venue', '').strip()
        start_date_str = request.form.get('start_date', '')
        end_date_str = request.form.get('end_date', '')
        target_units = request.form.get('target_units', 100, type=int)

        if not title or not venue or not start_date_str or not end_date_str or not hospital_id:
            flash('Please complete all mandatory campaign fields.', 'danger')
            return render_template('campaigns/create.html', hospitals=hospitals, cities=cities)

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            if end_date < start_date:
                flash('Campaign end date cannot be earlier than start date.', 'danger')
                return render_template('campaigns/create.html', hospitals=hospitals, cities=cities)

            campaign = Campaign(
                title=title,
                description=description,
                hospital_id=hospital_id,
                city_id=city_id,
                venue=venue,
                start_date=start_date,
                end_date=end_date,
                target_units=target_units or 100,
                collected_units=0,
                status='Upcoming' if start_date > date.today() else 'Ongoing',
                created_by=user.id
            )
            db.session.add(campaign)
            db.session.commit()
            log_audit(user.id, 'CREATE', 'campaigns', campaign.id, None, {'title': title})
            flash(f'Campaign "{title}" organized successfully.', 'success')
            return redirect(url_for('campaigns.view', id=campaign.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error creating campaign')
            flash('Error creating campaign. Please verify dates and details.', 'danger')

    return render_template('campaigns/create.html', hospitals=hospitals, cities=cities)


@campaigns_bp.route('/<int:id>')
def view(id):
    campaign = Campaign.active_query().filter_by(id=id).first_or_404()
    participants = CampaignParticipant.active_query().filter_by(campaign_id=campaign.id).all()
    donations = Donation.active_query().filter_by(campaign_id=campaign.id).order_by(Donation.donation_date.desc()).limit(10).all()
    
    # Restrict donor list exposure: only staff/admin can view donor list for recording
    user = get_current_user()
    if user and (user.is_admin or user.is_hospital_staff):
        donors = Donor.active_query().all()
    else:
        donors = []

    blood_groups = BloodGroup.active_query().all()

    return render_template(
        'campaigns/view.html',
        campaign=campaign,
        participants=participants,
        donations=donations,
        donors=donors,
        blood_groups=blood_groups
    )


@campaigns_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'hospital_staff')
def edit(id):
    campaign = Campaign.active_query().filter_by(id=id).first_or_404()
    hospitals = Hospital.active_query().all()
    cities = City.active_query().all()

    if request.method == 'POST':
        user = get_current_user()
        campaign.title = request.form.get('title', '').strip()
        campaign.description = request.form.get('description', '').strip()
        campaign.venue = request.form.get('venue', '').strip()
        campaign.target_units = request.form.get('target_units', type=int)
        campaign.status = request.form.get('status', 'Ongoing')
        campaign.updated_by = user.id

        try:
            db.session.commit()
            log_audit(user.id, 'UPDATE', 'campaigns', campaign.id)
            flash('Campaign updated.', 'success')
            return redirect(url_for('campaigns.view', id=campaign.id))
        except Exception:
            db.session.rollback()
            flash('Update failed.', 'danger')

    return render_template('campaigns/edit.html', campaign=campaign, hospitals=hospitals, cities=cities)


@campaigns_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete(id):
    campaign = Campaign.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()
    campaign.soft_delete(user.id)
    try:
        db.session.commit()
        log_audit(user.id, 'SOFT_DELETE', 'campaigns', campaign.id)
        flash('Campaign soft-deleted.', 'warning')
    except Exception:
        db.session.rollback()
        flash('Delete failed.', 'danger')

    return redirect(url_for('campaigns.index'))


@campaigns_bp.route('/<int:id>/join', methods=['POST'])
@login_required
def join(id):
    campaign = Campaign.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()

    # Block joining completed or cancelled campaigns
    if campaign.status in ('Completed', 'Cancelled'):
        flash(f'Cannot join campaign because it is {campaign.status.lower()}.', 'warning')
        return redirect(url_for('campaigns.view', id=campaign.id))

    role_in_camp = request.form.get('role', 'Volunteer').strip()
    allowed_roles = ['Donor', 'Volunteer', 'Organizer']
    if role_in_camp not in allowed_roles:
        role_in_camp = 'Volunteer'

    existing = CampaignParticipant.active_query().filter_by(campaign_id=campaign.id, user_id=user.id).first()
    if existing:
        flash('You are already registered for this campaign!', 'info')
        return redirect(url_for('campaigns.view', id=campaign.id))

    try:
        part = CampaignParticipant(
            campaign_id=campaign.id,
            user_id=user.id,
            role_in_campaign=role_in_camp,
            created_by=user.id
        )
        db.session.add(part)
        db.session.commit()
        flash(f'Successfully registered for "{campaign.title}" as {role_in_camp}!', 'success')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to join campaign')
        flash('Failed to join campaign. Please try again.', 'danger')

    return redirect(url_for('campaigns.view', id=campaign.id))


@campaigns_bp.route('/<int:id>/record-donation', methods=['POST'])
@login_required
@role_required('admin', 'hospital_staff')
def record_donation(id):
    campaign = Campaign.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()
    donor_id = request.form.get('donor_id', type=int)
    blood_group_id = request.form.get('blood_group_id', type=int)
    volume_ml = request.form.get('volume_ml', 450, type=int)

    today = date.today()

    # Validate campaign active status and date window
    if campaign.status != 'Ongoing':
        flash(f'Cannot record donations: campaign status is "{campaign.status}" (must be Ongoing).', 'warning')
        return redirect(url_for('campaigns.view', id=campaign.id))
    if not (campaign.start_date <= today <= campaign.end_date):
        flash(f'Cannot record donations: today ({today}) is outside the campaign active dates ({campaign.start_date} to {campaign.end_date}).', 'warning')
        return redirect(url_for('campaigns.view', id=campaign.id))

    donor = Donor.get_by_id(donor_id)
    if not donor:
        flash('Donor not found.', 'danger')
        return redirect(url_for('campaigns.view', id=campaign.id))

    # Validate clinical eligibility
    if not (18 <= (donor.age or 0) <= 60):
        flash(f'Donor age ({donor.age or "unknown"}) is outside the eligible range (18-60 years).', 'danger')
        return redirect(url_for('campaigns.view', id=campaign.id))
    if (donor.weight_kg or 0) < 50.0:
        flash(f'Donor weight ({donor.weight_kg}kg) is below minimum requirement (50kg).', 'danger')
        return redirect(url_for('campaigns.view', id=campaign.id))
    if donor.last_donation_date and donor.days_since_last_donation < 90:
        days_left = 90 - donor.days_since_last_donation
        flash(f'Donor must wait {days_left} more day(s) before donating again (minimum 90-day cooldown).', 'danger')
        return redirect(url_for('campaigns.view', id=campaign.id))
    if donor.donation_eligibility_status != 'Eligible':
        flash(f'Donor status is "{donor.donation_eligibility_status}". Only "Eligible" donors can donate.', 'danger')
        return redirect(url_for('campaigns.view', id=campaign.id))

    # Validate hospital blood bank
    bb = campaign.hospital.blood_bank
    if not bb:
        flash(f'Hospital "{campaign.hospital.name}" does not have an active blood bank to receive units.', 'danger')
        return redirect(url_for('campaigns.view', id=campaign.id))

    try:
        # 1. Create BloodUnit in hospital blood bank with collision-free unit number
        bg_target_id = blood_group_id or donor.blood_group_id
        bg_obj = BloodGroup.get_by_id(bg_target_id)
        unit_num = generate_unit_number(bg_obj.name if bg_obj else 'UNK')

        unit = BloodUnit(
            blood_bank_id=bb.id,
            unit_number=unit_num,
            blood_group_id=bg_target_id,
            component_type='PRBC',
            donation_date=today,
            expiry_date=today + timedelta(days=35),
            donor_id=donor.id,
            volume_ml=volume_ml or 450,
            status='Available',
            storage_location='Campaign Collection Box',
            created_by=user.id
        )
        db.session.add(unit)
        db.session.flush()

        tx = InventoryTransaction(
            blood_bank_id=bb.id,
            blood_unit_id=unit.id,
            transaction_type='IN_DONATION',
            quantity=1,
            reason=f"Drive collection from campaign #{campaign.id} ({campaign.title})",
            performed_by_user_id=user.id,
            created_by=user.id
        )
        db.session.add(tx)

        # 2. Record Donation event
        donation = Donation(
            donor_id=donor.id,
            hospital_id=campaign.hospital_id,
            campaign_id=campaign.id,
            blood_unit_id=unit.id,
            donation_date=today,
            blood_group_id=bg_target_id,
            donation_type='Voluntary',
            volume_ml=volume_ml or 450,
            created_by=user.id
        )
        db.session.add(donation)

        # 3. Update donor counts and campaign metrics
        donor.total_donations += 1
        donor.last_donation_date = today
        campaign.collected_units += 1

        # Sync blood bank dynamic stock
        sync_blood_bank_stock(bb.id)

        # Check badges
        check_and_award_donor_badges(donor)

        db.session.commit()
        log_audit(user.id, 'RECORD_CAMPAIGN_DONATION', 'donations', donation.id)
        flash(f'Donation from {donor.full_name} recorded! Unit {unit_num} added to {bb.bank_name}. Total units: {campaign.collected_units}.', 'success')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to record campaign donation')
        flash('Failed to record donation. Please try again.', 'danger')

    return redirect(url_for('campaigns.view', id=campaign.id))
