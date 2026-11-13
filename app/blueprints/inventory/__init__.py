from datetime import datetime, date, timedelta
import secrets
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models import (
    BloodUnit,
    InventoryTransaction,
    HospitalBloodBank,
    BloodGroup,
    Donor,
    User
)
from app.utils import get_current_user, login_required, role_required, log_audit
from app.services.inventory_service import check_and_expire_units, sync_blood_bank_stock, generate_unit_number

inventory_bp = Blueprint('inventory', __name__)


@inventory_bp.route('/')
@login_required
def index():
    check_and_expire_units()
    user = get_current_user()

    if user.is_hospital_staff and user.hospital_id:
        blood_banks = HospitalBloodBank.active_query().filter_by(hospital_id=user.hospital_id).all()
    else:
        blood_banks = HospitalBloodBank.active_query().all()

    # Recompute active stock for all loaded banks
    for b in blood_banks:
        sync_blood_bank_stock(b.id)

    blood_groups = BloodGroup.active_query().order_by(BloodGroup.name).all()

    # Single SQL GROUP BY count query to eliminate N+1 loops
    from sqlalchemy import func
    counts_q = db.session.query(
        BloodGroup.name,
        func.count(BloodUnit.id)
    ).join(BloodUnit, BloodGroup.id == BloodUnit.blood_group_id).filter(
        BloodUnit.is_deleted == False,
        BloodUnit.status == 'Available'
    )
    if user.is_hospital_staff and user.hospital_id:
        counts_q = counts_q.join(HospitalBloodBank, BloodUnit.blood_bank_id == HospitalBloodBank.id).filter(
            HospitalBloodBank.hospital_id == user.hospital_id
        )
    counts_dict = dict(counts_q.group_by(BloodGroup.name).all())
    bg_counts = {bg.name: counts_dict.get(bg.name, 0) for bg in blood_groups}

    today = date.today()
    soon_q = BloodUnit.active_query().filter(
        BloodUnit.status == 'Available',
        BloodUnit.expiry_date >= today,
        BloodUnit.expiry_date <= today + timedelta(days=7)
    )
    exp_q = BloodUnit.active_query().filter(
        BloodUnit.status.in_(['Available', 'Expired']),
        BloodUnit.expiry_date < today
    )

    if user.is_hospital_staff and user.hospital_id:
        soon_q = soon_q.join(HospitalBloodBank).filter(HospitalBloodBank.hospital_id == user.hospital_id)
        exp_q = exp_q.join(HospitalBloodBank).filter(HospitalBloodBank.hospital_id == user.hospital_id)

    expiring_soon_units = soon_q.all()
    expired_units = exp_q.all()
    low_stock_groups = [name for name, count in bg_counts.items() if count < 5]

    return render_template(
        'inventory/dashboard.html',
        blood_banks=blood_banks,
        blood_groups=blood_groups,
        bg_counts=bg_counts,
        expiring_soon_units=expiring_soon_units,
        expired_units=expired_units,
        low_stock_groups=low_stock_groups
    )


@inventory_bp.route('/units')
@login_required
def units():
    check_and_expire_units()
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    blood_group_id = request.args.get('blood_group_id', type=int)
    status = request.args.get('status', '').strip()
    component_type = request.args.get('component_type', '').strip()

    query = BloodUnit.active_query().options(
        joinedload(BloodUnit.blood_group),
        joinedload(BloodUnit.blood_bank)
    )

    if user.is_hospital_staff and user.hospital_id:
        query = query.join(HospitalBloodBank).filter(HospitalBloodBank.hospital_id == user.hospital_id)

    if search:
        query = query.filter(BloodUnit.unit_number.ilike(f"%{search}%"))
    if blood_group_id:
        query = query.filter(BloodUnit.blood_group_id == blood_group_id)
    if status:
        query = query.filter(BloodUnit.status == status)
    if component_type:
        query = query.filter(BloodUnit.component_type == component_type)

    pagination = query.order_by(BloodUnit.expiry_date.asc()).paginate(page=page, per_page=10, error_out=False)
    blood_groups = BloodGroup.active_query().order_by(BloodGroup.name).all()

    return render_template(
        'inventory/units.html',
        pagination=pagination,
        units=pagination.items,
        search=search,
        selected_bg=blood_group_id,
        selected_status=status,
        selected_component=component_type,
        blood_groups=blood_groups
    )


