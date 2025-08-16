import alembic.config

alembic_args = [
    '--raiseerr',
    '-c', 'middleware/alembic.ini',
    'revision',
    '--autogenerate',
    '-m', 'add name and location to user',
]
alembic.config.main(argv=alembic_args)
