"""add line total and manifest send audit

Revision ID: 6afe8891b3d3
Revises: f9a3f0238be9
Create Date: 2026-08-02 16:53:10.519423

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6afe8891b3d3'
down_revision = 'f9a3f0238be9'
branch_labels = None
depends_on = None


def upgrade():
    # NOTE: autogenerate wanted to drop the idx_* performance indexes from revision
    # a1b2c3d4e5f6 because they are not declared on the models. They are intentional -
    # those drops have been removed here.

    with op.batch_alter_table('trip_order', schema=None) as batch_op:
        batch_op.add_column(sa.Column('manifest_sent_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('manifest_sent_to', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('manifest_send_count', sa.Integer(), nullable=True))

    with op.batch_alter_table('trip_order_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('line_total', sa.Numeric(precision=12, scale=2), nullable=True))

    # Existing rows predate the audit trail; treat them as never sent rather than null.
    op.execute('UPDATE trip_order SET manifest_send_count = 0 WHERE manifest_send_count IS NULL')


def downgrade():
    with op.batch_alter_table('trip_order_item', schema=None) as batch_op:
        batch_op.drop_column('line_total')

    with op.batch_alter_table('trip_order', schema=None) as batch_op:
        batch_op.drop_column('manifest_send_count')
        batch_op.drop_column('manifest_sent_to')
        batch_op.drop_column('manifest_sent_at')
