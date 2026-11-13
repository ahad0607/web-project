from app.extensions import db
from app.models.base import BaseModel


class City(BaseModel):
    """Geographic cities."""
    __tablename__ = 'cities'

    name = db.Column(db.String(100), unique=True, nullable=False)
    state_province = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(50), default='Pakistan', nullable=False)

    areas = db.relationship('Area', back_populates='city', cascade='all, delete-orphan')
    users = db.relationship('User', back_populates='city', foreign_keys='User.city_id')
    hospitals = db.relationship('Hospital', back_populates='city')
    patients = db.relationship('Patient', back_populates='city')
    donors = db.relationship('Donor', back_populates='city')

    def __repr__(self):
        return f"<City {self.name}>"


class Area(BaseModel):
    """Locality/Neighborhood within a city."""
    __tablename__ = 'areas'

    city_id = db.Column(db.Integer, db.ForeignKey('cities.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    postal_code = db.Column(db.String(20), nullable=True)

    city = db.relationship('City', back_populates='areas')
    patients = db.relationship('Patient', back_populates='area')
    donors = db.relationship('Donor', back_populates='area')
    hospitals = db.relationship('Hospital', back_populates='area')

    def __repr__(self):
        return f"<Area {self.name} ({self.city.name if self.city else ''})>"
