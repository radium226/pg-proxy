from radium226.pg import PostgreSQL
from contextlib import closing
from time import sleep

import pytest


@pytest.mark.parametrize("ssl", [True, False])
def test_postgresql(ssl) -> None:
    with PostgreSQL(ssl=ssl) as pg:
        with pg.connect() as connection:
            with closing(connection.cursor()) as cursor:
                cursor.execute("SELECT 1")
                assert cursor.fetchone() == (1,)