"""Index cho truy vấn feed /library/changes: WHERE pinned, status ORDER BY last_seen, id."""
from sqlalchemy import inspect

from app.db import engine


def test_shared_tones_co_index_feed():
    names = {ix["name"]: ix["column_names"] for ix in inspect(engine).get_indexes("shared_tones")}
    assert names.get("ix_shared_tones_feed") == ["pinned", "status", "last_seen", "id"]
