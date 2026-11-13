from datetime import date, timedelta
from app.extensions import db
from app.models.base import BaseModel, utcnow


class Donor(BaseModel):
    """Blood donor profile."""
    __tablename__ = 'donors'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    blood_group_id = db.Column(db.Integer, db.ForeignKey('blood_groups.id', ondelete='RESTRICT'), nullable=False, index=True)
    city_id = db.Column(db.Integer, db.ForeignKey('cities.id', ondelete='SET NULL'), nullable=True, index=True)
    area_id = db.Column(db.Integer, db.ForeignKey('areas.id', ondelete='SET NULL'), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(10), nullable=False)  # Male, Female, Other
    weight_kg = db.Column(db.Float, default=65.0, nullable=False)  # Minimum 50kg required
    last_donation_date = db.Column(db.Date, nullable=True)
    total_donations = db.Column(db.Integer, default=0, nullable=False, index=True)
    donation_eligibility_status = db.Column(db.String(30), default='Eligible', nullable=False, index=True)  # Eligible, Deferred, Under-Age, Recent-Donation
    preferred_donation_center_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='SET NULL'), nullable=True)

    # Relationships
    user = db.relationship('User', back_populates='donor_profile', foreign_keys=[user_id])
    blood_group = db.relationship('BloodGroup', back_populates='donors')
    city = db.relationship('City', back_populates='donors')
    area = db.relationship('Area', back_populates='donors')
    preferred_center = db.relationship('Hospital')

    screenings = db.relationship('DonorHealthScreening', back_populates='donor', cascade='all, delete-orphan', order_by='desc(DonorHealthScreening.screening_date)')
    availability = db.relationship('DonorAvailability', back_populates='donor', uselist=False, cascade='all, delete-orphan')
    donations = db.relationship('Donation', back_populates='donor', cascade='all, delete-orphan')
    badges = db.relationship('DonorBadge', back_populates='donor', cascade='all, delete-orphan')
    matches = db.relationship('DonorMatch', back_populates='donor', cascade='all, delete-orphan')
    response_logs = db.relationship('ResponseLog', back_populates='donor', cascade='all, delete-orphan')

    @property
    def age(self):
        if self.date_of_birth:
            today = date.today()
            return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        return None

    @property
    def full_name(self):
        return self.user.full_name if self.user else "Unknown Donor"

    @property
    def days_since_last_donation(self):
        if self.last_donation_date:
            return (date.today() - self.last_donation_date).days
        return 9999

    @property
    def is_eligible_to_donate(self):
        """Clinical eligibility: Age 18-60, weight >= 50kg, and at least 90 days interval."""
        if not (18 <= (self.age or 0) <= 60):
            return False
        if (self.weight_kg or 0) < 50.0:
            return False
        if self.last_donation_date and self.days_since_last_donation < 90:
            return False
        return self.donation_eligibility_status == 'Eligible'

    @property
    def next_eligible_date(self):
        if self.last_donation_date:
            return self.last_donation_date + timedelta(days=90)
        return date.today()

    def __repr__(self):
        return f"<Donor {self.full_name} ({self.blood_group.name if self.blood_group else ''})>"


class DonorHealthScreening(BaseModel):
    """Clinical pre-donation screening record."""
    __tablename__ = 'donor_health_screenings'

    donor_id = db.Column(db.Integer, db.ForeignKey('donors.id', ondelete='CASCADE'), nullable=False)
    screening_date = db.Column(db.Date, nullable=False)
    weight_kg = db.Column(db.Float, nullable=False)
    systolic_bp = db.Column(db.Integer, default=120, nullable=False)
    diastolic_bp = db.Column(db.Integer, default=80, nullable=False)
    pulse_bpm = db.Column(db.Integer, default=72, nullable=False)
    hemoglobin_level = db.Column(db.Float, default=13.5, nullable=False)  # >= 12.5 g/dL required
    is_eligible = db.Column(db.Boolean, default=True, nullable=False)
    disqualification_reason = db.Column(db.String(255), nullable=True)
    screened_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    donor = db.relationship('Donor', back_populates='screenings')
    screened_by = db.relationship('User', foreign_keys=[screened_by_user_id])


class DonorAvailability(BaseModel):
    """Donor preferences and emergency responsiveness settings."""
    __tablename__ = 'donor_availability'

    donor_id = db.Column(db.Integer, db.ForeignKey('donors.id', ondelete='CASCADE'), unique=True, nullable=False)
    is_available_for_emergency = db.Column(db.Boolean, default=True, nullable=False)
    available_days = db.Column(db.String(100), default='All Days', nullable=False)  # e.g., 'Weekends', 'Monday,Wednesday'
    preferred_time_slot = db.Column(db.String(50), default='Anytime', nullable=False)  # Morning, Evening, Anytime
    travel_radius_km = db.Column(db.Integer, default=25, nullable=False)

    donor = db.relationship('Donor', back_populates='availability')


class Donation(BaseModel):
    """Historical or completed blood donation event."""
    __tablename__ = 'donations'

    donor_id = db.Column(db.Integer, db.ForeignKey('donors.id', ondelete='CASCADE'), nullable=False, index=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='RESTRICT'), nullable=False, index=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id', ondelete='SET NULL'), nullable=True, index=True)
    blood_unit_id = db.Column(db.Integer, db.ForeignKey('blood_units.id', ondelete='SET NULL'), nullable=True)
    donation_date = db.Column(db.Date, nullable=False, index=True)
    blood_group_id = db.Column(db.Integer, db.ForeignKey('blood_groups.id', ondelete='RESTRICT'), nullable=False, index=True)
    donation_type = db.Column(db.String(30), default='Voluntary', nullable=False)  # Voluntary, Directed, Emergency
    volume_ml = db.Column(db.Integer, default=450, nullable=False)
    notes = db.Column(db.String(255), nullable=True)

    donor = db.relationship('Donor', back_populates='donations')
    hospital = db.relationship('Hospital')
    campaign = db.relationship('Campaign', back_populates='donations')
    blood_unit = db.relationship('BloodUnit', back_populates='donation_event')
    blood_group = db.relationship('BloodGroup')


class Badge(BaseModel):
    """Gamification badges awarded to frequent donors."""
    __tablename__ = 'badges'

    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    icon = db.Column(db.String(50), default='fa-award', nullable=False)
    min_donations_required = db.Column(db.Integer, default=1, nullable=False)

    donor_badges = db.relationship('DonorBadge', back_populates='badge', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Badge {self.name}>"


class DonorBadge(BaseModel):
    """Junction table linking donors to earned badges."""
    __tablename__ = 'donor_badges'

    donor_id = db.Column(db.Integer, db.ForeignKey('donors.id', ondelete='CASCADE'), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey('badges.id', ondelete='CASCADE'), nullable=False)
    awarded_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    donor = db.relationship('Donor', back_populates='badges')
    badge = db.relationship('Badge', back_populates='donor_badges')
