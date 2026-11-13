from datetime import datetime, date
from app.extensions import db
from app.models.base import BaseModel, utcnow


class Campaign(BaseModel):
    """Community and university blood donation drives."""
    __tablename__ = 'campaigns'

    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='RESTRICT'), nullable=False, index=True)
    city_id = db.Column(db.Integer, db.ForeignKey('cities.id', ondelete='SET NULL'), nullable=True, index=True)
    area_id = db.Column(db.Integer, db.ForeignKey('areas.id', ondelete='SET NULL'), nullable=True)
    venue = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.Date, nullable=False, index=True)
    end_date = db.Column(db.Date, nullable=False, index=True)
    target_units = db.Column(db.Integer, default=100, nullable=False)
    collected_units = db.Column(db.Integer, default=0, nullable=False)
    banner_url = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(30), default='Upcoming', nullable=False, index=True)  # Upcoming, Ongoing, Completed, Cancelled

    hospital = db.relationship('Hospital', back_populates='campaigns')
    city = db.relationship('City')
    area = db.relationship('Area')
    participants = db.relationship('CampaignParticipant', back_populates='campaign', cascade='all, delete-orphan')
    donations = db.relationship('Donation', back_populates='campaign')

    @property
    def progress_percentage(self):
        if self.target_units > 0:
            return min(100, int((self.collected_units / self.target_units) * 100))
        return 0

    @property
    def is_active(self):
        today = date.today()
        return self.start_date <= today <= self.end_date

    def __repr__(self):
        return f"<Campaign {self.title}>"


class CampaignParticipant(BaseModel):
    """Volunteers, donors, and staff registered for a campaign drive."""
    __tablename__ = 'campaign_participants'

    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    role_in_campaign = db.Column(db.String(30), default='Donor', nullable=False)  # Donor, Volunteer, Organizer
    registered_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    attended = db.Column(db.Boolean, default=False, nullable=False)
    units_donated = db.Column(db.Integer, default=0, nullable=False)

    campaign = db.relationship('Campaign', back_populates='participants')
    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f"<CampaignParticipant User {self.user_id} in Camp {self.campaign_id}>"


class Feedback(BaseModel):
    """User reviews, ratings, and experience reports."""
    __tablename__ = 'feedback'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    category = db.Column(db.String(50), default='General', nullable=False)  # Transfusion Experience, Donation Drive, Hospital Service, System Bug
    rating = db.Column(db.Integer, default=5, nullable=False, index=True)  # 1 to 5 stars
    comment = db.Column(db.Text, nullable=False)
    is_public = db.Column(db.Boolean, default=True, nullable=False, index=True)

    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f"<Feedback #{self.id}: {self.rating} stars by User {self.user_id}>"
