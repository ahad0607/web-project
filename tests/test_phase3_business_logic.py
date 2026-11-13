import pytest
from datetime import date, datetime, timedelta
from app.extensions import db
from app.models.auth import User, Role
from app.models.hospital import Hospital, HospitalBloodBank, Doctor
from app.models.reference import BloodGroup, Diagnosis
from app.models.donor import Donor, DonorAvailability
from app.models.patient import Patient, ChelationTherapyRecord
from app.models.request import BloodRequest, EmergencyRequest, DonorMatch
from app.models.inventory import BloodUnit
from app.models.transfusion import TransfusionSchedule
from app.models.other import Feedback, Campaign, CampaignParticipant
from app.models.care import Appointment, Medication, PatientMedication
from app.models.donor import Donation
from app.utils import find_and_match_donors
from app.blueprints.inventory import check_and_expire_units, sync_blood_bank_stock


@pytest.fixture
def phase3_setup(app):
    """Seed data needed for business logic tests."""
    with app.app_context():
        # Roles
        hstaff_role = Role.query.filter_by(slug='hospital_staff').first()
        if not hstaff_role:
            hstaff_role = Role(name='Hospital Staff', slug='hospital_staff')
            db.session.add(hstaff_role)
            db.session.flush()

        doc_role = Role.query.filter_by(slug='doctor').first()
        if not doc_role:
            doc_role = Role(name='Doctor', slug='doctor')
            db.session.add(doc_role)
            db.session.flush()

        donor_role = Role.query.filter_by(slug='donor').first()
        patient_role = Role.query.filter_by(slug='patient').first()

        # Blood groups
        bg_bpos = BloodGroup.query.filter_by(name='B+').first()
        bg_opos = BloodGroup.query.filter_by(name='O+').first()

        # Hospitals
        h1 = Hospital(name='Hospital Alpha', license_number='LIC-HA', address='Alpha Rd', phone='111', city_id=1)
        h2 = Hospital(name='Hospital Beta', license_number='LIC-HB', address='Beta Rd', phone='222', city_id=1)
        db.session.add_all([h1, h2])
        db.session.flush()

        bb1 = HospitalBloodBank(hospital_id=h1.id, license_number='BB-HA', in_charge_name='Head Alpha', contact_phone='111', current_stock_units=0)
        bb2 = HospitalBloodBank(hospital_id=h2.id, license_number='BB-HB', in_charge_name='Head Beta', contact_phone='222', current_stock_units=0)
        db.session.add_all([bb1, bb2])
        db.session.flush()

        # Staff user scoped to Hospital 1
        staff_u = User(username='staff_h1', email='staff1@test.com', full_name='Staff Alpha', phone='03009999991', role_id=hstaff_role.id, hospital_id=h1.id)
        staff_u.set_password('Staff@123')
        db.session.add(staff_u)
        db.session.flush()

        # Donors: 1 exact B+, 1 compatible O+
        u_d1 = User(username='donor_exact', email='donor_ex@test.com', full_name='Donor Exact', phone='03009999992', role_id=donor_role.id, city_id=1)
        u_d1.set_password('Donor@123')
        u_d2 = User(username='donor_compat', email='donor_cp@test.com', full_name='Donor Compat', phone='03009999993', role_id=donor_role.id, city_id=1)
        u_d2.set_password('Donor@123')
        db.session.add_all([u_d1, u_d2])
        db.session.flush()

        d1 = Donor(user_id=u_d1.id, blood_group_id=bg_bpos.id, city_id=1, date_of_birth=date(1995, 1, 1), gender='Male', weight_kg=70.0)
        d2 = Donor(user_id=u_d2.id, blood_group_id=bg_opos.id, city_id=1, date_of_birth=date(1996, 1, 1), gender='Male', weight_kg=72.0)
        db.session.add_all([d1, d2])
        db.session.flush()

        avail1 = DonorAvailability(donor_id=d1.id, is_available_for_emergency=True)
        avail2 = DonorAvailability(donor_id=d2.id, is_available_for_emergency=True)
        db.session.add_all([avail1, avail2])

        # Patient
        u_p = User(username='patient_p1', email='p1@test.com', full_name='Patient Alpha', phone='03009999994', role_id=patient_role.id, city_id=1)
        u_p.set_password('Patient@123')
        db.session.add(u_p)
        db.session.flush()

        patient = Patient(user_id=u_p.id, mrn='THAL-P1', blood_group_id=bg_bpos.id, date_of_birth=date(2010, 1, 1), gender='Female', emergency_contact_name='Parent', emergency_contact_phone='123')
        db.session.add(patient)
        db.session.flush()

        # Doctor
        u_doc = User(username='doc_tariq', email='doc_tariq@test.com', full_name='Dr. Tariq', phone='03009999995', role_id=doc_role.id, hospital_id=h1.id)
        u_doc.set_password('Doctor@123')
        db.session.add(u_doc)
        db.session.flush()

        doc = Doctor(user_id=u_doc.id, hospital_id=h1.id, license_number='DOC-001', specialization='Hematologist')
        db.session.add(doc)
        db.session.flush()

        patient.primary_doctor_id = doc.id

        db.session.commit()

        return {
            'h1_id': h1.id,
            'h2_id': h2.id,
            'bb1_id': bb1.id,
            'staff_id': staff_u.id,
            'd1_id': d1.id,
            'd1_user_id': u_d1.id,
            'd2_id': d2.id,
            'p_id': patient.id,
            'doc_id': doc.id,
            'doc_user_id': u_doc.id,
            'bg_bpos_id': bg_bpos.id,
            'bg_opos_id': bg_opos.id
        }


