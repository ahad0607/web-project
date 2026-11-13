"""
LifeBridge Database Seeder
Populates all 46 database models with realistic Pakistani clinical and emergency donor data.
Admin Credentials:
    Email:    admin@lifebridge.com
    Password: Admin@123
"""

from datetime import datetime, date, timedelta
from app import create_app
from app.extensions import db
from app.models import (
    Role,
    Permission,
    UserRole,
    RolePermission,
    User,
    LoginLog,
    AuditLog,
    City,
    Area,
    BloodGroup,
    Diagnosis,
    Hospital,
    Department,
    Doctor,
    DoctorSchedule,
    HospitalBloodBank,
    Patient,
    Guardian,
    PatientGuardian,
    PatientMedicalHistory,
    PatientDiagnosis,
    HemoglobinRecord,
    FerritinRecord,
    ChelationTherapyRecord,
    Donor,
    DonorHealthScreening,
    DonorAvailability,
    Donation,
    Badge,
    DonorBadge,
    BloodUnit,
    InventoryTransaction,
    BloodRequest,
    RequestStatusLog,
    EmergencyRequest,
    DonorMatch,
    ResponseLog,
    TransfusionSchedule,
    TransfusionRecord,
    Appointment,
    Medication,
    PatientMedication,
    Notification,
    Campaign,
    CampaignParticipant,
    Feedback
)

app = create_app('development')

