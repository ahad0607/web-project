from datetime import date
from app.extensions import db
from app.models.base import BaseModel


class Patient(BaseModel):
    """Thalassemia patient record."""
    __tablename__ = 'patients'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    mrn = db.Column(db.String(30), nullable=False, index=True)  # e.g., 'THAL-2026-0001'
    blood_group_id = db.Column(db.Integer, db.ForeignKey('blood_groups.id', ondelete='RESTRICT'), nullable=False, index=True)
    city_id = db.Column(db.Integer, db.ForeignKey('cities.id', ondelete='SET NULL'), nullable=True, index=True)
    area_id = db.Column(db.Integer, db.ForeignKey('areas.id', ondelete='SET NULL'), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(10), nullable=False)  # Male, Female, Other
    weight_kg = db.Column(db.Float, default=30.0, nullable=False)
    height_cm = db.Column(db.Float, default=120.0, nullable=True)
    primary_hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='SET NULL'), nullable=True, index=True)
    primary_doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='SET NULL'), nullable=True, index=True)
    diagnosis_id = db.Column(db.Integer, db.ForeignKey('diagnoses.id', ondelete='SET NULL'), nullable=True)
    baseline_hemoglobin = db.Column(db.Float, default=7.0, nullable=False)  # in g/dL
    transfusion_interval_days = db.Column(db.Integer, default=21, nullable=False)  # standard 14 to 28 days
    emergency_contact_name = db.Column(db.String(100), nullable=False)
    emergency_contact_phone = db.Column(db.String(30), nullable=False)

    __table_args__ = (
        db.Index('uq_patients_mrn_active', 'mrn', unique=True, sqlite_where=db.text('is_deleted = 0')),
    )

    # Relationships
    user = db.relationship('User', back_populates='patient_profile', foreign_keys=[user_id])
    blood_group = db.relationship('BloodGroup', back_populates='patients')
    city = db.relationship('City', back_populates='patients')
    area = db.relationship('Area', back_populates='patients')
    primary_hospital = db.relationship('Hospital')
    primary_doctor = db.relationship('Doctor', back_populates='patients')
    diagnosis = db.relationship('Diagnosis', back_populates='patients')

    guardians = db.relationship('PatientGuardian', back_populates='patient', cascade='all, delete-orphan')
    medical_history = db.relationship('PatientMedicalHistory', back_populates='patient', uselist=False, cascade='all, delete-orphan')
    patient_diagnoses = db.relationship('PatientDiagnosis', back_populates='patient', cascade='all, delete-orphan')
    hemoglobin_records = db.relationship('HemoglobinRecord', back_populates='patient', cascade='all, delete-orphan', order_by='desc(HemoglobinRecord.test_date)')
    ferritin_records = db.relationship('FerritinRecord', back_populates='patient', cascade='all, delete-orphan', order_by='desc(FerritinRecord.test_date)')
    chelation_records = db.relationship('ChelationTherapyRecord', back_populates='patient', cascade='all, delete-orphan')
    transfusion_schedules = db.relationship('TransfusionSchedule', back_populates='patient', cascade='all, delete-orphan')
    transfusion_records = db.relationship('TransfusionRecord', back_populates='patient', cascade='all, delete-orphan')
    appointments = db.relationship('Appointment', back_populates='patient', cascade='all, delete-orphan')
    patient_medications = db.relationship('PatientMedication', back_populates='patient', cascade='all, delete-orphan')
    blood_requests = db.relationship('BloodRequest', back_populates='patient')

    @property
    def age(self):
        if self.date_of_birth:
            today = date.today()
            return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        return None

    @property
    def full_name(self):
        return self.user.full_name if self.user else "Unknown Patient"

    def __repr__(self):
        return f"<Patient {self.mrn}: {self.full_name}>"


class Guardian(BaseModel):
    """Guardian or parent details for pediatric thalassemia patients."""
    __tablename__ = 'guardians'

    full_name = db.Column(db.String(120), nullable=False)
    relationship_to_patient = db.Column(db.String(50), nullable=False)  # Father, Mother, Sibling, Uncle, etc.
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    cnic = db.Column(db.String(25), nullable=True)
    occupation = db.Column(db.String(100), nullable=True)
    address = db.Column(db.String(255), nullable=True)

    patient_links = db.relationship('PatientGuardian', back_populates='guardian', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Guardian {self.full_name} ({self.relationship_to_patient})>"


class PatientGuardian(BaseModel):
    """Junction table connecting patients to their guardians."""
    __tablename__ = 'patient_guardians'

    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False)
    guardian_id = db.Column(db.Integer, db.ForeignKey('guardians.id', ondelete='CASCADE'), nullable=False)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)

    patient = db.relationship('Patient', back_populates='guardians')
    guardian = db.relationship('Guardian', back_populates='patient_links')


