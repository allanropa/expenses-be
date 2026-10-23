"""Allow users to reuse names for accounts, cards, and categories."""

from alembic import op
import sqlalchemy as sa


revision = "0009_duplicate_names"
down_revision = "0008_query_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        metadata = sa.MetaData()
        category = sa.Table(
            "categories",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("is_archived", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        account = sa.Table(
            "accounts",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("account_type", sa.String(16), nullable=False),
            sa.Column("currency", sa.String(3), nullable=False),
            sa.Column("opening_balance", sa.Numeric(20, 4), nullable=False),
            sa.Column("opening_balance_date", sa.Date(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_archived", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        card = sa.Table(
            "credit_cards",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("issuing_bank", sa.String(120), nullable=True),
            sa.Column("statement_closing_day", sa.Integer(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_archived", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        for table in (category, account, card):
            with op.batch_alter_table(table.name, copy_from=table, recreate="always"):
                pass
        return

    op.drop_constraint("categories_user_id_name_key", "categories", type_="unique")
    op.drop_constraint("accounts_user_id_name_key", "accounts", type_="unique")
    op.drop_constraint("credit_cards_user_id_name_key", "credit_cards", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("categories_user_id_name_key", "categories", ["user_id", "name"])
    op.create_unique_constraint("accounts_user_id_name_key", "accounts", ["user_id", "name"])
    op.create_unique_constraint("credit_cards_user_id_name_key", "credit_cards", ["user_id", "name"])
