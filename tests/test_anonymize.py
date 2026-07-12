import pandas as pd
import pytest

from aeo_research.anonymize import (
    ColumnSpec,
    Datasheet,
    ReleaseError,
    pseudonymize,
    release_dataset,
)

SHEET = Datasheet(title="Test data", dataset_slug="test-data", study="test-study")


def ok_frame():
    return pd.DataFrame(
        {
            "video_id": ["r76p4i55-Us", "abcdefghijk"],
            "platform": ["openai", "gemini"],
            "cited": [1, 0],
        }
    )


def ok_columns():
    return [
        ColumnSpec("video_id", "YouTube video id"),
        ColumnSpec("platform", "AI platform"),
        ColumnSpec("cited", "1 = cited inline"),
    ]


def test_release_writes_csv_and_datasheet(tmp_path):
    paths = release_dataset(ok_frame(), ok_columns(), tmp_path, SHEET)
    assert paths["csv"].exists()
    text = paths["datasheet"].read_text()
    assert "citations evaluated in this study" in text
    assert "CC BY 4.0" in text
    out = pd.read_csv(paths["csv"])
    assert list(out.columns) == ["video_id", "platform", "cited"]


@pytest.mark.parametrize(
    "bad_name",
    ["execution_id", "executionId", "propertyId", "prompt_text", "fanout_query", "user_email"],
)
def test_forbidden_column_names_raise(tmp_path, bad_name):
    df = ok_frame()
    df[bad_name] = "x"
    cols = ok_columns() + [ColumnSpec(bad_name, "sneaky")]
    with pytest.raises(ReleaseError, match="forbidden"):
        release_dataset(df, cols, tmp_path, SHEET)


def test_cuid_values_raise(tmp_path):
    df = ok_frame()
    df["video_id"] = ["cm4xk2p9d0000abcdefghijkl", "abcdefghijk"]
    with pytest.raises(ReleaseError, match="cuid"):
        release_dataset(df, ok_columns(), tmp_path, SHEET)


def test_long_free_text_raises(tmp_path):
    df = ok_frame()
    df["platform"] = ["x" * 500, "gemini"]
    with pytest.raises(ReleaseError, match="free text"):
        release_dataset(df, ok_columns(), tmp_path, SHEET)


def test_long_text_allowed_when_public_fact(tmp_path):
    df = ok_frame()
    df["platform"] = ["x" * 500, "gemini"]
    cols = [
        ColumnSpec("video_id", "id"),
        ColumnSpec("platform", "public", public_fact=True),
        ColumnSpec("cited", "outcome"),
    ]
    paths = release_dataset(df, cols, tmp_path, SHEET)
    assert paths["csv"].exists()


def test_missing_column_raises(tmp_path):
    cols = ok_columns() + [ColumnSpec("nope", "missing")]
    with pytest.raises(ReleaseError, match="missing"):
        release_dataset(ok_frame(), cols, tmp_path, SHEET)


def test_nothing_written_on_failure(tmp_path):
    df = ok_frame()
    df["video_id"] = ["cm4xk2p9d0000abcdefghijkl", "abcdefghijk"]
    with pytest.raises(ReleaseError):
        release_dataset(df, ok_columns(), tmp_path, SHEET)
    assert list(tmp_path.iterdir()) == []


def test_pseudonymize_sequential_and_stable():
    s = pd.Series(["a", "b", "a", None, "c"])
    out = pseudonymize(s, "exec")
    assert out.tolist()[:3] == ["exec_0001", "exec_0002", "exec_0001"]
    assert pd.isna(out.iloc[3])
    assert out.iloc[4] == "exec_0003"
