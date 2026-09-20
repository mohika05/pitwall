"""Durable replay checkpoints, ingestion jobs, scenarios and model versions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "2b7a901c4d11"
down_revision = "8a464e5bb5c8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workspace_records",
        sa.Column("kind", sa.String(32), primary_key=True),
        sa.Column("key", sa.String(160), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("workspace_records")