@inventory_bp.route('/units/add', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'hospital_staff')
def add_unit():
    user = get_current_user()
    if user.is_hospital_staff and user.hospital_id:
        blood_banks = HospitalBloodBank.active_query().filter_by(hospital_id=user.hospital_id).all()
    else:
        blood_banks = HospitalBloodBank.active_query().all()

    blood_groups = BloodGroup.active_query().order_by(BloodGroup.name).all()
    donors = Donor.active_query().all()

    if request.method == 'POST':
        blood_bank_id = request.form.get('blood_bank_id', type=int)
        blood_group_id = request.form.get('blood_group_id', type=int)
        component_type = request.form.get('component_type', 'PRBC')
        donation_date_str = request.form.get('donation_date', '')
        expiry_date_str = request.form.get('expiry_date', '')
        donor_id = request.form.get('donor_id', type=int)
        volume_ml = request.form.get('volume_ml', 450, type=int)
        storage_location = request.form.get('storage_location', 'Shelf A')

        # Hospital scoping enforcement
        selected_bank = HospitalBloodBank.get_by_id(blood_bank_id)
        if not selected_bank:
            flash('Invalid blood bank selected.', 'danger')
            return render_template('inventory/add_unit.html', blood_banks=blood_banks, blood_groups=blood_groups, donors=donors)

        if user.is_hospital_staff and user.hospital_id and selected_bank.hospital_id != user.hospital_id:
            abort(403)

        bg = BloodGroup.get_by_id(blood_group_id)
        if not bg:
            flash('Valid blood group is required.', 'danger')
            return render_template('inventory/add_unit.html', blood_banks=blood_banks, blood_groups=blood_groups, donors=donors)

        if not (200 <= volume_ml <= 550):
            flash('Collected blood volume must be between 200 and 550 mL.', 'danger')
            return render_template('inventory/add_unit.html', blood_banks=blood_banks, blood_groups=blood_groups, donors=donors)

        try:
            today = date.today()
            donation_date = datetime.strptime(donation_date_str, '%Y-%m-%d').date() if donation_date_str else today
            # PRBC typically expires in 35-42 days
            expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date() if expiry_date_str else donation_date + timedelta(days=35)

            if expiry_date <= donation_date:
                flash('Expiry date must be after donation date.', 'danger')
                return render_template('inventory/add_unit.html', blood_banks=blood_banks, blood_groups=blood_groups, donors=donors)

            # Collision-free unit number generator via domain service
            unit_number = generate_unit_number(bg.name)

            unit = BloodUnit(
                blood_bank_id=blood_bank_id,
                unit_number=unit_number,
                blood_group_id=blood_group_id,
                component_type=component_type,
                donation_date=donation_date,
                expiry_date=expiry_date,
                donor_id=donor_id or None,
                volume_ml=volume_ml or 450,
                status='Available',
                storage_location=storage_location,
                created_by=user.id
            )
            db.session.add(unit)
            db.session.flush()

            # Record inventory transaction
            transaction = InventoryTransaction(
                blood_bank_id=blood_bank_id,
                blood_unit_id=unit.id,
                transaction_type='IN_DONATION',
                quantity=1,
                reason='Direct donor collection',
                performed_by_user_id=user.id,
                created_by=user.id
            )
            db.session.add(transaction)

            # Recompute dynamic blood bank stock
            sync_blood_bank_stock(blood_bank_id)

            db.session.commit()
            log_audit(user.id, 'CREATE', 'blood_units', unit.id, None, {'unit_number': unit_number})
            flash(f'Blood unit {unit_number} added to inventory.', 'success')
            return redirect(url_for('inventory.units'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Failed to add blood unit')
            flash('Failed to add unit. Please verify inputs.', 'danger')

    return render_template('inventory/add_unit.html', blood_banks=blood_banks, blood_groups=blood_groups, donors=donors)


@inventory_bp.route('/units/<int:id>')
@login_required
def view_unit(id):
    unit = BloodUnit.active_query().filter_by(id=id).first_or_404()
    transactions = InventoryTransaction.active_query().filter_by(blood_unit_id=unit.id).order_by(InventoryTransaction.created_at.desc()).all()
    return render_template('inventory/view_unit.html', unit=unit, transactions=transactions)


@inventory_bp.route('/units/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'hospital_staff')
def edit_unit(id):
    unit = BloodUnit.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()

    # Hospital staff can only edit units in their assigned hospital
    if user.is_hospital_staff and user.hospital_id and unit.blood_bank and unit.blood_bank.hospital_id != user.hospital_id:
        abort(403)

    if request.method == 'POST':
        new_status = request.form.get('status')
        new_location = request.form.get('storage_location')
        reason = request.form.get('reason', 'Status adjustment')

        valid_statuses = ['Available', 'Reserved', 'Transfused', 'Discarded', 'Expired']
        if new_status not in valid_statuses:
            flash(f'Invalid status "{new_status}". Allowed values: {", ".join(valid_statuses)}.', 'danger')
            return render_template('inventory/edit_unit.html', unit=unit)

        old_status = unit.status

        # Clinical boundary: terminal statuses cannot revert to active inventory
        if old_status in ('Transfused', 'Discarded', 'Expired') and new_status in ('Available', 'Reserved'):
            flash(f'Terminal status "{old_status}" cannot be reverted to "{new_status}".', 'danger')
            return render_template('inventory/edit_unit.html', unit=unit)

        unit.status = new_status
        unit.storage_location = new_location
        unit.updated_by = user.id

        if old_status != new_status:
            # Explicit transaction type mapping
            if new_status == 'Reserved':
                tx_type = 'RESERVE'
            elif new_status == 'Available' and old_status == 'Reserved':
                tx_type = 'UNRESERVE'
            elif new_status == 'Discarded':
                tx_type = 'OUT_DISCARD'
            elif new_status == 'Expired':
                tx_type = 'OUT_EXPIRED'
            elif new_status == 'Transfused':
                tx_type = 'OUT_TRANSFUSE'
            else:
                tx_type = 'TRANSFER'

            tx = InventoryTransaction(
                blood_bank_id=unit.blood_bank_id,
                blood_unit_id=unit.id,
                transaction_type=tx_type,
                quantity=1,
                reason=f"Status changed from {old_status} to {new_status}: {reason}",
                performed_by_user_id=user.id,
                created_by=user.id
            )
            db.session.add(tx)

        try:
            db.session.commit()
            if unit.blood_bank_id:
                sync_blood_bank_stock(unit.blood_bank_id)
            log_audit(user.id, 'UPDATE', 'blood_units', unit.id, {'status': old_status}, {'status': new_status})
            flash(f'Unit {unit.unit_number} updated.', 'success')
            return redirect(url_for('inventory.view_unit', id=unit.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Unit update failed')
            flash('Update failed. Please check inputs and try again.', 'danger')

    return render_template('inventory/edit_unit.html', unit=unit)


@inventory_bp.route('/units/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_unit(id):
    unit = BloodUnit.active_query().filter_by(id=id).first_or_404()
    user = get_current_user()
    bank_id = unit.blood_bank_id
    unit.soft_delete(user.id)
    
    try:
        db.session.commit()
        if bank_id:
            sync_blood_bank_stock(bank_id)
        log_audit(user.id, 'SOFT_DELETE', 'blood_units', unit.id)
        flash('Blood unit soft-deleted.', 'warning')
    except Exception:
        db.session.rollback()
        flash('Delete failed.', 'danger')

    return redirect(url_for('inventory.units'))


@inventory_bp.route('/transactions')
@login_required
def transactions():
    page = request.args.get('page', 1, type=int)
    pagination = InventoryTransaction.active_query().options(
        joinedload(InventoryTransaction.blood_unit),
        joinedload(InventoryTransaction.blood_bank)
    ).order_by(InventoryTransaction.created_at.desc()).paginate(page=page, per_page=15, error_out=False)

    return render_template('inventory/transactions.html', pagination=pagination, transactions=pagination.items)
