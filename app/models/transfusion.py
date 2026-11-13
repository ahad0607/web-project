from datetime import date
from app.extensions import db
from app.models.base import BaseModel


class TransfusionSchedule(BaseModel):
    """Recurring transfusion calendar plan for thalassemia patients."""
    __tablename__ = 'transfusion_schedules'

    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False, index=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='RESTRICT'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='SET NULL'), nullable=True, index=True)
    scheduled_date = db.Column(db.Date, nullable=False, index=True)
    target_hemoglobin = db.Column(db.Float, default=9.5, nullable=False)
    required_units = db.Column(db.Integer, default=1, nullable=False)
    blood_group_id = db.Column(db.Integer, db.ForeignKey('blood_groups.id', ondelete='RESTRICT'), nullable=False, index=True)
    linked_blood_request_id = db.Column(db.Integer, db.ForeignKey('blood_requests.id', ondelete='SET NULL'), nullable=True)
    status = db.Column(db.String(30), default='Scheduled', nullable=False, index=True)  # Scheduled, Completed, Rescheduled, Cancelled
    notes = db.Column(db.String(255), nullable=True)

    patient = db.relationship('Patient', back_populates='transfusion_schedules')
    hospital = db.relationship('Hospital')
    doctor = db.relationship('Doctor')
    blood_group = db.relationship('BloodGroup')
    linked_blood_request = db.relationship('BloodRequest', back_populates='linked_schedule')
    transfusion_record = db.relationship('TransfusionRecord', back_populates='schedule', uselist=False)

    @property
    def is_upcoming(self):
        return self.status == 'Scheduled' and self.scheduled_date >= date.today()

    def __repr__(self):
        return f"<TransfusionSchedule Patient {self.patient_id} on {self.scheduled_date} ({self.status})>"


class TransfusionRecord(BaseModel):
    """Clinical execution record of a completed blood transfusion."""
    __tablename__ = 'transfusion_records'

    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False, index=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('transfusion_schedules.id', ondelete='SET NULL'), nullable=True, index=True)
    blood_unit_id = db.Column(db.Integer, db.ForeignKey('blood_units.id', ondelete='RESTRICT'), nullable=False, index=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='RESTRICT'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='SET NULL'), nullable=True, index=True)
    transfusion_date = db.Column(db.Date, default=date.today, nullable=False, index=True)
    start_time = db.Column(db.String(10), default='10:00', nullable=False)
    end_time = db.Column(db.String(10), default='13:30', nullable=False)
    pre_transfusion_hb = db.Column(db.Float, nullable=False)
    post_transfusion_hb = db.Column(db.Float, nullable=False)
    adverse_reaction_observed = db.Column(db.Boolean, default=False, nullable=False)
    reaction_details = db.Column(db.String(255), default='None', nullable=True)

    patient = db.relationship('Patient', back_populates='transfusion_records')
    schedule = db.relationship('TransfusionSchedule', back_populates='transfusion_record')
    blood_unit = db.relationship('BloodUnit', back_populates='transfusion_record')
    hospital = db.relationship('Hospital')
    doctor = db.relationship('Doctor')

    @property
    def hb_gain(self):
        return round(self.post_transfusion_hb - self.pre_transfusion_hb, 2)

    def __repr__(self):
        return f"<TransfusionRecord Patient {self.patient_id} on {self.transfusion_date}: Unit {self.blood_unit_id}>"
