from logging.config import fileConfig

from alembic import context

from app.config.settings import settings
from app.core.database import Base, _make_engine

# Import all models so Alembic can detect them for autogenerate.
import app.models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # The app's engine, so a migration runs with the same SQLite settings as the
    # app: foreign keys enforced, WAL, a busy timeout (core/database.py)
    connectable = _make_engine(settings.database_url)
    with connectable.connect() as connection:
        # render_as_batch: SQLite cannot ALTER a column, drop a constraint or add
        # a column with a foreign key in place, so a future migration that does
        # any of those is run as a table rebuild (batch mode).
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
