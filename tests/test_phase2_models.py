import pytest
from app.extensions import db
from app.models.auth import User, Role
from app.models.inventory import BloodUnit
from app.models.reference import BloodGroup, Diagnosis
from app.models.hospital import Hospital, HospitalBloodBank, Doctor, DoctorSchedule
from app.models.patient import Patient, PatientDiagnosis
from datetime import date, timedelta
from sqlalchemy.exc import IntegrityError


def test_domain_status_preservation_on_soft_delete(app):
    """Verify that BaseModel.record_status soft-delete does not overwrite domain status."""
    with app.app_context():
        h = Hospital(name='Test H', license_number='LIC-H1', address='Addr', phone='123')
        db.session.add(h)
        db.session.flush()

        hbb = HospitalBloodBank(hospital_id=h.id, license_number='LIC-HBB1', in_charge_name='Dr InCharge', contact_phone='03001234567')
        db.session.add(hbb)
        db.session.flush()

        bg = BloodGroup.query.first()
        unit = BloodUnit(
            blood_bank_id=hbb.id,
            unit_number='LB-TEST-STATUS-001',
            blood_group_id=bg.id,
            component_type='PRBC',
            donation_date=date.today(),
            expiry_date=date.today() + timedelta(days=35),
            status='Available'
        )
        db.session.add(unit)
        db.session.commit()
        unit_id = unit.id

        assert unit.status == 'Available'
        assert unit.record_status == 'active'
        assert unit.is_deleted is False

        # Soft delete
        unit.soft_delete()
        db.session.commit()

        refetched = BloodUnit.query.get(unit_id)
        assert refetched.is_deleted is True
        assert refetched.record_status == 'deactive'
        # Domain status must remain preserved as Available
        assert refetched.status == 'Available'

        # Restore
        refetched.restore()
        db.session.commit()

        restored = BloodUnit.query.get(unit_id)
        assert restored.is_deleted is False
        assert restored.record_status == 'active'
        assert restored.status == 'Available'


def test_partial_unique_index_respects_soft_delete(app):
    """Verify that soft-deleted records do not block reuse of unique fields (sqlite_where)."""
    with app.app_context():
        role = Role.query.filter_by(slug='donor').first()
        u1 = User(
            username='reusable_user',
            email='reusable@example.com',
            role_id=role.id,
            full_name='First Instance',
            phone='03001111111'
        )
        u1.set_password('Pass1234')
        db.session.add(u1)
        db.session.commit()

        # Attempting to create duplicate active user must fail
        u_dup = User(
            username='reusable_user',
            email='reusable_dup@example.com',
            role_id=role.id,
            full_name='Duplicate Active',
            phone='03001111112'
        )
        u_dup.set_password('Pass1234')
        db.session.add(u_dup)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        # Soft-delete the first user
        u1 = User.query.filter_by(username='reusable_user').first()
        u1.soft_delete()
        db.session.commit()

        # Now creating a new user with the same username should succeed because old is is_deleted=1
        u2 = User(
            username='reusable_user',
            email='reusable_new@example.com',
            role_id=role.id,
            full_name='Second Instance',
            phone='03001111113'
        )
        u2.set_password('Pass1234')
        db.session.add(u2)
        db.session.commit()

        assert u2.id != u1.id
        assert u2.username == 'reusable_user'
        assert u2.is_deleted is False


def test_admin_recycle_bin_and_restore(auth_client, app):
    """Verify admin recycle bin displays soft-deleted records and allows restore."""
    with app.app_context():
        h = Hospital(
            name='Temporary Hospital for Deletion',
            license_number='LIC-TEMP-DEL-999',
            address='Recycle Bin St',
            phone='03009999999'
        )
        db.session.add(h)
        db.session.commit()
        h_id = h.id
        h.soft_delete()
        db.session.commit()

    resp = auth_client.get('/admin/recycle-bin')
    assert resp.status_code == 200
    assert b'Temporary Hospital for Deletion' in resp.data

    # Restore via POST
    restore_resp = auth_client.post(f'/admin/recycle-bin/restore/hospital/{h_id}', follow_redirects=True)
    assert restore_resp.status_code == 200
    assert b'restored successfully' in restore_resp.data

    with app.app_context():
        restored_h = Hospital.query.get(h_id)
        assert restored_h.is_deleted is False
        assert restored_h.record_status == 'active'


def test_doctor_schedule_creation(auth_client, app):
    """Verify doctor schedule view and creation."""
    with app.app_context():
        doctor_role = Role(name='Doctor', slug='doctor', description='Doctor')
        db.session.add(doctor_role)
        db.session.flush()

        doc_user = User(
            username='dr_test',
            email='dr_test@test.com',
            full_name='Dr Test Physician',
            phone='03002222222',
            role_id=doctor_role.id
        )
        doc_user.set_password('Doctor@123')
        db.session.add(doc_user)
        db.session.flush()

        doctor = Doctor(user_id=doc_user.id, license_number='DOC-LIC-999', specialization='Hematology')
        db.session.add(doctor)
        db.session.commit()
        doc_id = doctor.id

    view_resp = auth_client.get(f'/hospitals/doctors/{doc_id}/schedules')
    assert view_resp.status_code == 200

    post_resp = auth_client.post(f'/hospitals/doctors/{doc_id}/schedules', data={
        'day_of_week': 'Wednesday',
        'start_time': '10:00',
        'end_time': '14:00',
        'max_patients': 25
    }, follow_redirects=True)
    assert post_resp.status_code == 200

    with app.app_context():
        schedule = DoctorSchedule.query.filter_by(doctor_id=doc_id, day_of_week='Wednesday').first()
        assert schedule is not None
        assert schedule.max_patients == 25


def test_add_diagnosis_route(auth_client, app):
    """Verify linking diagnosis to patient."""
    with app.app_context():
        patient_role = Role.query.filter_by(slug='patient').first()
        bg = BloodGroup.query.first()
        p_user = User(
            username='patient_test',
            email='patient_test@test.com',
            full_name='Test Patient',
            phone='03003333333',
            role_id=patient_role.id
        )
        p_user.set_password('Patient@123')
        db.session.add(p_user)
        db.session.flush()

        patient = Patient(
            user_id=p_user.id,
            mrn='THAL-TEST-999',
            blood_group_id=bg.id,
            date_of_birth=date(2015, 1, 1),
            gender='Male',
            emergency_contact_name='Parent',
            emergency_contact_phone='03004444444'
        )
        db.session.add(patient)
        db.session.commit()
        p_id = patient.id

        diagnosis = Diagnosis.query.first()
        d_id = diagnosis.id

    post_resp = auth_client.post(f'/patients/{p_id}/diagnoses/add', data={
        'diagnosis_id': d_id,
        'diagnosed_date': '2026-05-10',
        'severity': 'Severe',
        'notes': 'Genetic confirmation complete'
    }, follow_redirects=True)
    assert post_resp.status_code == 200

    with app.app_context():
        pd = PatientDiagnosis.query.filter_by(patient_id=p_id, diagnosis_id=d_id).first()
        assert pd is not None
        assert pd.severity == 'Severe'
        assert pd.notes == 'Genetic confirmation complete'
