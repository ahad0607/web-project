from datetime import datetime, timezone
from app.extensions import db


def utcnow():
    """Returns timezone-naive UTC datetime for consistent database storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BaseModel(db.Model):
    """
    Abstract base model providing primary key, audit timestamps,
    user audit tracking, record status, and soft-delete capabilities across all tables.
    """
    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', use_alter=True, name='fk_%(table_name)s_created_by'), nullable=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id', use_alter=True, name='fk_%(table_name)s_updated_by'), nullable=True)
    record_status = db.Column(db.String(20), default='active', nullable=False)  # 'active' / 'deactive'
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    deleted_by = db.Column(db.Integer, db.ForeignKey('users.id', use_alter=True, name='fk_%(table_name)s_deleted_by'), nullable=True)

    @property
    def status(self):
        """Fallback for models without an explicit domain status column."""
        return self.record_status

    @status.setter
    def status(self, val):
        self.record_status = val

    @classmethod
    def active_query(cls):
        """Returns a base query excluding soft-deleted records."""
        return cls.query.filter(cls.is_deleted.is_(False))

    @classmethod
    def deleted_query(cls):
        """Returns a query of only soft-deleted records."""
        return cls.query.filter(cls.is_deleted.is_(True))

    @classmethod
    def get_by_id(cls, record_id):
        """Fetch active record by ID."""
        return cls.active_query().filter(cls.id == record_id).first()

    def soft_delete(self, user_id=None):
        """Soft-deletes this instance instead of hard-deleting from database."""
        self.is_deleted = True
        self.record_status = 'deactive'
        self.deleted_by = user_id
        self.updated_at = utcnow()
        if user_id:
            self.updated_by = user_id

    def restore(self, user_id=None):
        """Restores a soft-deleted record."""
        self.is_deleted = False
        self.record_status = 'active'
        self.deleted_by = None
        self.updated_at = utcnow()
        if user_id:
            self.updated_by = user_id
