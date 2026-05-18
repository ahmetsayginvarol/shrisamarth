"""make_booking_gender_nullable

Revision ID: e81025379ac4
Revises: 94e197e11bfb
Create Date: 2026-05-18 22:08:13.821123

"""
from alembic import op
import sqlalchemy as sa


revision = 'e81025379ac4'
down_revision = '94e197e11bfb'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.alter_column('gender',
               existing_type=sa.VARCHAR(length=1),
               nullable=True)


def downgrade():
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.alter_column('gender',
               existing_type=sa.VARCHAR(length=1),
               nullable=False)
