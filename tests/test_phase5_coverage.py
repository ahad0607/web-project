import pytest
from datetime import date, datetime, timedelta
from app import create_app
from app.extensions import db
from app.models.auth import User, Role
from app.models.hospital import Hospital, HospitalBloodBank, Doctor
from app.models.reference import BloodGroup
from app.models.donor import Donor
from app.models.patient import Patient
from app.models.inventory import BloodUnit
from app.models.request import BloodRequest, EmergencyRequest
from app.models.transfusion import TransfusionSchedule
from app.models.care import Appointment, Medication, PatientMedication
from app.utils import validate_phone, validate_email_format, validate_cnic
from app.services.donation_service import validate_donor_eligibility
from app.services.inventory_service import generate_unit_number, sync_blood_bank_stock
from app.services.transfusion_service import validate_transfusion_execution


def test_csrf_protection_enabled_rejects_missing_token():
    """Verify that when CSRF protection is enabled, POST requests without csrf_token fail with 400 Bad Request."""
    csrf_app = create_app('testing')
    csrf_app.config['WTF_CSRF_ENABLED'] = True

    with csrf_app.test_client() as client:
        # Attempt to post login without CSRF token
        resp = client.post('/auth/login', data={
            'username_or_email': 'admin',
            'password': 'AnyPassword123'
        })
        assert resp.status_code == 400
        assert b'CSRF' in resp.data or b'Bad Request' in resp.data or resp.status_code == 400


def test_validator_pakistan_formats_and_bounds():
    """Verify Pakistani phone, email, and CNIC validator helpers."""
    # Phone numbers
    assert validate_phone('03001234567') is True
    assert validate_phone('+923001234567') is True
    assert validate_phone('0300-1234567') is True
    assert validate_phone('021-34567890') is True
    assert validate_phone('12345') is False
    assert validate_phone('abcdefghijk') is False

    # Email
    assert validate_email_format('user@lifebridge.org') is True
    assert validate_email_format('invalid-email') is False
    assert validate_email_format('') is False

    # CNIC
    assert validate_cnic('42101-1234567-1') is True
    assert validate_cnic('4210112345671') is True
    assert validate_cnic('11111-1111111-1') is False  # Dummy identical digits
    assert validate_cnic('00000-0000000-0') is False  # Dummy identical digits
    assert validate_cnic('1234') is False


def test_donor_cooldown_and_eligibility_service(app):
    """Verify donation service correctly detects under-age, underweight, and cooldown periods."""
    with app.app_context():
        donor_role = Role.query.filter_by(slug='donor').first()
        if not donor_role:
            donor_role = Role(name='Donor', slug='donor')
            db.session.add(donor_role)
            db.session.flush()

        bg = BloodGroup.query.first() or BloodGroup(name='O+', can_donate_to='O+', can_receive_from='O+')
        db.session.add(bg)
        db.session.flush()

        # Underage donor (< 18)
        u1 = User(username='kid_donor', email='kid@test.com', full_name='Kid', phone='03001111111', role_id=donor_role.id)
        u1.set_password('Pass1234')
        db.session.add(u1)
        db.session.flush()

        d_young = Donor(user_id=u1.id, blood_group_id=bg.id, date_of_birth=date.today() - timedelta(days=16*365), gender='Male', weight_kg=60.0)
        is_el, reason = validate_donor_eligibility(d_young)
        assert is_el is False
        assert 'outside the eligible range' in reason

        # Underweight donor (< 50kg)
        u2 = User(username='light_donor', email='light@test.com', full_name='Light', phone='03002222222', role_id=donor_role.id)
        u2.set_password('Pass1234')
        db.session.add(u2)
        db.session.flush()

        d_light = Donor(user_id=u2.id, blood_group_id=bg.id, date_of_birth=date(1995, 1, 1), gender='Female', weight_kg=45.0)
        is_el, reason = validate_donor_eligibility(d_light)
        assert is_el is False
        assert 'below the minimum' in reason

        # Cooldown (< 90 days)
        u3 = User(username='recent_donor', email='recent@test.com', full_name='Recent', phone='03003333333', role_id=donor_role.id)
        u3.set_password('Pass1234')
        db.session.add(u3)
        db.session.flush()

        d_recent = Donor(user_id=u3.id, blood_group_id=bg.id, date_of_birth=date(1995, 1, 1), gender='Male', weight_kg=70.0, last_donation_date=date.today() - timedelta(days=30))
        is_el, reason = validate_donor_eligibility(d_recent)
        assert is_el is False
        assert 'minimum 90-day cooldown' in reason


