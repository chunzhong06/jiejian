from alembic import op
import sqlalchemy as sa

revision = 'workspace_0004'
down_revision = 'workspace_0003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('test_identities',sa.Column('authentication_json',sa.Text(),nullable=True))
    op.add_column('test_identities',sa.Column('verification_json',sa.Text(),nullable=True))
    op.create_table('operation_flow_revisions',
        sa.Column('flow_id',sa.String(36),primary_key=True),sa.Column('revision',sa.Integer(),primary_key=True),
        sa.Column('project_id',sa.String(64),sa.ForeignKey('projects.project_id',ondelete='RESTRICT'),nullable=False),
        sa.Column('payload_json',sa.Text(),nullable=False),sa.Column('created_at_us',sa.BigInteger(),nullable=False),
        sa.Column('adopted_at_us',sa.BigInteger(),nullable=True))
    for table in ('action_execution_bindings','action_resource_bindings','action_recovery_bindings'):
        with op.batch_alter_table(table,recreate='always') as batch:
            batch.alter_column('source_recording_id',existing_type=sa.String(36),nullable=True)
            batch.alter_column('source_draft_revision',existing_type=sa.Integer(),nullable=True)
            batch.alter_column('source_draft_sha256',existing_type=sa.String(64),nullable=True)
            batch.add_column(sa.Column('operation_flow_id',sa.String(36),nullable=True))
            batch.add_column(sa.Column('operation_flow_revision',sa.Integer(),nullable=True))
            batch.create_foreign_key('fk_'+table+'_operation_flow_id_operation_flow_revisions','operation_flow_revisions',['operation_flow_id','operation_flow_revision'],['flow_id','revision'],ondelete='RESTRICT')
            batch.create_check_constraint(op.f('ck_'+table+'_material_origin_matrix'),'(source_recording_id IS NOT NULL AND source_draft_revision IS NOT NULL AND source_draft_sha256 IS NOT NULL AND operation_flow_id IS NULL AND operation_flow_revision IS NULL) OR (source_recording_id IS NULL AND source_draft_revision IS NULL AND source_draft_sha256 IS NULL AND operation_flow_id IS NOT NULL AND operation_flow_revision IS NOT NULL)')
    op.get_bind().exec_driver_sql("UPDATE workspace_schema SET schema_digest = 'ad50b1417e938512e9031be570d6a014de106e4742e1f4768e613aab100718f9' WHERE singleton = 1")


def downgrade():
    raise RuntimeError('认证与操作流程修订不提供自动降级')
