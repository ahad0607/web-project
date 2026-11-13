from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models.base import BaseModel


class Role(BaseModel):
    """System user roles (Admin, Doctor, Hospital Staff, Donor, Patient)."""
    __tablename__ = 'roles'

    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)

    users = db.relationship('User', back_populates='role', lazy='dynamic', foreign_keys='User.role_id')
    permissions = db.relationship('RolePermission', back_populates='role', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Role {self.name}>"


class Permission(BaseModel):
    """Granular system permissions."""
    __tablename__ = 'permissions'

    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    module = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255), nullable=True)

    role_permissions = db.relationship('RolePermission', back_populates='permission', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Permission {self.slug}>"


class UserRole(BaseModel):
    """Junction table for secondary or multi-role assignments."""
    __tablename__ = 'user_roles'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id', ondelete='CASCADE'), nullable=False)

    user = db.relationship('User', back_populates='user_roles', foreign_keys=[user_id])
    role = db.relationship('Role')


class RolePermission(BaseModel):
    """Junction table mapping roles to permissions."""
    __tablename__ = 'role_permissions'

    role_id = db.Column(db.Integer, db.ForeignKey('roles.id', ondelete='CASCADE'), nullable=False)
    permission_id = db.Column(db.Integer, db.ForeignKey('permissions.id', ondelete='CASCADE'), nullable=False)

    role = db.relationship('Role', back_populates='permissions')
    permission = db.relationship('Permission', back_populates='role_permissions')


class User(BaseModel):
    """Core user account model."""
    __tablename__ = 'users'

    username = db.Column(db.String(80), nullable=False, index=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    cnic = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    city_id = db.Column(db.Integer, db.ForeignKey('cities.id', ondelete='SET NULL'), nullable=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='SET NULL'), nullable=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id', ondelete='RESTRICT'), nullable=False)
    is_active_account = db.Column(db.Boolean, default=True, nullable=False)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    last_login_at = db.Column(db.DateTime, nullable=True)
    avatar_url = db.Column(db.String(255), nullable=True)

    __table_args__ = (
        db.Index('uq_users_username_active', 'username', unique=True, sqlite_where=db.text('is_deleted = 0')),
        db.Index('uq_users_email_active', 'email', unique=True, sqlite_where=db.text('is_deleted = 0')),
        db.Index('uq_users_cnic_active', 'cnic', unique=True, sqlite_where=db.text('is_deleted = 0 AND cnic IS NOT NULL')),
    )

    # Relationships
    role = db.relationship('Role', back_populates='users', foreign_keys=[role_id])
    city = db.relationship('City', back_populates='users', foreign_keys=[city_id])
    hospital = db.relationship('Hospital', foreign_keys=[hospital_id])
    user_roles = db.relationship('UserRole', back_populates='user', cascade='all, delete-orphan', foreign_keys='UserRole.user_id')
    login_logs = db.relationship('LoginLog', back_populates='user', cascade='all, delete-orphan', foreign_keys='LoginLog.user_id')
    notifications = db.relationship('Notification', back_populates='user', cascade='all, delete-orphan', foreign_keys='Notification.user_id')

    # One-to-one profiles
    patient_profile = db.relationship('Patient', back_populates='user', uselist=False, cascade='all, delete-orphan', foreign_keys='Patient.user_id')
    donor_profile = db.relationship('Donor', back_populates='user', uselist=False, cascade='all, delete-orphan', foreign_keys='Donor.user_id')
    doctor_profile = db.relationship('Doctor', back_populates='user', uselist=False, cascade='all, delete-orphan', foreign_keys='Doctor.user_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def role_name(self):
        return self.role.name if self.role else ''

    @property
    def is_admin(self):
        return self.role and self.role.slug in ('admin', 'super_admin')

    @property
    def is_doctor(self):
        return self.role and self.role.slug == 'doctor'

    @property
    def is_donor(self):
        return self.role and self.role.slug == 'donor'

    @property
    def is_patient(self):
        return self.role and self.role.slug == 'patient'

    @property
    def is_hospital_staff(self):
        return self.role and self.role.slug in ('hospital_staff', 'hospital')

    def __repr__(self):
        return f"<User {self.username} ({self.email})>"


class LoginLog(BaseModel):
    """User authentication audit log."""
    __tablename__ = 'login_logs'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    login_status = db.Column(db.String(20), nullable=False)  # 'SUCCESS', 'FAILED'
    failure_reason = db.Column(db.String(100), nullable=True)

    user = db.relationship('User', back_populates='login_logs', foreign_keys=[user_id])


class AuditLog(BaseModel):
    """System-wide entity change audit log."""
    __tablename__ = 'audit_logs'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    action = db.Column(db.String(50), nullable=False)  # 'CREATE', 'UPDATE', 'SOFT_DELETE', 'RESTORE'
    table_name = db.Column(db.String(50), nullable=False)
    record_id = db.Column(db.Integer, nullable=True)
    old_values = db.Column(db.Text, nullable=True)
    new_values = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id])