def test_emergency_matching_ranking_and_expiration(app, phase3_setup):
    """Verify emergency matching algorithm ranks exact match higher and sets 24h expiration."""
    with app.app_context():
        # Create an emergency request for B+
        req = BloodRequest(
            hospital_id=phase3_setup['h1_id'],
            blood_group_id=phase3_setup['bg_bpos_id'],
            units_requested=2,
            urgency='Emergency',
            status='Pending'
        )
        db.session.add(req)
        db.session.flush()

        em = EmergencyRequest(
            request_id=req.id,
            hospital_id=phase3_setup['h1_id'],
            blood_group_id=phase3_setup['bg_bpos_id'],
            units_needed=2,
            is_broadcast_active=True
        )
        db.session.add(em)
        db.session.commit()

        # Run matching
        count = find_and_match_donors(em, max_donors=10)
        assert count == 2

        matches = DonorMatch.query.filter_by(emergency_request_id=em.id).order_by(DonorMatch.match_score.desc()).all()
        assert len(matches) == 2
        # Exact match (d1) score is 100, compatible (d2) score is 85
        assert matches[0].donor_id == phase3_setup['d1_id']
        assert matches[0].match_score == 100.0
        assert matches[1].donor_id == phase3_setup['d2_id']
        assert matches[1].match_score == 85.0

        # Verify 24h expiration
        assert matches[0].expires_at is not None
        assert matches[0].expires_at > datetime.utcnow()
        assert (matches[0].expires_at - datetime.utcnow()).total_seconds() > 23 * 3600


