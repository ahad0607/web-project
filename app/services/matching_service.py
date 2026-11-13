from datetime import datetime, timedelta
from flask import url_for, has_request_context
from app.extensions import db


def find_and_match_donors(emergency_request, max_donors=10, commit=True):
    """
    Ranks and matches available donors based on blood compatibility, location proximity,
    and emergency availability. Creates DonorMatch records with 24-hour expiration.
    """
    from app.models.donor import Donor
    from app.models.request import DonorMatch
    from app.models.reference import BloodGroup
    from app.utils import create_notification
    
    req_group = BloodGroup.get_by_id(emergency_request.blood_group_id)
    if not req_group:
        return 0

    compatible_donors = [x.strip() for x in (req_group.can_receive_from or '').split(',') if x.strip()]
    if req_group.name not in compatible_donors:
        compatible_donors.append(req_group.name)

    # Fetch donors with matching blood groups in the same city
    query = Donor.active_query().join(BloodGroup).filter(
        BloodGroup.name.in_(compatible_donors)
    )
    if emergency_request.hospital and emergency_request.hospital.city_id:
        query = query.filter(Donor.city_id == emergency_request.hospital.city_id)

    donors = query.all()
    candidates = []

    for donor in donors:
        # Check clinical eligibility
        if not donor.is_eligible_to_donate:
            continue
        
        # Check emergency availability
        if donor.availability and not donor.availability.is_available_for_emergency:
            continue

        # Prevent duplicate matching
        existing = DonorMatch.active_query().filter_by(
            emergency_request_id=emergency_request.id,
            donor_id=donor.id
        ).first()
        if existing:
            continue

        # Calculate score (100 for exact blood group match, 85 for compatible)
        match_score = 100.0 if (donor.blood_group and donor.blood_group.name == req_group.name) else 85.0
        
        # Estimate distance based on area/city locality
        if emergency_request.hospital and donor.area_id and emergency_request.hospital.area_id == donor.area_id:
            distance = 2.5
        elif emergency_request.hospital and donor.city_id and emergency_request.hospital.city_id == donor.city_id:
            distance = 6.0
        else:
            distance = 12.0

        # Honour broadcast_radius_km and donor travel_radius_km
        broadcast_limit = emergency_request.broadcast_radius_km or 30
        donor_travel_limit = (donor.availability.travel_radius_km or 25) if donor.availability else 25
        if distance > broadcast_limit or distance > donor_travel_limit:
            continue

        candidates.append((match_score, -distance, donor.days_since_last_donation, donor, distance))

    # Rank candidates: highest score first, closest distance second, then longest time since last donation
    candidates.sort(key=lambda c: (c[0], c[1], c[2]), reverse=True)
    top_candidates = candidates[:max_donors]

    matches_created = 0
    expires_at = datetime.utcnow() + timedelta(hours=24)

    for match_score, _, _, donor, distance in top_candidates:
        match = DonorMatch(
            emergency_request_id=emergency_request.id,
            donor_id=donor.id,
            match_score=match_score,
            match_distance_km=distance,
            status='Notified',
            notified_at=datetime.utcnow(),
            expires_at=expires_at,
            created_by=emergency_request.created_by
        )
        db.session.add(match)
        matches_created += 1

        # Notify donor immediately
        create_notification(
            user_id=donor.user_id,
            title="🚨 URGENT: Blood Request Match!",
            message=f"Urgent emergency request for {req_group.name} blood at {emergency_request.hospital.name if emergency_request.hospital else 'Hospital'}. Can you donate?",
            notification_type="Emergency",
            link_url=url_for('donors.emergency_matches') if has_request_context() else '/donors/emergency-matches',
            commit=False
        )

    if commit:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return 0

    return matches_created


def expire_emergency_broadcasts():
    """Auto-expires emergency broadcasts past their expired_at date and marks pending matches Timed Out."""
    from app.models.request import EmergencyRequest
    now = datetime.utcnow()
    expired_reqs = EmergencyRequest.active_query().filter(
        EmergencyRequest.is_broadcast_active == True,
        EmergencyRequest.expired_at != None,
        EmergencyRequest.expired_at < now
    ).all()
    if expired_reqs:
        for em in expired_reqs:
            em.is_broadcast_active = False
            em.status = 'Expired'
            for m in em.donor_matches:
                if not m.is_deleted and m.status == 'Notified':
                    m.status = 'Timed Out'
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
