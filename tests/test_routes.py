def test_public_routes(app):
    """Test public endpoints with a clean, unauthenticated client."""
    client = app.test_client()
    assert client.get('/auth/login').status_code == 200
    assert client.get('/auth/register').status_code == 200
    assert client.get('/about').status_code == 200
    assert client.get('/').status_code == 200


def test_authenticated_admin_routes(auth_client):
    """Smoke test ensuring every blueprint's key views render with status 200 without Jinja or SQL errors."""
    admin_endpoints = [
        '/',
        '/about',
        '/notifications',
        '/auth/profile',
        '/patients/',
        '/patients/create',
        '/donors/',
        '/donors/register',
        '/donors/badges',
        '/hospitals/',
        '/hospitals/create',
        '/inventory/',
        '/inventory/units',
        '/inventory/transactions',
        '/inventory/units/add',
        '/requests/',
        '/requests/create',
        '/requests/emergency/active',
        '/transfusions/schedules',
        '/transfusions/schedules/create',
        '/transfusions/records',
        '/care/appointments',
        '/care/appointments/create',
        '/care/medications',
        '/care/patient-medications/prescribe',
        '/care/chelation/record',
        '/campaigns/',
        '/campaigns/create',
        '/admin/',
        '/admin/users',
        '/admin/audit-logs',
        '/admin/login-logs',
        '/admin/reference/cities',
        '/admin/reference/areas',
        '/admin/reference/blood-groups',
        '/admin/reference/diagnoses',
        '/admin/feedback'
    ]

    for ep in admin_endpoints:
        resp = auth_client.get(ep)
        assert resp.status_code == 200, f"Route {ep} failed with status {resp.status_code}"
