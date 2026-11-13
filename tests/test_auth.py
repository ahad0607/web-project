from app.models import User


def test_user_registration(client, app):
    """Test standard user registration flow with validations."""
    response = client.post('/auth/register', data={
        'username': 'new_user',
        'email': 'new_user@example.com',
        'password': 'Password@123',
        'confirm_password': 'Password@123',
        'full_name': 'New Register User',
        'phone': '0300-9876543',
        'role_id': 2,
        'city_id': 1
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(username='new_user').first()
        assert user is not None
        assert user.check_password('Password@123') is True
        assert user.check_password('WrongPass') is False


def test_login_success_and_logout(client):
    """Test valid credential authentication and logout."""
    # Login
    response = client.post('/auth/login', data={
        'login_identifier': 'admin@test.com',
        'password': 'Admin@123'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Welcome back' in response.data

    # Check session
    with client.session_transaction() as sess:
        assert sess['user_id'] == 1
        assert sess['user_role'] == 'admin'

    # Logout
    logout_resp = client.get('/auth/logout', follow_redirects=True)
    assert logout_resp.status_code == 200
    with client.session_transaction() as sess:
        assert 'user_id' not in sess


def test_login_invalid_password(client):
    """Test login failure on invalid password."""
    response = client.post('/auth/login', data={
        'login_identifier': 'admin@test.com',
        'password': 'WrongPassword999'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Invalid username/email or password' in response.data


def test_rbac_access_control(client):
    """Test that unauthorized user is redirected to login for protected pages."""
    response = client.get('/patients/create')
    assert response.status_code == 302
    assert '/auth/login' in response.location