def seed_database(reset=False):
    with app.app_context():
        if reset:
            print("Resetting LifeBridge database tables...")
            db.drop_all()

        print("Initializing LifeBridge database tables...")
        db.create_all()

        # Check if already seeded
        if not reset and User.query.filter_by(email='admin@lifebridge.com').first():
            print("Database already contains data. Use python seed.py --reset to re-seed from scratch.")
            return

        print("Seeding Table 1 & 2: Roles & Permissions...")
        roles_data = [
            ('Admin', 'admin', 'System Administrator with unrestricted access'),
            ('Doctor', 'doctor', 'Licensed Hematologist / Clinical Pediatrician'),
            ('Hospital Staff', 'hospital_staff', 'Hospital Blood Bank Officer & Nurse'),
            ('Donor', 'donor', 'Voluntary Regular & Emergency Blood Donor'),
            ('Patient', 'patient', 'Registered Thalassemia Patient / Guardian')
        ]
        role_objs = {}
        for name, slug, desc in roles_data:
            r = Role(name=name, slug=slug, description=desc)
            db.session.add(r)
            role_objs[slug] = r
        db.session.flush()

        # Permissions
        perms = [
            ('View Patients', 'view_patients', 'patients'),
            ('Manage Transfusions', 'manage_transfusions', 'transfusions'),
            ('Manage Inventory', 'manage_inventory', 'inventory'),
            ('Emergency Broadcast', 'emergency_broadcast', 'requests'),
            ('System Administration', 'system_admin', 'admin')
        ]
        for name, slug, mod in perms:
            p = Permission(name=name, slug=slug, module=mod, description=f'Permission to {name}')
            db.session.add(p)
            db.session.flush()
            rp = RolePermission(role_id=role_objs['admin'].id, permission_id=p.id)
            db.session.add(rp)

        print("Seeding Table 8 & 9: Geography (Cities & Areas)...")
        cities_data = [
            ('Karachi', 'Sindh', '75270', ['Clifton', 'Gulshan-e-Iqbal', 'DHA Phase 5', 'Saddar', 'North Nazimabad']),
            ('Lahore', 'Punjab', '54000', ['Gulberg', 'Model Town', 'DHA Phase 3', 'Johar Town', 'Anarkali']),
            ('Islamabad', 'Federal', '44000', ['F-7', 'G-9', 'Blue Area', 'I-8', 'Bahria Town']),
            ('Peshawar', 'Khyber Pakhtunkhwa', '25000', ['Hayatabad', 'University Town', 'Saddar Peshawar']),
            ('Rawalpindi', 'Punjab', '46000', ['Saddar Rawalpindi', 'Satellite Town', 'Westridge'])
        ]
        city_objs = {}
        area_objs = []
        for c_name, prov, postal, areas in cities_data:
            city = City(name=c_name, state_province=prov, postal_code=postal, country='Pakistan')
            db.session.add(city)
            db.session.flush()
            city_objs[c_name] = city
            for a_name in areas:
                area = Area(city_id=city.id, name=a_name, postal_code=postal)
                db.session.add(area)
                area_objs.append(area)
        db.session.flush()

        print("Seeding Table 10 & 11: Reference (Blood Groups & Diagnoses)...")
        blood_groups_data = [
            ('O-', 'Negative', 'O-, O+, A-, A+, B-, B+, AB-, AB+', 'O-', 'Universal Red Cell Donor'),
            ('O+', 'Positive', 'O+, A+, B+, AB+', 'O-, O+', 'Most Common Blood Group'),
            ('A-', 'Negative', 'A-, A+, AB-, AB+', 'O-, A-', 'Rare Rh Negative Group'),
            ('A+', 'Positive', 'A+, AB+', 'O-, O+, A-, A+', 'Common Rh Positive Group'),
            ('B-', 'Negative', 'B-, B+, AB-, AB+', 'O-, B-', 'High Demand in Thalassemia'),
            ('B+', 'Positive', 'B+, AB+', 'O-, O+, B-, B+', 'Predominant in South Asia'),
            ('AB-', 'Negative', 'AB-, AB+', 'O-, A-, B-, AB-', 'Extremely Rare Donor Group'),
            ('AB+', 'Positive', 'AB+', 'O-, O+, A-, A+, B-, B+, AB-, AB+', 'Universal Red Cell Recipient')
        ]
        bg_objs = {}
        for name, rh, to_g, from_g, desc in blood_groups_data:
            bg = BloodGroup(name=name, rh_factor=rh, can_donate_to=to_g, can_receive_from=from_g, description=desc)
            db.session.add(bg)
            bg_objs[name] = bg
        db.session.flush()

        diagnoses_data = [
            ('D56.1', 'Beta Thalassemia Major', 'Hemoglobinopathy', 'Severe microcytic hypochromic anemia requiring regular transfusions'),
            ('D56.2', 'Beta Thalassemia Intermedia', 'Hemoglobinopathy', 'Moderate anemia with variable transfusion requirement'),
            ('D56.5', 'Hemoglobin E-Beta Thalassemia', 'Hemoglobinopathy', 'Compound heterozygote syndrome common in South Asia'),
            ('D57.2', 'Sickle-Cell Beta Thalassemia', 'Hemoglobinopathy', 'Sickling and thalassemia features requiring transfusion management')
        ]
        diag_objs = {}
        for code, name, cat, desc in diagnoses_data:
            diag = Diagnosis(code=code, name=name, category=cat, description=desc)
            db.session.add(diag)
            diag_objs[code] = diag
        db.session.flush()

        print("Seeding Table 3: Users (Admin, Doctor, Staff, Donors, Patients)...")
        users_seed = [
            ('admin', 'admin@lifebridge.com', 'Admin@123', 'Administrator LifeBridge', '0300-0000001', '42101-0000001-1', 'admin', 'Karachi'),
            ('dr_tariq', 'doctor.tariq@lifebridge.com', 'Doctor@123', 'Dr. Tariq Mansoor', '0300-1111111', '42101-1111111-1', 'doctor', 'Karachi'),
            ('dr_ayesha', 'doctor.ayesha@lifebridge.com', 'Doctor@123', 'Dr. Ayesha Siddiqa', '0300-2222222', '35202-2222222-2', 'doctor', 'Lahore'),
            ('staff_fatima', 'staff.fatima@lifebridge.com', 'Staff@123', 'Fatima Noor (Blood Bank In-Charge)', '0300-3333333', '42101-3333333-3', 'hospital_staff', 'Karachi'),
            ('donor_hamza', 'donor.hamza@lifebridge.com', 'Donor@123', 'Hamza Ali Khan', '0300-4444444', '42101-4444444-4', 'donor', 'Karachi'),
            ('donor_usman', 'donor.usman@lifebridge.com', 'Donor@123', 'Usman Ghani', '0300-5555555', '35202-5555555-5', 'donor', 'Lahore'),
            ('donor_maryam', 'donor.maryam@lifebridge.com', 'Donor@123', 'Maryam Tariq', '0300-6666666', '42101-6666666-6', 'donor', 'Karachi'),
            ('donor_saad', 'donor.saad@lifebridge.com', 'Donor@123', 'Saad Qureshi', '0300-7777777', '61101-7777777-7', 'donor', 'Islamabad'),
            ('patient_zainab', 'patient.zainab@lifebridge.com', 'Patient@123', 'Zainab Bibi', '0300-8888888', '42101-8888888-8', 'patient', 'Karachi'),
            ('patient_bilal', 'patient.bilal@lifebridge.com', 'Patient@123', 'Bilal Ahmed Khan', '0300-9999999', '35202-9999999-9', 'patient', 'Lahore')
        ]
        user_objs = {}
        for uname, email, pwd, fname, ph, cnic, r_slug, c_name in users_seed:
            u = User(
                username=uname,
                email=email,
                full_name=fname,
                phone=ph,
                cnic=cnic,
                role_id=role_objs[r_slug].id,
                city_id=city_objs[c_name].id,
                is_active_account=True
            )
            u.set_password(pwd)
            db.session.add(u)
            user_objs[uname] = u
        db.session.flush()

        # UserRole junction table (Table 4)
        for u in user_objs.values():
            ur = UserRole(user_id=u.id, role_id=u.role_id)
            db.session.add(ur)

        # Login Logs (Table 6) & Audit Logs (Table 7)
        for u in user_objs.values():
            ll = LoginLog(
                user_id=u.id,
                ip_address='127.0.0.1',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0',
                login_status='SUCCESS'
            )
            db.session.add(ll)

        al = AuditLog(
            user_id=user_objs['admin'].id,
            action='SYSTEM_BOOTSTRAP',
            table_name='system',
            record_id=1,
            new_values='{"status": "initialized", "version": "2.0"}'
        )
        db.session.add(al)

        print("Seeding Table 26, 27, 28, 29, 30: Hospitals, Departments, Doctors & Blood Banks...")
        hosp_data = [
            ('Indus Hospital & Health Network', 'HOSP-KHI-001', 'Karachi', 'Plot 123, Korangi Crossing', '021-35112709', '021-111-111-880'),
            ('Fatimid Foundation Thalassemia Center', 'HOSP-KHI-002', 'Karachi', '1 Britto Road, Garden East', '021-32225284', '021-32225285'),
            ('Children Hospital Lahore', 'HOSP-LHR-001', 'Lahore', 'Ferozepur Road', '042-99230901', '042-99230910'),
            ('Pakistan Institute of Medical Sciences (PIMS)', 'HOSP-ISB-001', 'Islamabad', 'Sector G-8/3', '051-9261170', '051-9261180')
        ]
        hospital_objs = {}
        for hname, lic, cname, addr, ph, hotl in hosp_data:
            h = Hospital(
                name=hname,
                license_number=lic,
                city_id=city_objs[cname].id,
                address=addr,
                phone=ph,
                emergency_hotline=hotl,
                has_blood_bank=True,
                has_thalassemia_center=True,
                total_beds=150
            )
            db.session.add(h)
            db.session.flush()
            hospital_objs[lic] = h

            # Department (Table 27)
            dept = Department(hospital_id=h.id, name='Pediatric Hematology & Oncology', floor='2nd Floor')
            db.session.add(dept)
            db.session.flush()

            # Blood Bank (Table 30)
            bb = HospitalBloodBank(
                hospital_id=h.id,
                license_number=f"BB-{lic}",
                in_charge_name="Chief Blood Transfusion Officer",
                contact_phone=ph,
                storage_capacity_units=500,
                current_stock_units=40
            )
            db.session.add(bb)
            db.session.flush()

        # Assign Hospital Staff to Indus Hospital
        user_objs['staff_fatima'].hospital_id = hospital_objs['HOSP-KHI-001'].id

        # Doctor (Table 28)
        doc1 = Doctor(
            user_id=user_objs['dr_tariq'].id,
            hospital_id=hospital_objs['HOSP-KHI-001'].id,
            department_id=1,
            specialization='Consultant Hematologist',
            license_number='PMDC-54321-S',
            consultation_fee=2000.0,
            experience_years=14
        )
        doc2 = Doctor(
            user_id=user_objs['dr_ayesha'].id,
            hospital_id=hospital_objs['HOSP-LHR-001'].id,
            department_id=3,
            specialization='Pediatric Hematologist',
            license_number='PMDC-87654-P',
            consultation_fee=1800.0,
            experience_years=10
        )
        db.session.add_all([doc1, doc2])
        db.session.flush()

        # Doctor Schedules (Table 29)
        for d in [doc1, doc2]:
            ds1 = DoctorSchedule(doctor_id=d.id, day_of_week='Monday', start_time='09:00', end_time='13:00', max_patients=15)
            ds2 = DoctorSchedule(doctor_id=d.id, day_of_week='Thursday', start_time='09:00', end_time='13:00', max_patients=15)
            db.session.add_all([ds1, ds2])

        print("Seeding Table 41: Medications...")
        meds_data = [
            ('Deferasirox (Asunra / Jadenu)', 'Deferasirox', 'Iron Chelator', 'Dispersible Tablet', '20-40 mg/kg/day', 'Once daily oral iron chelator for chronic iron overload'),
            ('Deferiprone (Ferriprox)', 'Deferiprone', 'Iron Chelator', 'Oral Capsule', '75-100 mg/kg/day', 'Oral chelator effective for cardiac iron clearance'),
            ('Deferoxamine (Desferal)', 'Deferoxamine mesylate', 'Iron Chelator', 'Subcutaneous Infusion', '30-50 mg/kg/day', 'Infusion chelator administered via portable battery pump'),
            ('Folic Acid Tablets', 'Pteroylglutamic acid', 'Vitamin', 'Tablet', '5 mg daily', 'Supports accelerated erythropoiesis in hemolytic states'),
            ('Calcium & Vitamin D3', 'Cholecalciferol', 'Vitamin', 'Chewable Tablet', '1 tablet daily', 'Bone mineral density support')
        ]
        med_objs = {}
        for mname, gname, dclass, form, dose, desc in meds_data:
            m = Medication(name=mname, generic_name=gname, drug_class=dclass, form=form, standard_dosage=dose, description=desc)
            db.session.add(m)
            med_objs[mname] = m
        db.session.flush()

        print("Seeding Table 12-19: Patients, Guardians, Medical History, Lab Records...")
        # Patient 1
        p1 = Patient(
            user_id=user_objs['patient_zainab'].id,
            mrn='THAL-2026-0001',
            blood_group_id=bg_objs['B+'].id,
            city_id=city_objs['Karachi'].id,
            date_of_birth=date(2016, 5, 14),
            gender='Female',
            weight_kg=26.5,
            height_cm=118.0,
            primary_hospital_id=hospital_objs['HOSP-KHI-001'].id,
            primary_doctor_id=doc1.id,
            diagnosis_id=diag_objs['D56.1'].id,
            baseline_hemoglobin=7.2,
            transfusion_interval_days=21,
            emergency_contact_name='Khan Muhammad (Father)',
            emergency_contact_phone='0300-8888888'
        )
        # Patient 2
        p2 = Patient(
            user_id=user_objs['patient_bilal'].id,
            mrn='THAL-2026-0002',
            blood_group_id=bg_objs['O+'].id,
            city_id=city_objs['Lahore'].id,
            date_of_birth=2014,
            gender='Male',
            weight_kg=32.0,
            height_cm=128.0,
            primary_hospital_id=hospital_objs['HOSP-LHR-001'].id,
            primary_doctor_id=doc2.id,
            diagnosis_id=diag_objs['D56.1'].id,
            baseline_hemoglobin=6.9,
            transfusion_interval_days=18,
            emergency_contact_name='Arshad Ahmed (Father)',
            emergency_contact_phone='0300-9999999'
        )
        # Fix p2 date of birth
        p2.date_of_birth = date(2014, 8, 22)
        db.session.add_all([p1, p2])
        db.session.flush()

        # Guardian (Table 13) & PatientGuardian (Table 14)
        g1 = Guardian(full_name='Khan Muhammad', relationship_to_patient='Father', phone='0300-8888888', cnic='42101-7654321-1')
        db.session.add(g1)
        db.session.flush()
        pg1 = PatientGuardian(patient_id=p1.id, guardian_id=g1.id, is_primary=True)
        db.session.add(pg1)

        # PatientMedicalHistory (Table 15)
        pmh1 = PatientMedicalHistory(
            patient_id=p1.id,
            splenectomy_done=False,
            hepatitis_b_status='Vaccinated',
            hepatitis_c_status='Negative',
            hiv_status='Negative',
            allergies='None reported',
            cardiac_complications='Normal echocardiogram',
            endocrine_complications='Mild growth delay',
            clinical_notes='Adherent to daily chelation. Pre-transfusion target 9.5 g/dL.'
        )
        pmh2 = PatientMedicalHistory(
            patient_id=p2.id,
            splenectomy_done=True,
            splenectomy_date=date(2022, 3, 15),
            hepatitis_b_status='Vaccinated',
            hepatitis_c_status='Negative',
            hiv_status='Negative',
            allergies='Penicillin allergic',
            clinical_notes='Post-splenectomy on oral penicillin prophylaxis.'
        )
        db.session.add_all([pmh1, pmh2])

        # PatientDiagnosis (Table 16)
        pd1 = PatientDiagnosis(patient_id=p1.id, diagnosis_id=diag_objs['D56.1'].id, diagnosed_date=date(2016, 11, 20), severity='Severe')
        db.session.add(pd1)

        # HemoglobinRecord (Table 17) & FerritinRecord (Table 18)
        today = date.today()
        hb1 = HemoglobinRecord(patient_id=p1.id, test_date=today - timedelta(days=22), hb_level=7.1, rbc_count=2.9, lab_name='Indus Pathology', notes='Pre-transfusion')
        hb2 = HemoglobinRecord(patient_id=p1.id, test_date=today - timedelta(days=21), hb_level=9.8, rbc_count=3.8, lab_name='Indus Pathology', notes='Post-transfusion (+2.7 g/dL)')
        hb3 = HemoglobinRecord(patient_id=p1.id, test_date=today - timedelta(days=2), hb_level=7.4, rbc_count=3.0, lab_name='Indus Pathology', notes='Due for cycle')
        db.session.add_all([hb1, hb2, hb3])

        fer1 = FerritinRecord(patient_id=p1.id, test_date=today - timedelta(days=60), ferritin_level=1680.0, target_level=1000.0, lab_name='Indus Pathology')
        fer2 = FerritinRecord(patient_id=p1.id, test_date=today - timedelta(days=10), ferritin_level=1520.0, target_level=1000.0, lab_name='Indus Pathology', notes='Declining nicely with Deferasirox')
        db.session.add_all([fer1, fer2])

        # ChelationTherapyRecord (Table 19)
        chel1 = ChelationTherapyRecord(
            patient_id=p1.id,
            medication_id=med_objs['Deferasirox (Asunra / Jadenu)'].id,
            dosage_mg=500.0,
            frequency='Once Daily',
            start_date=today - timedelta(days=180),
            adherence_percentage=96.0,
            prescribed_by_doctor_id=doc1.id
        )
        db.session.add(chel1)

        # PatientMedication (Table 42)
        pmed1 = PatientMedication(
            patient_id=p1.id,
            medication_id=med_objs['Deferasirox (Asunra / Jadenu)'].id,
            prescribed_by_doctor_id=doc1.id,
            dosage='500 mg',
            frequency='Once Daily',
            instructions='Dissolve in water, take 30 mins before breakfast',
            start_date=today - timedelta(days=180)
        )
        pmed2 = PatientMedication(
            patient_id=p1.id,
            medication_id=med_objs['Folic Acid Tablets'].id,
            prescribed_by_doctor_id=doc1.id,
            dosage='5 mg',
            frequency='Once Daily',
            instructions='Take after lunch',
            start_date=today - timedelta(days=180)
        )
        db.session.add_all([pmed1, pmed2])

        print("Seeding Table 24 & 25: Badges & Donor Gamification...")
        badges_data = [
            ('Bronze Donor', 'Completed 1 voluntary blood donation', 'fa-award', 1),
            ('Silver Donor', 'Completed 3 voluntary blood donations', 'fa-medal', 3),
            ('Gold Donor', 'Completed 5 voluntary blood donations', 'fa-trophy', 5),
            ('Life Saver', 'Completed 10 regular blood donations', 'fa-heart', 10),
            ('Thalassemia Hero', 'Completed 15+ dedicated blood donations', 'fa-crown', 15)
        ]
        badge_objs = {}
        for bname, desc, ico, req_don in badges_data:
            bdg = Badge(name=bname, description=desc, icon=ico, min_donations_required=req_don)
            db.session.add(bdg)
            badge_objs[bname] = bdg
        db.session.flush()

        print("Seeding Table 20-23: Donors, Screenings, Availability & Donations...")
        donor1 = Donor(
            user_id=user_objs['donor_hamza'].id,
            blood_group_id=bg_objs['B+'].id,
            city_id=city_objs['Karachi'].id,
            date_of_birth=date(1998, 4, 10),
            gender='Male',
            weight_kg=72.0,
            last_donation_date=today - timedelta(days=95),
            total_donations=6,
            donation_eligibility_status='Eligible',
            preferred_donation_center_id=hospital_objs['HOSP-KHI-001'].id
        )
        donor2 = Donor(
            user_id=user_objs['donor_usman'].id,
            blood_group_id=bg_objs['O+'].id,
            city_id=city_objs['Lahore'].id,
            date_of_birth=date(1995, 11, 2),
            gender='Male',
            weight_kg=78.0,
            last_donation_date=today - timedelta(days=110),
            total_donations=11,
            donation_eligibility_status='Eligible',
            preferred_donation_center_id=hospital_objs['HOSP-LHR-001'].id
        )
        donor3 = Donor(
            user_id=user_objs['donor_maryam'].id,
            blood_group_id=bg_objs['B+'].id,
            city_id=city_objs['Karachi'].id,
            date_of_birth=date(2001, 7, 19),
            gender='Female',
            weight_kg=56.0,
            last_donation_date=today - timedelta(days=120),
            total_donations=3,
            donation_eligibility_status='Eligible',
            preferred_donation_center_id=hospital_objs['HOSP-KHI-002'].id
        )
        donor4 = Donor(
            user_id=user_objs['donor_saad'].id,
            blood_group_id=bg_objs['O-'].id,
            city_id=city_objs['Islamabad'].id,
            date_of_birth=date(1999, 1, 30),
            gender='Male',
            weight_kg=70.0,
            last_donation_date=today - timedelta(days=15),  # in cooldown
            total_donations=4,
            donation_eligibility_status='Eligible'
        )
        db.session.add_all([donor1, donor2, donor3, donor4])
        db.session.flush()

        # Donor Availability (Table 22)
        for d in [donor1, donor2, donor3, donor4]:
            da = DonorAvailability(
                donor_id=d.id,
                is_available_for_emergency=True,
                available_days='All Days',
                preferred_time_slot='Anytime',
                travel_radius_km=30
            )
            db.session.add(da)

        # Donor Health Screening (Table 21)
        dhs1 = DonorHealthScreening(
            donor_id=donor1.id,
            screening_date=today - timedelta(days=95),
            weight_kg=72.0,
            systolic_bp=120,
            diastolic_bp=80,
            pulse_bpm=72,
            hemoglobin_level=14.2,
            is_eligible=True,
            screened_by_user_id=user_objs['dr_tariq'].id
        )
        db.session.add(dhs1)

        # Donor Badges (Table 25)
        db1 = DonorBadge(donor_id=donor1.id, badge_id=badge_objs['Bronze Donor'].id)
        db2 = DonorBadge(donor_id=donor1.id, badge_id=badge_objs['Silver Donor'].id)
        db3 = DonorBadge(donor_id=donor1.id, badge_id=badge_objs['Gold Donor'].id)
        db4 = DonorBadge(donor_id=donor2.id, badge_id=badge_objs['Life Saver'].id)
        db.session.add_all([db1, db2, db3, db4])

        print("Seeding Table 44 & 45: Campaigns & Participants...")
        camp1 = Campaign(
            title='Annual FAST-NUCES Thalassemia Blood Drive',
            description='Voluntary student blood drive dedicated to pediatric thalassemia patients in Karachi.',
            hospital_id=hospital_objs['HOSP-KHI-001'].id,
            city_id=city_objs['Karachi'].id,
            venue='Main Campus Auditorium, FAST-NUCES, Karachi',
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=2),
            target_units=150,
            collected_units=82,
            status='Ongoing'
        )
        camp2 = Campaign(
            title='World Thalassemia Day Drive Lahore',
            description='Emergency blood drive raising awareness and collecting PRBC units.',
            hospital_id=hospital_objs['HOSP-LHR-001'].id,
            city_id=city_objs['Lahore'].id,
            venue='Liberty Roundabout Medical Camp, Lahore',
            start_date=today + timedelta(days=10),
            end_date=today + timedelta(days=12),
            target_units=100,
            collected_units=0,
            status='Upcoming'
        )
        db.session.add_all([camp1, camp2])
        db.session.flush()

        part1 = CampaignParticipant(campaign_id=camp1.id, user_id=user_objs['donor_hamza'].id, role_in_campaign='Donor', attended=True, units_donated=1)
        part2 = CampaignParticipant(campaign_id=camp1.id, user_id=user_objs['donor_maryam'].id, role_in_campaign='Volunteer', attended=True)
        db.session.add_all([part1, part2])

        # Donation record (Table 23)
        don1 = Donation(
            donor_id=donor1.id,
            hospital_id=hospital_objs['HOSP-KHI-001'].id,
            campaign_id=camp1.id,
            donation_date=today - timedelta(days=95),
            blood_group_id=bg_objs['B+'].id,
            donation_type='Voluntary',
            volume_ml=450,
            status='Completed'
        )
        db.session.add(don1)

        print("Seeding Table 31 & 32: Blood Units & Inventory Transactions...")
        bb1 = hospital_objs['HOSP-KHI-001'].blood_bank
        unit_samples = [
            ('BU-2026-00101', 'B+', 'PRBC', today - timedelta(days=10), today + timedelta(days=25), 'Available', 'Shelf A-1'),
            ('BU-2026-00102', 'B+', 'PRBC', today - timedelta(days=4), today + timedelta(days=31), 'Available', 'Shelf A-1'),
            ('BU-2026-00103', 'O+', 'PRBC', today - timedelta(days=12), today + timedelta(days=23), 'Available', 'Shelf B-2'),
            ('BU-2026-00104', 'O-', 'Whole Blood', today - timedelta(days=28), today + timedelta(days=7), 'Available', 'Shelf C-1'),  # Expiring soon!
            ('BU-2026-00105', 'A+', 'PRBC', today - timedelta(days=30), today + timedelta(days=5), 'Available', 'Shelf A-2'),  # Expiring soon!
            ('BU-2026-00106', 'AB+', 'Platelets', today - timedelta(days=2), today + timedelta(days=3), 'Available', 'Agitator-1'),
            ('BU-2026-00107', 'B+', 'PRBC', today - timedelta(days=22), today + timedelta(days=13), 'Transfused', 'Shelf A-1')
        ]
        unit_objs = {}
        for unum, bgname, comp, ddate, edate, ust, loc in unit_samples:
            unit = BloodUnit(
                blood_bank_id=bb1.id,
                unit_number=unum,
                blood_group_id=bg_objs[bgname].id,
                component_type=comp,
                donation_date=ddate,
                expiry_date=edate,
                donor_id=donor1.id if 'B+' in bgname else None,
                volume_ml=450,
                status=ust,
                storage_location=loc
            )
            db.session.add(unit)
            unit_objs[unum] = unit
            db.session.flush()

            tx = InventoryTransaction(
                blood_bank_id=bb1.id,
                blood_unit_id=unit.id,
                transaction_type='IN_DONATION',
                quantity=1,
                reason='Collected via voluntary drive',
                performed_by_user_id=user_objs['staff_fatima'].id
            )
            db.session.add(tx)

        print("Seeding Table 33-37: Requests, Emergencies, Matches & Response Logs...")
        req1 = BloodRequest(
            patient_id=p1.id,
            hospital_id=hospital_objs['HOSP-KHI-001'].id,
            blood_group_id=bg_objs['B+'].id,
            component_type='PRBC',
            units_requested=2,
            units_fulfilled=0,
            urgency='Emergency',
            needed_by_date=today,
            reason='Acute severe anemia crisis (Hb: 5.8 g/dL)',
            status='Pending'
        )
        req2 = BloodRequest(
            patient_id=p2.id,
            hospital_id=hospital_objs['HOSP-LHR-001'].id,
            blood_group_id=bg_objs['O+'].id,
            component_type='PRBC',
            units_requested=1,
            units_fulfilled=1,
            urgency='Normal',
            needed_by_date=today + timedelta(days=3),
            reason='Scheduled routine transfusion',
            status='Fulfilled'
        )
        db.session.add_all([req1, req2])
        db.session.flush()

        rlog1 = RequestStatusLog(request_id=req1.id, previous_status='None', new_status='Pending', changed_by_user_id=user_objs['admin'].id, notes='Emergency broadcast triggered')
        rlog2 = RequestStatusLog(request_id=req2.id, previous_status='Pending', new_status='Fulfilled', changed_by_user_id=user_objs['dr_ayesha'].id, notes='Fulfilled from local bank')
        db.session.add_all([rlog1, rlog2])

        # Emergency Request (Table 35)
        em1 = EmergencyRequest(
            request_id=req1.id,
            patient_id=p1.id,
            hospital_id=hospital_objs['HOSP-KHI-001'].id,
            blood_group_id=bg_objs['B+'].id,
            units_needed=2,
            severity_level='Life-Threatening',
            broadcast_radius_km=30,
            is_broadcast_active=True,
            broadcast_time=datetime.utcnow()
        )
        db.session.add(em1)
        db.session.flush()

        # DonorMatch (Table 36)
        match1 = DonorMatch(
            emergency_request_id=em1.id,
            donor_id=donor1.id,
            match_score=100.0,
            match_distance_km=4.8,
            status='Notified',
            notified_at=datetime.utcnow()
        )
        match2 = DonorMatch(
            emergency_request_id=em1.id,
            donor_id=donor3.id,
            match_score=100.0,
            match_distance_km=7.2,
            status='Accepted',
            notified_at=datetime.utcnow() - timedelta(minutes=25),
            responded_at=datetime.utcnow() - timedelta(minutes=10)
        )
        db.session.add_all([match1, match2])
        db.session.flush()

        # ResponseLog (Table 37)
        resp1 = ResponseLog(donor_match_id=match2.id, donor_id=donor3.id, action='Accepted', response_time_seconds=900, remarks='On my way to Indus Hospital')
        db.session.add(resp1)

        print("Seeding Table 38 & 39: Transfusion Schedules & Transfusion Records...")
        sched1 = TransfusionSchedule(
            patient_id=p1.id,
            hospital_id=hospital_objs['HOSP-KHI-001'].id,
            doctor_id=doc1.id,
            scheduled_date=today + timedelta(days=2),
            target_hemoglobin=9.5,
            required_units=1,
            blood_group_id=p1.blood_group_id,
            linked_blood_request_id=req1.id,
            status='Scheduled',
            notes='Auto-scheduled 21-day cycle'
        )
        sched_past = TransfusionSchedule(
            patient_id=p1.id,
            hospital_id=hospital_objs['HOSP-KHI-001'].id,
            doctor_id=doc1.id,
            scheduled_date=today - timedelta(days=21),
            target_hemoglobin=9.5,
            required_units=1,
            blood_group_id=p1.blood_group_id,
            status='Completed',
            notes='Executed on time'
        )
        db.session.add_all([sched1, sched_past])
        db.session.flush()

        trec1 = TransfusionRecord(
            patient_id=p1.id,
            schedule_id=sched_past.id,
            blood_unit_id=unit_objs['BU-2026-00107'].id,
            hospital_id=hospital_objs['HOSP-KHI-001'].id,
            doctor_id=doc1.id,
            transfusion_date=today - timedelta(days=21),
            start_time='10:15 AM',
            end_time='01:45 PM',
            pre_transfusion_hb=7.1,
            post_transfusion_hb=9.8,
            adverse_reaction_observed=False,
            reaction_details='Smooth infusion, no fever or hives'
        )
        db.session.add(trec1)

        print("Seeding Table 40 & 43: Appointments & Notifications...")
        appt1 = Appointment(
            patient_id=p1.id,
            doctor_id=doc1.id,
            hospital_id=hospital_objs['HOSP-KHI-001'].id,
            appointment_date=today,
            time_slot='10:00 AM - 10:30 AM',
            reason='Routine Pre-transfusion Clinical Checkup',
            appointment_type='Pre-transfusion',
            status='Booked'
        )
        db.session.add(appt1)

        notif1 = Notification(
            user_id=user_objs['donor_hamza'].id,
            title='🚨 Emergency Blood Match!',
            message='Urgent B+ blood required for pediatric thalassemia patient at Indus Hospital.',
            notification_type='Emergency',
            link_url='/donors/emergency-matches'
        )
        notif2 = Notification(
            user_id=user_objs['patient_zainab'].id,
            title='Transfusion Reminder',
            message='Your scheduled blood transfusion is confirmed in 2 days.',
            notification_type='Schedule',
            link_url='/transfusions/schedules'
        )
        db.session.add_all([notif1, notif2])

        print("Seeding Table 46: Feedback...")
        fb1 = Feedback(
            user_id=user_objs['patient_zainab'].id,
            category='Transfusion Experience',
            rating=5,
            comment='The daycare staff at Indus Hospital is extremely compassionate. Transfusion was painless and well monitored.',
            is_public=True
        )
        fb2 = Feedback(
            user_id=user_objs['donor_hamza'].id,
            category='Donation Drive',
            rating=5,
            comment='Great experience donating at the FAST campus blood drive. Very smooth screening process.',
            is_public=True
        )
        db.session.add_all([fb1, fb2])

        db.session.commit()
        print("LifeBridge database successfully seeded across all 46 models!")
        print("Default Admin Login: admin@lifebridge.com / Admin@123")

if __name__ == '__main__':
    import sys
    reset_flag = '--reset' in sys.argv or '--force' in sys.argv
    seed_database(reset=reset_flag)
