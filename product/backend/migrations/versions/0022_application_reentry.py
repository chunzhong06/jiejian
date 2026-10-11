# 同一源码目录允许显式建立独立项目；保留原项目、授权和历史关联。
from alembic import op

revision = '0022_application_reentry'
down_revision = '0021_candidate_visibility'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('application_understanding') as batch:
        batch.drop_constraint('uq_application_understanding_source_root', type_='unique')
        batch.create_index('ix_application_understanding_source_root', ['source_root'])


def downgrade():
    raise RuntimeError('STATE_PRECONDITION: independent application history requires an explicit backup')
