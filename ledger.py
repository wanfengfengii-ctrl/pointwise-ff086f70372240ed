from contextlib import contextmanager
import sqlite3


MAX_RECORD_ID = (1 << 63) - 1


def record_id(value: int) -> int:
    if type(value) is not int or not 0 < value <= MAX_RECORD_ID:
        raise ValueError('expected a positive SQLite record number')
    return value


def open_database(path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


@contextmanager
def write_transaction(connection: sqlite3.Connection):
    connection.execute('BEGIN IMMEDIATE')
    try:
        yield
        connection.commit()
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
