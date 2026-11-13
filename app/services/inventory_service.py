from datetime import datetime, date
import secrets
from app.extensions import db


def generate_unit_number(blood_group_name=None):
    """
    Generates a unique, collision-free blood unit barcode identifier.
    Format: LB-{BG}-{YYMMDD}-{HEX}
    """
    bg_code = (blood_group_name or 'UNK').replace('+', 'POS').replace('-', 'NEG').replace(' ', '')
    today = date.today()
    return f"LB-{bg_code}-{today.strftime('%y%m%d')}-{secrets.token_hex(3).upper()}"


def check_and_expire_units():
    """Auto-mark units as Expired once past their expiry_date."""
    from app.models.inventory import BloodUnit
    today = date.today()
    expired = BloodUnit.active_query().filter(
        BloodUnit.status == 'Available',
        BloodUnit.expiry_date < today
    ).all()
    if expired:
        affected_banks = set()
        for u in expired:
            u.status = 'Expired'
            u.updated_at = datetime.utcnow()
            if u.blood_bank_id:
                affected_banks.add(u.blood_bank_id)
        try:
            db.session.commit()
            for b_id in affected_banks:
                sync_blood_bank_stock(b_id)
        except Exception:
            db.session.rollback()


def sync_blood_bank_stock(blood_bank_id):
    """Dynamic stock recomputation for a hospital blood bank based on Available units."""
    from app.models.hospital import HospitalBloodBank
    from app.models.inventory import BloodUnit
    bank = HospitalBloodBank.get_by_id(blood_bank_id)
    if bank:
        count = BloodUnit.active_query().filter_by(
            blood_bank_id=blood_bank_id,
            status='Available'
        ).count()
        bank.current_stock_units = count
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        return count
    return 0
