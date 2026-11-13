import sys
from pathlib import Path
import pytest

# Ensure lifebridge root directory is in python path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import create_app
from app.extensions import db
from app.models import Role, User, City, BloodGroup, Diagnosis


@pytest.fixture
def app():
    """Create and configure a clean testing app instance with an in-memory SQLite database."""
    app = create_app('testing')
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret'
    })

    with app.app_context():
        db.create_all()

        # Seed minimal roles
        admin_role = Role(name='Admin', slug='admin', description='Administrator')
        patient_role = Role(name='Patient', slug='patient', description='Patient')
        donor_role = Role(name='Donor', slug='donor', description='Donor')
        db.session.add_all([admin_role, patient_role, donor_role])

        # Seed sample city
        city = City(name='Karachi', country='Pakistan')
        db.session.add(city)

        # Seed sample blood groups
        bg1 = BloodGroup(name='B+', rh_factor='Positive', can_donate_to='B+, AB+', can_receive_from='O-, O+, B-, B+')
        bg2 = BloodGroup(name='O+', rh_factor='Positive', can_donate_to='O+, A+, B+, AB+', can_receive_from='O-, O+')
        db.session.add_all([bg1, bg2])

        # Seed sample diagnosis
        diag = Diagnosis(code='D56.1', name='Beta Thalassemia Major', category='Hemoglobinopathy')
        db.session.add(diag)

        # Seed admin user
        admin = User(
            username='admin_test',
            email='admin@test.com',
            full_name='Test Admin',
            phone='0300-1234567',
            role_id=1,
            is_active_account=True
        )
        admin.set_password('Admin@123')
        db.session.add(admin)

        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def auth_client(client, app):
    """A test client logged in as Admin."""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['user_role'] = 'admin'
        sess['user_name'] = 'Test Admin'
    return client
