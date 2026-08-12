"""为 LLM Candidate 增加可选、严格校验的生成 provenance。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_stage5_llm_candidate_metadata"
down_revision: str | None = "0004_stage5_contracts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contract_candidates",
        sa.Column("llm_metadata_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contract_candidates", "llm_metadata_json")
