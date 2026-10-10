# 候选归档只改变展示状态，保留全部修订和批准来源。
from alembic import op
import sqlalchemy as sa

revision = '0021_candidate_visibility'
down_revision = '0020_environment_progress'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('rule_candidate_visibility',
        sa.Column('candidate_id', sa.String(36), primary_key=True),
        sa.Column('archived', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('updated_at_us', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['candidate_id'], ['rule_candidates.candidate_id'], ondelete='RESTRICT'),
        sa.CheckConstraint('version >= 1', name='version_positive'))


def downgrade():
    raise RuntimeError('STATE_PRECONDITION: candidate archive history requires an explicit backup')
