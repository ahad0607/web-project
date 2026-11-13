from app.models import City, User
from app.extensions import db


def test_soft_delete_mechanism(app):
    """Verify that soft delete marks row as deleted without removing from database."""
    with app.app_context():
        # Create a test city
        city = City(name='Peshawar Test', country='Pakistan')
        db.session.add(city)
        db.session.commit()
        city_id = city.id

        # Check it is active
        assert City.active_query().filter_by(id=city_id).first() is not None

        # Perform soft delete by admin user (id=1)
        city.soft_delete(user_id=1)
        db.session.commit()

        # Check instance properties
        assert city.is_deleted is True
        assert city.record_status == 'deactive'
        assert city.status == 'deactive'
        assert city.deleted_by == 1

        # Check active_query() excludes this record
        assert City.active_query().filter_by(id=city_id).first() is None

        # Verify record STILL physically exists in the database table (no hard deletion)
        raw_record = db.session.query(City).filter_by(id=city_id).first()
        assert raw_record is not None
        assert raw_record.is_deleted is True

        # Test restore functionality
        raw_record.restore(user_id=1)
        db.session.commit()

        assert raw_record.is_deleted is False
        assert raw_record.record_status == 'active'
        assert raw_record.status == 'active'
        assert City.active_query().filter_by(id=city_id).first() is not None