class PatientMedicalHistory(BaseModel):
    """Long-term medical background, organ complications and surgical history."""
    __tablename__ = 'patient_medical_history'

    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), unique=True, nullable=False)
    splenectomy_done = db.Column(db.Boolean, default=False, nullable=False)
    splenectomy_date = db.Column(db.Date, nullable=True)
    hepatitis_b_status = db.Column(db.String(20), default='Negative', nullable=False)  # Negative, Positive, Vaccinated
    hepatitis_c_status = db.Column(db.String(20), default='Negative', nullable=False)
    hiv_status = db.Column(db.String(20), default='Negative', nullable=False)
    cardiac_complications = db.Column(db.String(255), nullable=True)
    endocrine_complications = db.Column(db.String(255), nullable=True)  # Diabetes, Hypothyroidism, etc.
    allergies = db.Column(db.String(255), default='None reported', nullable=True)
    clinical_notes = db.Column(db.Text, nullable=True)

    patient = db.relationship('Patient', back_populates='medical_history')


class PatientDiagnosis(BaseModel):
    """Diagnosis records for a patient."""
    __tablename__ = 'patient_diagnoses'

    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False)
    diagnosis_id = db.Column(db.Integer, db.ForeignKey('diagnoses.id', ondelete='CASCADE'), nullable=False)
    diagnosed_date = db.Column(db.Date, nullable=False)
    diagnosed_by_doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='SET NULL'), nullable=True)
    severity = db.Column(db.String(30), default='Moderate', nullable=False)  # Mild, Moderate, Severe
    notes = db.Column(db.Text, nullable=True)

    patient = db.relationship('Patient', back_populates='patient_diagnoses')
    diagnosis = db.relationship('Diagnosis', back_populates='patient_diagnoses')
    diagnosed_by = db.relationship('Doctor')


class HemoglobinRecord(BaseModel):
    """Laboratory hemoglobin level measurements for transfusion tracking."""
    __tablename__ = 'hemoglobin_records'

    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False, index=True)
    test_date = db.Column(db.Date, nullable=False, index=True)
    hb_level = db.Column(db.Float, nullable=False)  # in g/dL, e.g., 8.2
    rbc_count = db.Column(db.Float, nullable=True)   # in million/mcL
    lab_name = db.Column(db.String(100), default='Central Pathology Lab', nullable=True)
    recorded_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    notes = db.Column(db.String(255), nullable=True)

    patient = db.relationship('Patient', back_populates='hemoglobin_records')
    recorded_by = db.relationship('User', foreign_keys=[recorded_by_user_id])

    def __repr__(self):
        return f"<HbRecord Patient {self.patient_id}: {self.hb_level} g/dL on {self.test_date}>"


class FerritinRecord(BaseModel):
    """Serum ferritin tracking (iron overload monitoring in transfusion-dependent patients)."""
    __tablename__ = 'ferritin_records'

    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False, index=True)
    test_date = db.Column(db.Date, nullable=False, index=True)
    ferritin_level = db.Column(db.Float, nullable=False)  # in ng/mL, e.g., 1850.0
    target_level = db.Column(db.Float, default=1000.0, nullable=False)
    lab_name = db.Column(db.String(100), default='Central Pathology Lab', nullable=True)
    recorded_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    notes = db.Column(db.String(255), nullable=True)

    patient = db.relationship('Patient', back_populates='ferritin_records')
    recorded_by = db.relationship('User', foreign_keys=[recorded_by_user_id])

    @property
    def is_elevated(self):
        return self.ferritin_level > 1000.0

    def __repr__(self):
        return f"<FerritinRecord Patient {self.patient_id}: {self.ferritin_level} ng/mL>"


class ChelationTherapyRecord(BaseModel):
    """Iron chelation therapy tracking (Deferasirox, Deferoxamine, Deferiprone)."""
    __tablename__ = 'chelation_therapy_records'

    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False, index=True)
    medication_id = db.Column(db.Integer, db.ForeignKey('medications.id', ondelete='RESTRICT'), nullable=False, index=True)
    dosage_mg = db.Column(db.Float, nullable=False)
    frequency = db.Column(db.String(50), default='Once Daily', nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    adherence_percentage = db.Column(db.Float, default=95.0, nullable=False)  # patient compliance %
    side_effects_noted = db.Column(db.String(255), nullable=True)
    prescribed_by_doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='SET NULL'), nullable=True)

    patient = db.relationship('Patient', back_populates='chelation_records')
    medication = db.relationship('Medication', back_populates='chelation_records')
    prescribed_by_doctor = db.relationship('Doctor', back_populates='prescribed_chelation')

    def __repr__(self):
        return f"<ChelationRecord Patient {self.patient_id}: {self.dosage_mg}mg>"
