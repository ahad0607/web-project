from datetime import date, datetime
from app.extensions import db


def get_compatible_blood_group_ids(patient_blood_group_id):
    """Returns a list of compatible donor blood group IDs for a recipient."""
    from app.models.reference import BloodGroup
    patient_bg = BloodGroup.get_by_id(patient_blood_group_id)
    if not patient_bg:
        return []
    
    compatible_ids = []
    for bg in BloodGroup.active_query().all():
        if patient_bg.is_compatible_recipient(bg.name):
            compatible_ids.append(bg.id)
    return compatible_ids if compatible_ids else [patient_blood_group_id]


def validate_transfusion_execution(schedule, blood_unit, pre_hb, post_hb, start_time='10:00', end_time='13:30'):
    """
    Performs clinical verification before executing a blood transfusion.
    Returns (is_valid: bool, error_message: str | None).
    """
    if schedule.status != 'Scheduled':
        return False, 'This transfusion schedule has already been executed or cancelled.'

    if not blood_unit or blood_unit.is_deleted:
        return False, 'Selected blood unit is not valid.'

    if blood_unit.status != 'Available':
        return False, f'Selected blood unit is not Available (current status: {blood_unit.status}).'

    if blood_unit.expiry_date < date.today():
        return False, f'Blood unit {blood_unit.unit_number} expired on {blood_unit.expiry_date} and cannot be transfused.'

    if schedule.hospital_id and blood_unit.blood_bank and blood_unit.blood_bank.hospital_id != schedule.hospital_id:
        return False, 'Selected blood unit does not belong to the schedule hospital blood bank.'

    # Check recipient compatibility
    compatible_groups = get_compatible_blood_group_ids(schedule.blood_group_id)
    if blood_unit.blood_group_id not in compatible_groups:
        return False, f'Blood unit group ({blood_unit.blood_group.name if blood_unit.blood_group else "Unknown"}) is incompatible with patient.'

    # Clinical Hb limits
    if pre_hb is None or not (2.0 <= pre_hb <= 20.0):
        return False, 'Pre-transfusion hemoglobin must be clinically valid (between 2.0 and 20.0 g/dL).'
    if post_hb is None or not (2.0 <= post_hb <= 20.0):
        return False, 'Post-transfusion hemoglobin must be clinically valid (between 2.0 and 20.0 g/dL).'

    # Valid times
    try:
        t_start = datetime.strptime(start_time, '%H:%M').time()
        t_end = datetime.strptime(end_time, '%H:%M').time()
        if t_end <= t_start:
            return False, 'Transfusion completion time must be strictly after start time.'
    except (ValueError, TypeError):
        return False, 'Invalid start or end time format (expected HH:MM).'

    return True, None
