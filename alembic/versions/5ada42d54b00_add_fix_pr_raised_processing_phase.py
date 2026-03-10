"""Add fix_pr_raised processing phase

Revision ID: 5ada42d54b00
Revises: 8a4b15ccb884
Create Date: 2026-03-09 11:38:04.322510

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5ada42d54b00'
down_revision = '8a4b15ccb884'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("check_processing_phase", "drift_events", type_="check")
    op.create_check_constraint(
        "check_processing_phase",
        "drift_events",
        "processing_phase IN ('queued', 'scouting', 'analyzing', 'generating', 'verifying', 'completed', 'failed', 'fix_pr_raised')",
    )


def downgrade() -> None:
    op.drop_constraint("check_processing_phase", "drift_events", type_="check")
    op.create_check_constraint(
        "check_processing_phase",
        "drift_events",
        "processing_phase IN ('queued', 'scouting', 'analyzing', 'generating', 'verifying', 'completed', 'failed')",
    )
