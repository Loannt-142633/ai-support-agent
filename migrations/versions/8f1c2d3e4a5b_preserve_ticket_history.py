"""Preserve ticket history and normalize PostgreSQL enums."""

from collections.abc import Sequence

from alembic import op

revision: str = "8f1c2d3e4a5b"
down_revision: str | None = "725477bbd989"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_enum(
    type_name: str, values: tuple[str, ...], transform: str = "lower"
) -> None:
    old_type = f"{type_name}_old"
    value_list = ", ".join(f"'{value}'" for value in values)
    op.execute(f"ALTER TYPE {type_name} RENAME TO {old_type}")
    op.execute(f"CREATE TYPE {type_name} AS ENUM ({value_list})")
    op.execute(
        "ALTER TABLE tickets "
        f"ALTER COLUMN {type_name.removeprefix('ticket')} "
        f"TYPE {type_name} USING {transform}"
        f"({type_name.removeprefix('ticket')}::text)::%s" % type_name
    )
    op.execute(f"DROP TYPE {old_type}")


def upgrade() -> None:
    """Normalize existing enum storage and preserve tickets after user deletion."""

    _replace_enum("ticketcategory", ("general", "billing", "technical"))
    _replace_enum("ticketpriority", ("low", "medium", "high", "urgent"))
    _replace_enum("ticketstatus", ("open", "in_progress", "resolved", "closed"))
    op.execute("ALTER TABLE tickets ALTER COLUMN user_id DROP NOT NULL")
    op.drop_constraint("tickets_user_id_fkey", "tickets", type_="foreignkey")
    op.create_foreign_key(
        "tickets_user_id_fkey",
        "tickets",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Restore legacy enum labels and cascading user deletion."""

    op.drop_constraint("tickets_user_id_fkey", "tickets", type_="foreignkey")
    op.create_foreign_key(
        "tickets_user_id_fkey",
        "tickets",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute("DELETE FROM tickets WHERE user_id IS NULL")
    op.execute("ALTER TABLE tickets ALTER COLUMN user_id SET NOT NULL")
    _replace_enum(
        "ticketcategory", ("GENERAL", "BILLING", "TECHNICAL"), transform="upper"
    )
    _replace_enum(
        "ticketpriority", ("LOW", "MEDIUM", "HIGH", "URGENT"), transform="upper"
    )
    _replace_enum(
        "ticketstatus",
        ("OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"),
        transform="upper",
    )
