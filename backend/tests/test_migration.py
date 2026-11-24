from sqlalchemy import inspect, text

from app.db.session import _add_missing_columns, engine


def test_missing_nullable_columns_are_added_without_data_loss():
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE "transcripts"'))
        conn.execute(text('CREATE TABLE "transcripts" (id VARCHAR(32) PRIMARY KEY, meeting_id VARCHAR(32), language VARCHAR(10), model VARCHAR(200), segments JSON, full_text TEXT, created_at DATETIME)'))
        conn.execute(text("INSERT INTO transcripts (id, meeting_id, language, model, segments, full_text) VALUES ('t1', 'm1', 'ko', 'x', '[]', '보존')"))
    _add_missing_columns()
    cols = {c["name"] for c in inspect(engine).get_columns("transcripts")}
    assert "audio_file_id" in cols
    with engine.connect() as conn:
        assert conn.execute(text("SELECT full_text FROM transcripts WHERE id='t1'")).scalar() == "보존"
