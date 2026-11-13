from app.extensions import db
from app.models.base import BaseModel


class Hospital(BaseModel):
    """Medical centers and treatment facilities."""
    __tablename__ = 'hospitals'

    name = db.Column(db.String(150), nullable=False)
    license_number = db.Column(db.String(50), unique=True, nullable=False)
    city_id = db.Column(db.Integer, db.ForeignKey('cities.id', ondelete='SET NULL'), nullable=True)
    area_id = db.Column(db.Integer, db.ForeignKey('areas.id', ondelete='SET NULL'), nullable=True)
    address = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    emergency_hotline = db.Column(db.String(30), nullable=True)
    has_blood_bank = db.Column(db.Boolean, default=True, nullable=False)
    has_thalassemia_center = db.Column(db.Boolean, default=True, nullable=False)
    total_beds = db.Column(db.Integer, default=50, nullable=False)

    city = db.relationship('City', back_populates='hospitals')
    area = db.relationship('Area', back_populates='hospitals')
    departments = db.relationship('Department', back_populates='hospital', cascade='all, delete-orphan')
    doctors = db.relationship('Doctor', back_populates='hospital')
    blood_bank = db.relationship('HospitalBloodBank', back_populates='hospital', uselist=False, cascade='all, delete-orphan')
    campaigns = db.relationship('Campaign', back_populates='hospital')
    blood_requests = db.relationship('BloodRequest', back_populates='hospital')

    def __repr__(self):
        return f"<Hospital {self.name}>"


class Department(BaseModel):
    """Hospital department (e.g., Hematology, Pediatrics, Blood Transfusion)."""
    __tablename__ = 'departments'

    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    floor = db.Column(db.String(20), nullable=True)
    contact_ext = db.Column(db.String(20), nullable=True)

    hospital = db.relationship('Hospital', back_populates='departments')
    doctors = db.relationship('Doctor', back_populates='department')

    def __repr__(self):
        return f"<Department {self.name}>"


class Doctor(BaseModel):
    """Practicing physicians and hematologists."""
    __tablename__ = 'doctors'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='SET NULL'), nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id', ondelete='SET NULL'), nullable=True)
    specialization = db.Column(db.String(100), default='Hematology', nullable=False)
    license_number = db.Column(db.String(50), unique=True, nullable=False)  # PMDC registration
    consultation_fee = db.Column(db.Numeric(10, 2), default=0.0, nullable=False)
    experience_years = db.Column(db.Integer, default=5, nullable=False)

    user = db.relationship('User', back_populates='doctor_profile', foreign_keys=[user_id])
    hospital = db.relationship('Hospital', back_populates='doctors')
    department = db.relationship('Department', back_populates='doctors')
    schedules = db.relationship('DoctorSchedule', back_populates='doctor', cascade='all, delete-orphan')
    patients = db.relationship('Patient', back_populates='primary_doctor')
    appointments = db.relationship('Appointment', back_populates='doctor')
    prescribed_chelation = db.relationship('ChelationTherapyRecord', back_populates='prescribed_by_doctor')
    prescribed_medications = db.relationship('PatientMedication', back_populates='prescribed_by_doctor')

    @property
    def full_name(self):
        return f"Dr. {self.user.full_name}" if self.user else "Dr. Unknown"

    def __repr__(self):
        return f"<Doctor {self.license_number}>"


class DoctorSchedule(BaseModel):
    """Weekly outpatient / transfusion clinic schedule."""
    __tablename__ = 'doctor_schedules'

    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='CASCADE'), nullable=False)
    day_of_week = db.Column(db.String(20), nullable=False)  # Monday, Tuesday, etc.
    start_time = db.Column(db.String(10), nullable=False)   # "09:00"
    end_time = db.Column(db.String(10), nullable=False)     # "14:00"
    max_patients = db.Column(db.Integer, default=20, nullable=False)

    doctor = db.relationship('Doctor', back_populates='schedules')

    def __repr__(self):
        return f"<DoctorSchedule {self.day_of_week} {self.start_time}-{self.end_time}>"


class HospitalBloodBank(BaseModel):
    """Blood bank facility embedded within or attached to a hospital."""
    __tablename__ = 'hospital_blood_banks'

    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='CASCADE'), unique=True, nullable=False)
    license_number = db.Column(db.String(50), unique=True, nullable=False)
    in_charge_name = db.Column(db.String(120), nullable=False)
    contact_phone = db.Column(db.String(30), nullable=False)
    storage_capacity_units = db.Column(db.Integer, default=500, nullable=False)
    current_stock_units = db.Column(db.Integer, default=0, nullable=False)
    low_stock_threshold = db.Column(db.Integer, default=10, nullable=False)

    hospital = db.relationship('Hospital', back_populates='blood_bank')
    blood_units = db.relationship('BloodUnit', back_populates='blood_bank', cascade='all, delete-orphan')
    transactions = db.relationship('InventoryTransaction', back_populates='blood_bank', cascade='all, delete-orphan')

    @property
    def bank_name(self):
        return f"{self.hospital.name} Blood Bank" if self.hospital else f"Blood Bank ({self.license_number})"

    def __repr__(self):
        return f"<HospitalBloodBank {self.hospital.name if self.hospital else self.license_number}>"
