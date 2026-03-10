"""add fix_pr_merged processing phase

Revision ID: b2a50fb4be80
Revises: 6ea9418ff8c8
Create Date: 2026-03-09 13:38:26.935790

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2a50fb4be80'
down_revision = '6ea9418ff8c8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("check_processing_phase", "drift_events", type_="check")
    op.create_check_constraint(
        "check_processing_phase",
        "drift_events",
        "processing_phase IN ('queued', 'scouting', 'analyzing', 'generating', 'verifying', 'completed', 'failed', 'fix_pr_raised', 'fix_pr_merged')",
    )


def downgrade() -> None:
    op.drop_constraint("check_processing_phase", "drift_events", type_="check")
    op.create_check_constraint(
        "check_processing_phase",
        "drift_events",
        "processing_phase IN ('queued', 'scouting', 'analyzing', 'generating', 'verifying', 'completed', 'failed', 'fix_pr_raised')",
    )

