"""add location mapping to trip order

Revision ID: f9a3f0238be9
Revises: c1f583dd0272
Create Date: 2026-08-02 08:38:54.393184

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f9a3f0238be9'
down_revision = 'c1f583dd0272'
branch_labels = None
depends_on = None


def upgrade():
    # NOTE: autogenerate wanted to drop the idx_* performance indexes from revision
    # a1b2c3d4e5f6 because they are not declared on the models. They are intentional -
    # those drops have been removed here.

    with op.batch_alter_table('trip_order', schema=None) as batch_op:
        batch_op.add_column(sa.Column('location_mapping_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_trip_order_location_mapping', 'location_mapping', ['location_mapping_id'], ['id']
        )


def downgrade():
    with op.batch_alter_table('trip_order', schema=None) as batch_op:
        batch_op.drop_constraint('fk_trip_order_location_mapping', type_='foreignkey')
        batch_op.drop_column('location_mapping_id')
