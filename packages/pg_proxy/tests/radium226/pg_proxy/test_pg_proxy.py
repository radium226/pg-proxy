from pytest import fixture

from radium226.pg import PostgreSQL
from radium226.pg_proxy import PostgreSQLProxy

from contextlib import closing
import psycopg2


@fixture
def pg() -> PostgreSQL:
    with PostgreSQL() as pg:
        yield pg


@fixture
def pg_proxy(pg: PostgreSQL) -> PostgreSQLProxy:
    with PostgreSQLProxy(
        remote_host=pg.host,
        remote_port=pg.port,
    ) as pg_proxy:
        yield pg_proxy


def test_pg_proxy(pg_proxy: PostgreSQLProxy) -> None:
    print(f"pg_proxy={pg_proxy}")
    host = pg_proxy.host
    print(f"host={host}")

    port = pg_proxy.port
    print(f"port={port}")

    with closing(psycopg2.connect(
        dbname="postgres",
        user="postgres",
        host=host,
        port=port,
        sslmode="require",
    )) as connection, closing(connection.cursor()) as cursor: 
        cursor.execute("SELECT * FROM information_schema.sql_features LIMIT 10")
        for index, result in enumerate(cursor, start=1):
            print(result)
            pass
            # assert result == (index,)
