from radium226.pg import PostgreSQL
from contextlib import closing


def test_postgresql() -> None:
    with PostgreSQL() as pg, pg.connect() as connection:
        with closing(connection.cursor()) as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
            