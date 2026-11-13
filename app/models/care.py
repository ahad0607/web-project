from datetime import date
from app.extensions import db
from app.models.base import BaseModel


class Appointment(BaseModel):
    """Clinical outpatient consultations and pre/post transfusion visits."""
    __tablename__ = 'appointments'

    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='RESTRICT'), nullable=False, index=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='RESTRICT'), nullable=False, index=True)
    appointment_date = db.Column(db.Date, nullable=False, index=True)
    time_slot = db.Column(db.String(30), default='10:00 AM - 10:30 AM', nullable=False)
    reason = db.Column(db.String(255), default='Routine Thalassemia Checkup', nullable=False)
    appointment_type = db.Column(db.String(50), default='Regular Checkup', nullable=False)  # Regular Checkup, Pre-transfusion, Post-transfusion
    status = db.Column(db.String(30), default='Booked', nullable=False, index=True)  # Booked, Completed, Cancelled, No-Show

    patient = db.relationship('Patient', back_populates='appointments')
    doctor = db.relationship('Doctor', back_populates='appointments')
    hospital = db.relationship('Hospital')

    @property
    def is_upcoming(self):
        return self.status == 'Booked' and self.appointment_date >= date.today()

    def __repr__(self):
        return f"<Appointment Patient {self.patient_id} with Dr {self.doctor_id} on {self.appointment_date}>"


class Medication(BaseModel):
    """Pharmaceutical drug formulary (chelators, vitamins, supplements)."""
    __tablename__ = 'medications'

    name = db.Column(db.String(100), unique=True, nullable=False)       # e.g., Deferasirox
    generic_name = db.Column(db.String(100), nullable=False)           # e.g., Exjade / Jadenu
    drug_class = db.Column(db.String(80), default='Iron Chelator', nullable=False)  # Iron Chelator, Vitamin, Folic Acid
    form = db.Column(db.String(50), default='Dispersible Tablet', nullable=False)    # Tablet, Syrup, Injection, Infusion
    standard_dosage = db.Column(db.String(100), default='20-40 mg/kg/day', nullable=False)
    description = db.Column(db.Text, nullable=True)

    patient_medications = db.relationship('PatientMedication', back_populates='medication', cascade='all, delete-orphan')
    chelation_records = db.relationship('ChelationTherapyRecord', back_populates='medication')

    def __repr__(self):
        return f"<Medication {self.name} ({self.drug_class})>"


class PatientMedication(BaseModel):
    """Active and past prescriptions for a patient."""
    __tablename__ = 'patient_medications'

    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False, index=True)
    medication_id = db.Column(db.Integer, db.ForeignKey('medications.id', ondelete='RESTRICT'), nullable=False, index=True)
    prescribed_by_doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='SET NULL'), nullable=True)
    dosage = db.Column(db.String(100), default='500 mg', nullable=False)
    frequency = db.Column(db.String(100), default='Once Daily', nullable=False)
    instructions = db.Column(db.String(255), default='Dissolve in water, take before meal', nullable=True)
    start_date = db.Column(db.Date, default=date.today, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

    patient = db.relationship('Patient', back_populates='patient_medications')
    medication = db.relationship('Medication', back_populates='patient_medications')
    prescribed_by_doctor = db.relationship('Doctor', back_populates='prescribed_medications')

    def __repr__(self):
        return f"<PatientMedication Patient {self.patient_id}: {self.medication.name if self.medication else ''}>"


class Notification(BaseModel):
    """User in-app notifications for emergencies, transfusions, and appointments."""
    __tablename__ = 'notifications'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(30), default='System', nullable=False)  # Emergency, Schedule, Donation, System
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    link_url = db.Column(db.String(255), nullable=True)

    user = db.relationship('User', back_populates='notifications', foreign_keys=[user_id])

    def __repr__(self):
        return f"<Notification #{self.id} for User {self.user_id}: {self.title}>"
