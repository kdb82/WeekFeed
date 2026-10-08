import pytest

from weekfeed.store.db import connect, migrate


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    migrate(c)
    yield c
    c.close()
