from datetime import date
from app.extensions import db
from app.models.base import BaseModel


class BloodUnit(BaseModel):
    """Individual bagged blood unit stored in a hospital blood bank."""
    __tablename__ = 'blood_units'

    blood_bank_id = db.Column(db.Integer, db.ForeignKey('hospital_blood_banks.id', ondelete='CASCADE'), nullable=False, index=True)
    unit_number = db.Column(db.String(50), nullable=False, index=True)
    blood_group_id = db.Column(db.Integer, db.ForeignKey('blood_groups.id', ondelete='RESTRICT'), nullable=False, index=True)
    component_type = db.Column(db.String(50), default='PRBC', nullable=False)  # PRBC, Whole Blood, Platelets, FFP
    donation_date = db.Column(db.Date, nullable=False, index=True)
    expiry_date = db.Column(db.Date, nullable=False, index=True)
    donor_id = db.Column(db.Integer, db.ForeignKey('donors.id', ondelete='SET NULL'), nullable=True, index=True)
    volume_ml = db.Column(db.Integer, default=450, nullable=False)
    storage_location = db.Column(db.String(80), default='Main Refrigerator Shelf A', nullable=False)
    status = db.Column(db.String(30), default='Available', nullable=False, index=True)  # Available, Reserved, Transfused, Expired, Discarded

    __table_args__ = (
        db.Index('uq_blood_units_unit_number_active', 'unit_number', unique=True, sqlite_where=db.text('is_deleted = 0')),
    )

    blood_bank = db.relationship('HospitalBloodBank', back_populates='blood_units')
    blood_group = db.relationship('BloodGroup', back_populates='blood_units')
    donor = db.relationship('Donor')
    donation_event = db.relationship('Donation', back_populates='blood_unit', uselist=False)
    transactions = db.relationship('InventoryTransaction', back_populates='blood_unit', cascade='all, delete-orphan')
    transfusion_record = db.relationship('TransfusionRecord', back_populates='blood_unit', uselist=False)

    @property
    def days_to_expiry(self):
        if self.expiry_date:
            return (self.expiry_date - date.today()).days
        return 0

    @property
    def is_expired(self):
        return self.days_to_expiry < 0

    @property
    def is_expiring_soon(self):
        return 0 <= self.days_to_expiry <= 7

    def __repr__(self):
        return f"<BloodUnit {self.unit_number} ({self.blood_group.name if self.blood_group else ''} {self.component_type})>"


class InventoryTransaction(BaseModel):
    """Audit ledger for all inventory movements."""
    __tablename__ = 'inventory_transactions'

    blood_bank_id = db.Column(db.Integer, db.ForeignKey('hospital_blood_banks.id', ondelete='CASCADE'), nullable=False, index=True)
    blood_unit_id = db.Column(db.Integer, db.ForeignKey('blood_units.id', ondelete='CASCADE'), nullable=False, index=True)
    transaction_type = db.Column(db.String(30), nullable=False, index=True)  # IN_DONATION, OUT_TRANSFUSION, OUT_DISCARD, TRANSFER
    quantity = db.Column(db.Integer, default=1, nullable=False)
    reference_id = db.Column(db.String(50), nullable=True)  # request_id or transfusion_id
    reason = db.Column(db.String(255), nullable=True)
    performed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    blood_bank = db.relationship('HospitalBloodBank', back_populates='transactions')
    blood_unit = db.relationship('BloodUnit', back_populates='transactions')
    performed_by = db.relationship('User', foreign_keys=[performed_by_user_id])

    def __repr__(self):
        return f"<InventoryTransaction {self.transaction_type}: Unit {self.blood_unit_id}>"
