from datetime import date, timedelta
from app.models import Patient, Donor, BloodUnit, Hospital, HospitalBloodBank, InventoryTransaction
from app.extensions import db


def test_patient_crud(auth_client, app):
    """Test creating and retrieving a thalassemia patient."""
    response = auth_client.post('/patients/create', data={
        'full_name': 'Ali Raza',
        'email': 'ali.raza@test.com',
        'phone': '0300-4445556',
        'cnic': '42101-1122334-1',
        'date_of_birth': '2015-06-10',
        'gender': 'Male',
        'blood_group_id': 1,
        'city_id': 1,
        'weight_kg': 28.0,
        'height_cm': 120.0,
        'baseline_hemoglobin': 7.5,
        'transfusion_interval_days': 21,
        'emergency_contact_name': 'Raza Khan',
        'emergency_contact_phone': '0300-4445556'
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        p = Patient.query.filter_by(emergency_contact_name='Raza Khan').first()
        assert p is not None
        assert p.mrn.startswith('THAL-')
        assert p.age == 11
        assert p.is_deleted is False


def test_donor_screening_logic(app):
    """Test clinical screening thresholds (weight >= 50kg, Hb >= 12.5)."""
    from app.utils import validate_donor_screening

    # Valid donor
    errs = validate_donor_screening(weight_kg=65.0, systolic_bp=120, diastolic_bp=80, pulse_bpm=72, hemoglobin_level=13.8)
    assert len(errs) == 0

    # Under-weight and low Hb
    errs_invalid = validate_donor_screening(weight_kg=45.0, systolic_bp=120, diastolic_bp=80, pulse_bpm=80, hemoglobin_level=11.2)
    assert len(errs_invalid) == 2
    assert any('50 kg' in e for e in errs_invalid)
    assert any('12.5 g/dL' in e for e in errs_invalid)


def test_inventory_blood_unit_lifecycle(app):
    """Test blood unit addition, expiry calculation, and transaction logging."""
    with app.app_context():
        # Setup hospital and blood bank
        hosp = Hospital(
            name='Test Hospital',
            license_number='TEST-H-01',
            city_id=1,
            address='Street 1',
            phone='021-1234567'
        )
        db.session.add(hosp)
        db.session.flush()

        bank = HospitalBloodBank(
            hospital_id=hosp.id,
            license_number='BB-TEST-01',
            in_charge_name='Dr. Incharge',
            contact_phone='021-1234567',
            storage_capacity_units=100,
            current_stock_units=1
        )
        db.session.add(bank)
        db.session.flush()

        today = date.today()
        unit = BloodUnit(
            blood_bank_id=bank.id,
            unit_number='TEST-UNIT-001',
            blood_group_id=1,
            component_type='PRBC',
            donation_date=today,
            expiry_date=today + timedelta(days=35),
            status='Available',
            storage_location='Shelf A-1'
        )
        db.session.add(unit)
        db.session.flush()

        tx = InventoryTransaction(
            blood_bank_id=bank.id,
            blood_unit_id=unit.id,
            transaction_type='IN_DONATION',
            quantity=1,
            reason='Test donation'
        )
        db.session.add(tx)
        db.session.commit()

        # Assertions
        assert unit.days_to_expiry == 35
        assert unit.is_expired is False
        assert unit.is_expiring_soon is False
        assert len(unit.transactions) == 1
        assert unit.transactions[0].transaction_type == 'IN_DONATION'
