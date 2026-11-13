"""
LifeBridge Core Domain Services Package.
Encapsulates critical business logic, matching algorithms, clinical rules, and stock management.
"""

from app.services.matching_service import find_and_match_donors, expire_emergency_broadcasts
from app.services.inventory_service import check_and_expire_units, sync_blood_bank_stock, generate_unit_number
from app.services.transfusion_service import validate_transfusion_execution, get_compatible_blood_group_ids
from app.services.donation_service import check_and_award_donor_badges, validate_donor_eligibility
