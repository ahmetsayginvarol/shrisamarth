"""Add check-in fields, route_stops, notifications, seat_locks, user fields

Revision ID: 94e197e11bfb
Revises: 1263fe8f5988
Create Date: 2026-05-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '94e197e11bfb'
down_revision = '1263fe8f5988'
branch_labels = None
depends_on = None


def upgrade():
    # ── users: phone, gender, credit_balance ────────────────────────────────
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('phone', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('gender', sa.String(length=1), nullable=True))
        batch_op.add_column(sa.Column('credit_balance', sa.Numeric(10, 2), nullable=False, server_default='0'))

    # ── voyages: recurrence_group ────────────────────────────────────────────
    with op.batch_alter_table('voyages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('recurrence_group', sa.String(length=30), nullable=True))
        batch_op.create_index('ix_voyages_recurrence_group', ['recurrence_group'], unique=False)

    # ── bookings: passenger_email, boarded_at, boarded_by_id ────────────────
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('passenger_email', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('boarded_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('boarded_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_bookings_boarded_by_id_users',
            'users', ['boarded_by_id'], ['id']
        )

    # ── route_stops ──────────────────────────────────────────────────────────
    op.create_table(
        'route_stops',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('voyage_id', sa.Integer(), nullable=False),
        sa.Column('stop_name', sa.String(length=80), nullable=False),
        sa.Column('stop_type', sa.String(length=10), nullable=False),
        sa.Column('stop_time', sa.String(length=5), nullable=True),
        sa.Column('stop_order', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['voyage_id'], ['voyages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── notifications ────────────────────────────────────────────────────────
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('link', sa.String(length=500), nullable=True),
        sa.Column('booking_id', sa.Integer(), nullable=True),
        sa.Column('passenger_phone', sa.String(length=20), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True, index=True),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])

    # ── seat_locks ───────────────────────────────────────────────────────────
    op.create_table(
        'seat_locks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('voyage_id', sa.Integer(), nullable=False),
        sa.Column('seat_id', sa.String(length=8), nullable=False),
        sa.Column('session_id', sa.String(length=64), nullable=False),
        sa.Column('locked_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['voyage_id'], ['voyages.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('seat_locks')
    op.drop_index('ix_notifications_created_at', table_name='notifications')
    op.drop_table('notifications')
    op.drop_table('route_stops')

    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_constraint('fk_bookings_boarded_by_id_users', type_='foreignkey')
        batch_op.drop_column('boarded_by_id')
        batch_op.drop_column('boarded_at')
        batch_op.drop_column('passenger_email')

    with op.batch_alter_table('voyages', schema=None) as batch_op:
        batch_op.drop_index('ix_voyages_recurrence_group')
        batch_op.drop_column('recurrence_group')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('credit_balance')
        batch_op.drop_column('gender')
        batch_op.drop_column('phone')
