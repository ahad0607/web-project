from datetime import datetime, date
from app.extensions import db
from app.models.base import BaseModel, utcnow


class BloodRequest(BaseModel):
    """General and urgent blood requests submitted by hospitals or patients."""
    __tablename__ = 'blood_requests'

    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='SET NULL'), nullable=True, index=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='RESTRICT'), nullable=False, index=True)
    blood_group_id = db.Column(db.Integer, db.ForeignKey('blood_groups.id', ondelete='RESTRICT'), nullable=False, index=True)
    component_type = db.Column(db.String(50), default='PRBC', nullable=False)
    units_requested = db.Column(db.Integer, default=1, nullable=False)
    units_fulfilled = db.Column(db.Integer, default=0, nullable=False)
    urgency = db.Column(db.String(30), default='Normal', nullable=False, index=True)  # Normal, Urgent, Emergency
    needed_by_date = db.Column(db.Date, default=date.today, nullable=False, index=True)
    reason = db.Column(db.String(255), default='Routine Thalassemia Transfusion', nullable=False)
    status = db.Column(db.String(30), default='Pending', nullable=False, index=True)  # Pending, In Progress, Partially Fulfilled, Fulfilled, Cancelled

    patient = db.relationship('Patient', back_populates='blood_requests')
    hospital = db.relationship('Hospital', back_populates='blood_requests')
    blood_group = db.relationship('BloodGroup', back_populates='blood_requests')
    status_logs = db.relationship('RequestStatusLog', back_populates='request', cascade='all, delete-orphan', order_by='desc(RequestStatusLog.created_at)')
    emergency_request = db.relationship('EmergencyRequest', back_populates='blood_request', uselist=False, cascade='all, delete-orphan')
    linked_schedule = db.relationship('TransfusionSchedule', back_populates='linked_blood_request', uselist=False)

    @property
    def is_fulfilled(self):
        return self.units_fulfilled >= self.units_requested

    def __repr__(self):
        return f"<BloodRequest #{self.id}: {self.units_requested} units of {self.blood_group.name if self.blood_group else ''} ({self.status})>"


class RequestStatusLog(BaseModel):
    """Audit trail for blood request status transitions."""
    __tablename__ = 'request_status_logs'

    request_id = db.Column(db.Integer, db.ForeignKey('blood_requests.id', ondelete='CASCADE'), nullable=False)
    previous_status = db.Column(db.String(30), nullable=False)
    new_status = db.Column(db.String(30), nullable=False)
    changed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    notes = db.Column(db.String(255), nullable=True)

    request = db.relationship('BloodRequest', back_populates='status_logs')
    changed_by = db.relationship('User', foreign_keys=[changed_by_user_id])


class EmergencyRequest(BaseModel):
    """Broadcasted SOS emergency blood request."""
    __tablename__ = 'emergency_requests'

    request_id = db.Column(db.Integer, db.ForeignKey('blood_requests.id', ondelete='CASCADE'), unique=True, nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='SET NULL'), nullable=True, index=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='RESTRICT'), nullable=False, index=True)
    blood_group_id = db.Column(db.Integer, db.ForeignKey('blood_groups.id', ondelete='RESTRICT'), nullable=False, index=True)
    units_needed = db.Column(db.Integer, default=1, nullable=False)
    severity_level = db.Column(db.String(30), default='Critical', nullable=False)  # High, Critical, Life-Threatening
    broadcast_radius_km = db.Column(db.Integer, default=30, nullable=False)
    is_broadcast_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    broadcast_time = db.Column(db.DateTime, default=utcnow, nullable=False)
    expired_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(30), default='Active', nullable=False, index=True)  # Active, Fulfilled, Expired, Cancelled

    blood_request = db.relationship('BloodRequest', back_populates='emergency_request')
    patient = db.relationship('Patient')
    hospital = db.relationship('Hospital')
    blood_group = db.relationship('BloodGroup')
    donor_matches = db.relationship('DonorMatch', back_populates='emergency_request', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<EmergencyRequest #{self.id} for {self.blood_group.name if self.blood_group else ''}>"


class DonorMatch(BaseModel):
    """Algorithmic match pairing an emergency request to an eligible donor."""
    __tablename__ = 'donor_matches'

    emergency_request_id = db.Column(db.Integer, db.ForeignKey('emergency_requests.id', ondelete='CASCADE'), nullable=False, index=True)
    donor_id = db.Column(db.Integer, db.ForeignKey('donors.id', ondelete='CASCADE'), nullable=False, index=True)
    match_score = db.Column(db.Float, default=100.0, nullable=False)  # 0 to 100 based on proximity & availability
    match_distance_km = db.Column(db.Float, default=5.0, nullable=False)
    status = db.Column(db.String(30), default='Notified', nullable=False, index=True)  # Notified, Accepted, Declined, Fulfilled, Timed Out
    notified_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    responded_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True, index=True)

    emergency_request = db.relationship('EmergencyRequest', back_populates='donor_matches')
    donor = db.relationship('Donor', back_populates='matches')
    response_logs = db.relationship('ResponseLog', back_populates='donor_match', cascade='all, delete-orphan')

    @property
    def is_expired(self):
        from datetime import datetime
        if self.expires_at and datetime.utcnow() > self.expires_at and self.status == 'Notified':
            return True
        return False

    def __repr__(self):
        return f"<DonorMatch Req {self.emergency_request_id} -> Donor {self.donor_id} ({self.status})>"


class ResponseLog(BaseModel):
    """Audit log of donor response to an emergency alert."""
    __tablename__ = 'response_logs'

    donor_match_id = db.Column(db.Integer, db.ForeignKey('donor_matches.id', ondelete='CASCADE'), nullable=False)
    donor_id = db.Column(db.Integer, db.ForeignKey('donors.id', ondelete='CASCADE'), nullable=False)
    action = db.Column(db.String(30), nullable=False)  # 'Accepted', 'Declined'
    response_time_seconds = db.Column(db.Integer, default=60, nullable=False)
    remarks = db.Column(db.String(255), nullable=True)

    donor_match = db.relationship('DonorMatch', back_populates='response_logs')
    donor = db.relationship('Donor', back_populates='response_logs')
