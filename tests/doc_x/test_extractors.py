# tests/doc_x/test_extractors.py
"""
Unit tests for document text extractors.
"""
import pytest

from apps.doc_x.extract import extract_csv, extract_text, extract_txt


def test_extract_txt(temp_txt_file):
    """Test text file extraction."""
    text = extract_txt(temp_txt_file)

    assert "test text file" in text.lower()
    assert "multiple lines" in text.lower()
    assert len(text) > 0


def test_extract_csv(temp_csv_file):
    """Test CSV file extraction."""
    text = extract_csv(temp_csv_file)

    assert "Name" in text
    assert "Age" in text
    assert "John" in text
    assert "Jane" in text
    assert "CSV File with" in text


def test_extract_text_universal(temp_txt_file):
    """Test universal extract_text function."""
    text = extract_text(temp_txt_file, file_type="txt")

    assert len(text) > 0
    assert "test text file" in text.lower()


def test_extract_text_auto_detect(temp_txt_file):
    """Test that extract_text auto-detects file type."""
    text = extract_text(temp_txt_file)

    assert len(text) > 0


def test_extract_csv_max_rows(temp_csv_file):
    """Test CSV extraction with max_rows limit."""
    text = extract_csv(temp_csv_file, max_rows=2)

    # Should still contain headers and summary
    assert "Name" in text
    assert "columns" in text.lower()


def test_extract_unsupported_file_type(temp_txt_file):
    """Test that unsupported file types raise error."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        extract_text(temp_txt_file, file_type="xyz")


def test_extract_empty_csv():
    """Test extraction of empty CSV."""
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("Header1,Header2\n")  # Only headers
        temp_path = f.name

    try:
        text = extract_csv(temp_path)
        assert "Empty CSV" in text or "0 rows" in text.lower()
    finally:
        os.remove(temp_path)


def test_extract_txt_encoding_fallback():
    """Test that TXT extractor handles encoding issues."""
    import os
    import tempfile

    # Create file with latin-1 encoding
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=False) as f:
        f.write("Café résumé".encode("latin-1"))
        temp_path = f.name

    try:
        text = extract_txt(temp_path)
        assert len(text) > 0
    finally:
        os.remove(temp_path)
