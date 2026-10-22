"""drop unused order and trip_drivers tables

Revision ID: 6ef364e81ac1
Revises: 6afe8891b3d3
Create Date: 2026-10-22 14:33:31.055381

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6ef364e81ac1'
down_revision = '6afe8891b3d3'
branch_labels = None
depends_on = None


def upgrade():
    # Neither table was ever read or written by the app - trips use trip_order and
    # trip.driver1_id/driver2_id instead.
    op.drop_table('trip_drivers')
    op.drop_table('order')


def downgrade():
    op.create_table('order',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trip_id', sa.Integer(), nullable=True),
    sa.Column('leaftrade_order_id', sa.String(length=100), nullable=False),
    sa.Column('invoice_id', sa.String(length=100), nullable=True),
    sa.Column('biotrack_manifest_id', sa.String(length=100), nullable=True),
    sa.Column('delivery_date', sa.Date(), nullable=True),
    sa.Column('customer_name', sa.String(length=200), nullable=True),
    sa.Column('customer_contact', sa.String(length=200), nullable=True),
    sa.Column('customer_location', sa.String(length=500), nullable=True),
    sa.Column('order_status', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['trip_id'], ['trip.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('leaftrade_order_id')
    )
    op.create_table('trip_drivers',
    sa.Column('trip_id', sa.Integer(), nullable=False),
    sa.Column('driver_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['driver_id'], ['driver.id'], ),
    sa.ForeignKeyConstraint(['trip_id'], ['trip.id'], ),
    sa.PrimaryKeyConstraint('trip_id', 'driver_id')
    )
