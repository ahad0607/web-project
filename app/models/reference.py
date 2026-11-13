from app.extensions import db
from app.models.base import BaseModel


class BloodGroup(BaseModel):
    """ABO & Rh blood group reference model with compatibility mapping."""
    __tablename__ = 'blood_groups'

    name = db.Column(db.String(10), unique=True, nullable=False)  # A+, A-, B+, B-, AB+, AB-, O+, O-
    rh_factor = db.Column(db.String(5), nullable=False)           # Positive, Negative
    can_donate_to = db.Column(db.String(100), nullable=False)     # Comma-separated compatible recipients
    can_receive_from = db.Column(db.String(100), nullable=False)  # Comma-separated compatible donors
    description = db.Column(db.String(255), nullable=True)

    patients = db.relationship('Patient', back_populates='blood_group')
    donors = db.relationship('Donor', back_populates='blood_group')
    blood_units = db.relationship('BloodUnit', back_populates='blood_group')
    blood_requests = db.relationship('BloodRequest', back_populates='blood_group')

    def is_compatible_donor(self, recipient_group_name):
        """Check if self blood group can donate to recipient_group_name."""
        recipients = [x.strip() for x in (self.can_donate_to or '').split(',')]
        return recipient_group_name in recipients

    def is_compatible_recipient(self, donor_group_name):
        """Check if self blood group can receive from donor_group_name."""
        donors = [x.strip() for x in (self.can_receive_from or '').split(',')]
        return donor_group_name in donors

    def __repr__(self):
        return f"<BloodGroup {self.name}>"


class Diagnosis(BaseModel):
    """Medical diagnosis catalog (ICD-10 aligned for thalassemia and hemoglobinopathies)."""
    __tablename__ = 'diagnoses'

    code = db.Column(db.String(20), unique=True, nullable=False)  # e.g., D56.1
    name = db.Column(db.String(150), nullable=False)              # Beta Thalassemia Major
    category = db.Column(db.String(100), default='Hemoglobinopathy', nullable=False)
    description = db.Column(db.Text, nullable=True)

    patients = db.relationship('Patient', back_populates='diagnosis')
    patient_diagnoses = db.relationship('PatientDiagnosis', back_populates='diagnosis')

    def __repr__(self):
        return f"<Diagnosis {self.code}: {self.name}>"
