import pytest
from app.models.auth import User, Role, LoginLog
from app.models.patient import Patient
from app.models.donor import Donor
from app.extensions import db


def test_public_routes_protected_against_leaks(client):
    """Ensure requests and donors lists/views require authentication."""
    # Unauthenticated accesses must redirect to login
    for path in ['/requests/', '/requests/1', '/requests/emergency/active', '/donors/', '/donors/1']:
        res = client.get(path, follow_redirects=False)
        assert res.status_code == 302
        assert '/auth/login' in res.headers['Location']


def test_rbac_bypass_fix(client, app):
    """Ensure non-admin cannot access routes where their role is not explicitly allowed."""
    with app.app_context():
        donor_role = Role.query.filter_by(slug='donor').first()
        donor_user = User(
            username='test_rbac_donor',
            email='rbac_donor@example.com',
            full_name='RBAC Donor',
            phone='03009998877',
            role_id=donor_role.id
        )
        donor_user.set_password('Secret123')
        db.session.add(donor_user)
        db.session.commit()
        donor_id = donor_user.id

    # Log in as donor
    with client.session_transaction() as sess:
        sess['user_id'] = donor_id
        sess['user_role'] = 'donor'

    # Admin route: /admin/users -> must return 403
    res = client.get('/admin/users')
    assert res.status_code == 403

    # Patient creation route: /patients/create -> must return 403 for donor
    res = client.get('/patients/create')
    assert res.status_code == 403


def test_open_redirect_protection(client, auth_client):
    """Ensure login next parameter rejects malicious open redirects."""
    # Attempt login with external or protocol-relative redirect
    bad_urls = ['//attacker.com', '/\\attacker.com', 'http://attacker.com']
    for bad in bad_urls:
        res = client.post('/auth/login', data={
            'login_identifier': 'admin',
            'password': 'AdminPassword123!',
            'next': bad
        }, follow_redirects=False)
        # Should redirect to default dashboard, NOT to the attacker URL
        assert res.status_code == 302
        assert res.headers['Location'] == '/' or '/main' in res.headers['Location']


def test_login_brute_force_rate_limit(client, app):
    """Ensure login locks/returns 429 after 5 failed attempts."""
    for _ in range(5):
        res = client.post('/auth/login', data={
            'login_identifier': 'admin',
            'password': 'wrongpassword'
        })
        assert res.status_code == 200

    # 6th attempt should be blocked with 429
    res = client.post('/auth/login', data={
        'login_identifier': 'admin',
        'password': 'wrongpassword'
    })
    assert res.status_code == 429
    assert b'Too many failed login attempts' in res.data


def test_inactive_account_blocked(client, app):
    """Ensure inactive account is kicked out and cannot login."""
    with app.app_context():
        donor_role = Role.query.filter_by(slug='donor').first()
        user = User(
            username='inactive_tester',
            email='inactive@example.com',
            full_name='Inactive Tester',
            phone='03001112233',
            role_id=donor_role.id,
            is_active_account=False
        )
        user.set_password('Password123!')
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    res = client.post('/auth/login', data={
        'login_identifier': 'inactive_tester',
        'password': 'Password123!'
    })
    assert b'deactivated' in res.data or res.status_code == 200

    # Inactive session check
    with client.session_transaction() as sess:
        sess['user_id'] = user_id

    res = client.get('/patients/')
    # Should clear session and redirect to login
    assert res.status_code == 302
    assert '/auth/login' in res.headers['Location']