def test_inventory_service_generation_and_sync(app):
    """Verify barcode format uniqueness and dynamic stock synchronization."""
    with app.app_context():
        num1 = generate_unit_number('B+')
        num2 = generate_unit_number('B+')
        assert num1.startswith('LB-BPOS-')
        assert num1 != num2

        h = Hospital(name='Aga Khan Hospital', license_number='AKUH-KHI', address='Stadium Road, Karachi', phone='021-111-911-911', total_beds=500)
        db.session.add(h)
        db.session.flush()

        bb = HospitalBloodBank(hospital_id=h.id, license_number='BB-AKUH', in_charge_name='Dr. Incharge', contact_phone='03001112233', current_stock_units=0)
        db.session.add(bb)
        db.session.flush()

        bg = BloodGroup.query.first() or BloodGroup(name='A+', can_donate_to='A+', can_receive_from='A+')
        db.session.add(bg)
        db.session.flush()

        u1 = BloodUnit(blood_bank_id=bb.id, unit_number=num1, blood_group_id=bg.id, donation_date=date.today(), expiry_date=date.today()+timedelta(days=30), status='Available')
        u2 = BloodUnit(blood_bank_id=bb.id, unit_number=num2, blood_group_id=bg.id, donation_date=date.today(), expiry_date=date.today()+timedelta(days=30), status='Reserved')
        db.session.add_all([u1, u2])
        db.session.commit()

        # Only Available counts in active stock
        stock = sync_blood_bank_stock(bb.id)
        assert stock == 1
        refetched_bb = db.session.get(HospitalBloodBank, bb.id)
        assert refetched_bb.current_stock_units == 1


def test_doctor_patient_isolation_and_dropdown_scoping(client, app):
    """Verify that a doctor only sees their assigned patients and cannot view other doctors' patients."""
    with app.app_context():
        doc_role = Role.query.filter_by(slug='doctor').first()
        if not doc_role:
            doc_role = Role(name='Doctor', slug='doctor')
            db.session.add(doc_role)
            db.session.flush()

        pat_role = Role.query.filter_by(slug='patient').first()
        if not pat_role:
            pat_role = Role(name='Patient', slug='patient')
            db.session.add(pat_role)
            db.session.flush()

        h = Hospital.query.first() or Hospital(name='Civil Hospital', license_number='CIV-01', address='Mission Road, Karachi', phone='021-99215740')
        db.session.add(h)
        db.session.flush()

        bg = BloodGroup.query.first() or BloodGroup(name='B+', can_donate_to='B+', can_receive_from='B+')
        db.session.add(bg)
        db.session.flush()

        # Doctor 1 & Doctor 2
        u_d1 = User(username='doc_one', email='d1@test.com', full_name='Dr. One', phone='03001111112', role_id=doc_role.id)
        u_d1.set_password('Pass1234')
        u_d2 = User(username='doc_two', email='d2@test.com', full_name='Dr. Two', phone='03001111113', role_id=doc_role.id)
        u_d2.set_password('Pass1234')
        db.session.add_all([u_d1, u_d2])
        db.session.flush()

        d1 = Doctor(user_id=u_d1.id, hospital_id=h.id, license_number='LIC-D1')
        d2 = Doctor(user_id=u_d2.id, hospital_id=h.id, license_number='LIC-D2')
        db.session.add_all([d1, d2])
        db.session.flush()

        # Patient assigned to Doctor 2
        u_p = User(username='pat_exclusive', email='pe@test.com', full_name='Patient Exclusive', phone='03001111114', role_id=pat_role.id)
        u_p.set_password('Pass1234')
        db.session.add(u_p)
        db.session.flush()

        p2 = Patient(user_id=u_p.id, mrn='THAL-EXCL', blood_group_id=bg.id, date_of_birth=date(2012, 1, 1), gender='Female', primary_doctor_id=d2.id, emergency_contact_name='G', emergency_contact_phone='123')
        db.session.add(p2)
        db.session.commit()
        p2_id = p2.id
        d1_user_id = u_d1.id

    # Doctor 1 logs in and attempts to access Patient 2's medical record
    with client.session_transaction() as sess:
        sess['user_id'] = d1_user_id
        sess['user_role'] = 'doctor'
        sess['user_name'] = 'Dr. One'

    resp = client.get(f'/patients/{p2_id}')
    assert resp.status_code == 403  # Doctor 1 is strictly forbidden from viewing Doctor 2's patient
