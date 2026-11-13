from datetime import datetime, date
from app.extensions import db


def validate_donor_eligibility(donor):
    """
    Clinically validates whether a donor is currently eligible to donate blood.
    Returns (is_eligible: bool, reason: str | None).
    """
    if not donor:
        return False, "Donor not found."

    age = donor.age
    if age is None or not (18 <= age <= 60):
        return False, f"Donor age ({age or 'unknown'}) is outside the eligible range (18-60 years)."

    if (donor.weight_kg or 0) < 50.0:
        return False, f"Donor weight ({donor.weight_kg} kg) is below the minimum required 50 kg."

    if donor.last_donation_date and donor.days_since_last_donation < 90:
        days_left = 90 - donor.days_since_last_donation
        return False, f"Donor must wait {days_left} more day(s) before donating again (minimum 90-day cooldown)."

    if donor.donation_eligibility_status != 'Eligible':
        return False, f"Donor status is '{donor.donation_eligibility_status}'. Only 'Eligible' donors may donate."

    return True, None


def check_and_award_donor_badges(donor):
    """Awards gamification badges to donors according to lifetime donation counts."""
    from app.models.donor import Badge, DonorBadge
    from app.utils import create_notification
    try:
        badges = Badge.active_query().order_by(Badge.min_donations_required.asc()).all()
        current_badge_ids = [b.badge_id for b in donor.badges if not b.is_deleted]
        
        for b in badges:
            if donor.total_donations >= b.min_donations_required and b.id not in current_badge_ids:
                new_db = DonorBadge(
                    donor_id=donor.id,
                    badge_id=b.id,
                    awarded_at=datetime.utcnow()
                )
                db.session.add(new_db)
                create_notification(
                    user_id=donor.user_id,
                    title="New Badge Unlocked! 🏅",
                    message=f"Congratulations! You've been awarded the '{b.name}' badge for completing {donor.total_donations} life-saving donations.",
                    notification_type="System",
                    link_url="/donors/profile"
                )
        db.session.commit()
    except Exception:
        db.session.rollback()