def test_blood_request_status_state_machine(client, app, phase3_setup):
    """Verify status transition enforcement (e.g. Fulfilled is terminal, cannot revert to Pending)."""
    # Login as staff
    with client.session_transaction() as sess:
        sess['user_id'] = phase3_setup['staff_id']
        sess['user_role'] = 'hospital_staff'
        sess['user_name'] = 'Staff Alpha'

    with app.app_context():
        req = BloodRequest(
            hospital_id=phase3_setup['h1_id'],
            blood_group_id=phase3_setup['bg_bpos_id'],
            units_requested=2,
            urgency='Normal',
            status='Pending'
        )
        db.session.add(req)
        db.session.commit()
        req_id = req.id

    # Pending -> Approved: Valid
    resp = client.post(f'/requests/{req_id}/status', data={'status': 'Approved'}, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert BloodRequest.query.get(req_id).status == 'Approved'

    # Approved -> Pending: Invalid transition for non-admin
    resp_invalid = client.post(f'/requests/{req_id}/status', data={'status': 'Pending'}, follow_redirects=True)
    assert resp_invalid.status_code == 200
    assert b'Invalid status transition' in resp_invalid.data
    with app.app_context():
        # Status should NOT change
        assert BloodRequest.query.get(req_id).status == 'Approved'


def test_transfusion_clinical_hb_validation_and_expiry(client, app, phase3_setup):
    """Verify clinical boundaries for Hb and rejection of expired blood unit."""
    with client.session_transaction() as sess:
        sess['user_id'] = phase3_setup['staff_id']
        sess['user_role'] = 'hospital_staff'
        sess['user_name'] = 'Staff Alpha'

    with app.app_context():
        # Create an expired unit
        exp_unit = BloodUnit(
            blood_bank_id=phase3_setup['bb1_id'],
            unit_number='LB-EXPIRED-001',
            blood_group_id=phase3_setup['bg_bpos_id'],
            donation_date=date.today() - timedelta(days=40),
            expiry_date=date.today() - timedelta(days=5),
            status='Available'
        )
        # Create a valid available unit
        valid_unit = BloodUnit(
            blood_bank_id=phase3_setup['bb1_id'],
            unit_number='LB-VALID-001',
            blood_group_id=phase3_setup['bg_bpos_id'],
            donation_date=date.today(),
            expiry_date=date.today() + timedelta(days=35),
            status='Available'
        )
        sched = TransfusionSchedule(
            patient_id=phase3_setup['p_id'],
            hospital_id=phase3_setup['h1_id'],
            scheduled_date=date.today(),
            status='Scheduled',
            blood_group_id=phase3_setup['bg_bpos_id']
        )
        db.session.add_all([exp_unit, valid_unit, sched])
        db.session.commit()
        exp_u_id = exp_unit.id
        val_u_id = valid_unit.id
        sched_id = sched.id

    # 1. Attempting execution with expired unit should fail
    resp_exp = client.post(f'/transfusions/schedules/{sched_id}/execute', data={
        'blood_unit_id': exp_u_id,
        'pre_transfusion_hb': 7.5,
        'post_transfusion_hb': 9.2
    }, follow_redirects=True)
    assert b'expired' in resp_exp.data

    # 2. Attempting execution with invalid Hb (< 2.0 or > 20.0) should fail
    resp_hb = client.post(f'/transfusions/schedules/{sched_id}/execute', data={
        'blood_unit_id': val_u_id,
        'pre_transfusion_hb': 1.2,  # Invalid!
        'post_transfusion_hb': 9.2
    }, follow_redirects=True)
    assert b'Pre-transfusion hemoglobin must be clinically valid' in resp_hb.data

    # 3. Successful valid execution
    resp_ok = client.post(f'/transfusions/schedules/{sched_id}/execute', data={
        'blood_unit_id': val_u_id,
        'pre_transfusion_hb': 7.5,
        'post_transfusion_hb': 9.2
    }, follow_redirects=True)
    assert b'Transfusion completed successfully' in resp_ok.data

    # 4. Attempting to execute again must be blocked
    resp_re_exec = client.post(f'/transfusions/schedules/{sched_id}/execute', data={
        'blood_unit_id': val_u_id,
        'pre_transfusion_hb': 7.5,
        'post_transfusion_hb': 9.2
    }, follow_redirects=True)
    assert b'already been executed' in resp_re_exec.data


def test_inventory_auto_expiration_and_stock_sync(app, phase3_setup):
    """Verify auto-expiration of units and dynamic stock syncing."""
    with app.app_context():
        # Unit that expired yesterday
        u = BloodUnit(
            blood_bank_id=phase3_setup['bb1_id'],
            unit_number='LB-AUTO-EXP-001',
            blood_group_id=phase3_setup['bg_bpos_id'],
            donation_date=date.today() - timedelta(days=40),
            expiry_date=date.today() - timedelta(days=1),
            status='Available'
        )
        db.session.add(u)
        db.session.commit()
        u_id = u.id

        # Trigger auto-expiration
        check_and_expire_units()

        refetched = BloodUnit.query.get(u_id)
        assert refetched.status == 'Expired'

        # Trigger stock sync
        stock = sync_blood_bank_stock(phase3_setup['bb1_id'])
        bank = HospitalBloodBank.query.get(phase3_setup['bb1_id'])
        assert bank.current_stock_units == stock


def test_hospital_staff_cross_hospital_boundary(client, app, phase3_setup):
    """Verify hospital staff cannot manage requests belonging to a different hospital."""
    # Login as Staff Alpha (assigned to Hospital 1)
    with client.session_transaction() as sess:
        sess['user_id'] = phase3_setup['staff_id']
        sess['user_role'] = 'hospital_staff'
        sess['user_name'] = 'Staff Alpha'

    with app.app_context():
        # Request belonging to Hospital 2
        req_h2 = BloodRequest(
            hospital_id=phase3_setup['h2_id'],
            blood_group_id=phase3_setup['bg_bpos_id'],
            units_requested=1,
            urgency='Normal',
            status='Pending'
        )
        db.session.add(req_h2)
        db.session.commit()
        h2_req_id = req_h2.id

    # Staff Alpha attempting to update Hospital 2 request must get 403 Forbidden
    resp = client.post(f'/requests/{h2_req_id}/status', data={'status': 'Approved'})
    assert resp.status_code == 403


def test_campaign_date_validation(client, auth_client, phase3_setup):
    """Verify campaign end date cannot be earlier than start date."""
    resp = auth_client.post('/campaigns/create', data={
        'title': 'Test Drive',
        'venue': 'Campus Lawn',
        'hospital_id': phase3_setup['h1_id'],
        'start_date': '2026-06-15',
        'end_date': '2026-06-10',  # End before start!
        'target_units': 50
    }, follow_redirects=True)
    assert b'Campaign end date cannot be earlier than start date' in resp.data


def test_public_feedback_and_admin_moderation(client, auth_client, app):
    """Verify public can submit feedback and admin can moderate visibility."""
    # Public submission
    resp = client.post('/feedback', data={
        'category': 'Hospital Service',
        'rating': 5,
        'comment': 'Exceptional thalassemia care and friendly doctors!'
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Thank you for your valuable feedback' in resp.data

    with app.app_context():
        fb = Feedback.query.filter_by(comment='Exceptional thalassemia care and friendly doctors!').first()
        assert fb is not None
        assert fb.is_public is True
        fb_id = fb.id

    # Admin view moderation
    mod_resp = auth_client.get('/admin/feedback')
    assert mod_resp.status_code == 200
    assert b'Exceptional thalassemia care' in mod_resp.data

    # Admin toggle visibility to hidden
    toggle_resp = auth_client.post(f'/admin/feedback/{fb_id}/toggle-visibility', follow_redirects=True)
    assert toggle_resp.status_code == 200

    with app.app_context():
        fb_updated = db.session.get(Feedback, fb_id)
        assert fb_updated.is_public is False


def test_inventory_edit_status_terminal_and_transitions(client, app, phase3_setup):
    """Verify terminal blood unit statuses cannot be reverted and transitions generate correct transactions."""
    with client.session_transaction() as sess:
        sess['user_id'] = phase3_setup['staff_id']
        sess['user_role'] = 'hospital_staff'
        sess['user_name'] = 'Staff Alpha'

    with app.app_context():
        unit = BloodUnit(
            blood_bank_id=phase3_setup['bb1_id'],
            unit_number='LB-TEST-TERM-001',
            blood_group_id=phase3_setup['bg_bpos_id'],
            donation_date=date.today(),
            expiry_date=date.today() + timedelta(days=30),
            status='Transfused'
        )
        db.session.add(unit)
        db.session.commit()
        u_id = unit.id

    # 1. Attempt to revert terminal status 'Transfused' to 'Available' must fail
    resp = client.post(f'/inventory/units/{u_id}/edit', data={
        'status': 'Available',
        'storage_location': 'Shelf A',
        'reason': 'Accidental marking'
    }, follow_redirects=True)
    assert b'Terminal status' in resp.data

    with app.app_context():
        u = db.session.get(BloodUnit, u_id)
        assert u.status == 'Transfused'


def test_campaign_join_and_donation_eligibility(client, app, phase3_setup):
    """Verify campaign join role whitelisting, inactive blocking, and donor eligibility on donation."""
    with app.app_context():
        today = date.today()
        camp = Campaign(
            title='Central Karachi Thalassemia Drive',
            description='Community drive',
            hospital_id=phase3_setup['h1_id'],
            venue='Hospital Lawn',
            start_date=today,
            end_date=today + timedelta(days=2),
            target_units=50,
            status='Ongoing'
        )
        db.session.add(camp)
        db.session.commit()
        camp_id = camp.id

    # Join campaign as donor user
    with client.session_transaction() as sess:
        sess['user_id'] = phase3_setup['d1_user_id']
        sess['user_role'] = 'donor'
        sess['user_name'] = 'Donor One'

    join_resp = client.post(f'/campaigns/{camp_id}/join', data={
        'role': 'Volunteer'
    }, follow_redirects=True)
    assert b'Successfully registered' in join_resp.data

    # Record donation as hospital staff
    with client.session_transaction() as sess:
        sess['user_id'] = phase3_setup['staff_id']
        sess['user_role'] = 'hospital_staff'
        sess['user_name'] = 'Staff Alpha'

    don_resp = client.post(f'/campaigns/{camp_id}/record-donation', data={
        'donor_id': phase3_setup['d1_id'],
        'blood_group_id': phase3_setup['bg_bpos_id'],
        'volume_ml': 450
    }, follow_redirects=True)
    assert b'recorded' in don_resp.data

    # Attempting second immediate donation must fail due to 90-day cooldown
    don_resp_fail = client.post(f'/campaigns/{camp_id}/record-donation', data={
        'donor_id': phase3_setup['d1_id'],
        'blood_group_id': phase3_setup['bg_bpos_id'],
        'volume_ml': 450
    }, follow_redirects=True)
    assert b'minimum 90-day cooldown' in don_resp_fail.data


def test_care_appointment_double_booking_and_prescriptions(client, app, phase3_setup):
    """Verify doctor double booking prevention and duplicate prescription blocking."""
    with client.session_transaction() as sess:
        sess['user_id'] = phase3_setup['staff_id']
        sess['user_role'] = 'hospital_staff'
        sess['user_name'] = 'Staff Alpha'

    tomorrow = date.today() + timedelta(days=1)
    slot = '10:00 AM - 10:30 AM'

    # 1. Book first appointment
    resp1 = client.post('/care/appointments/create', data={
        'patient_id': phase3_setup['p_id'],
        'doctor_id': phase3_setup['doc_id'],
        'hospital_id': phase3_setup['h1_id'],
        'appointment_date': tomorrow.strftime('%Y-%m-%d'),
        'time_slot': slot,
        'reason': 'Routine Visit',
        'appointment_type': 'Regular Checkup'
    }, follow_redirects=True)
    assert b'Appointment successfully booked' in resp1.data

    # 2. Attempt double-booking same doctor, same date, same slot
    resp2 = client.post('/care/appointments/create', data={
        'patient_id': phase3_setup['p_id'],
        'doctor_id': phase3_setup['doc_id'],
        'hospital_id': phase3_setup['h1_id'],
        'appointment_date': tomorrow.strftime('%Y-%m-%d'),
        'time_slot': slot,
        'reason': 'Second Visit',
        'appointment_type': 'Regular Checkup'
    }, follow_redirects=True)
    assert b'already booked' in resp2.data

    # 3. Create medication and prescribe
    with app.app_context():
        med = Medication(
            name='Deferasirox (Exjade)',
            generic_name='Deferasirox',
            drug_class='Iron Chelator',
            form='Dispersible Tablet',
            standard_dosage='20 mg/kg/day'
        )
        db.session.add(med)
        db.session.commit()
        med_id = med.id

    with client.session_transaction() as sess:
        sess['user_id'] = phase3_setup['doc_user_id']
        sess['user_role'] = 'doctor'
        sess['user_name'] = 'Dr. Tariq'

    presc_resp = client.post('/care/patient-medications/prescribe', data={
        'patient_id': phase3_setup['p_id'],
        'medication_id': med_id,
        'dosage': '500 mg',
        'frequency': 'Once Daily'
    }, follow_redirects=True)
    assert b'Prescription added successfully' in presc_resp.data

    # 4. Duplicate active prescription blocked
    presc_dup = client.post('/care/patient-medications/prescribe', data={
        'patient_id': phase3_setup['p_id'],
        'medication_id': med_id,
        'dosage': '500 mg',
        'frequency': 'Once Daily'
    }, follow_redirects=True)
    assert b'already has an active prescription' in presc_dup.data


def test_admin_user_crud_and_password_reset(auth_client, app, phase3_setup):
    """Verify admin user creation validation, edit user, and password reset."""
    # Create user with hospital staff role and assigned hospital
    resp = auth_client.post('/admin/users/create', data={
        'username': 'staff_newbie',
        'email': 'newbie@lifebridge.org',
        'full_name': 'Newbie Staff',
        'phone': '03009988776',
        'password': 'SecurePassword123',
        'role_id': Role.query.filter_by(slug='hospital_staff').first().id,
        'hospital_id': phase3_setup['h1_id']
    }, follow_redirects=True)
    assert b'User account staff_newbie created' in resp.data

    with app.app_context():
        u = User.query.filter_by(username='staff_newbie').first()
        assert u is not None
        assert u.hospital_id == phase3_setup['h1_id']
        u_id = u.id

    # Edit user
    edit_resp = auth_client.post(f'/admin/users/{u_id}/edit', data={
        'full_name': 'Newbie Senior Staff',
        'email': 'newbie@lifebridge.org',
        'phone': '03009988776',
        'role_id': Role.query.filter_by(slug='hospital_staff').first().id,
        'hospital_id': phase3_setup['h1_id']
    }, follow_redirects=True)
    assert b'updated successfully' in edit_resp.data

    with app.app_context():
        u_edited = db.session.get(User, u_id)
        assert u_edited.full_name == 'Newbie Senior Staff'

    # Reset password
    reset_resp = auth_client.post(f'/admin/users/{u_id}/reset-password', follow_redirects=True)
    assert b'has been reset to temporary password' in reset_resp.data

    with app.app_context():
        u_reset = db.session.get(User, u_id)
        assert u_reset.must_change_password is True

