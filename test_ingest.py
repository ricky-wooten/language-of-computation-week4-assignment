"""Tests that ingest.py does what rules.md says.

rules.md is the only source of truth. Every test below names the rule or the
examples-table row it comes from.

How the tests stay away from the real files
-------------------------------------------
ingest.py keeps books.db and ingestion-log.json beside itself. Each test makes
a fresh temporary folder and points ingest.py at a test.db and a temporary log
inside it. When the test ends, passed or failed, the whole folder is deleted.
Every test also checks that the real books.db and ingestion-log.json in the
project folder were not created, changed or deleted.

Run with:  .venv/bin/python -m pytest
"""

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile

import pytest

import ingest

HERE = os.path.dirname(os.path.abspath(__file__))
BOOKS_CSV = os.path.join(HERE, "books.csv")
BATCH2_CSV = os.path.join(HERE, "books-batch2.csv")
REAL_DB = os.path.join(HERE, "books.db")
REAL_LOG = os.path.join(HERE, "ingestion-log.json")

# The 23 headers come from the supplied books.csv (rules.md, "Files and the report").
with open(BOOKS_CSV, newline="", encoding="utf-8-sig") as _handle:
    HEADER = next(csv.reader(_handle))

# Action sentences, word for word from rules.md ("Files and the report").
ISBN_SENTENCE = "Find the correct ISBN, correct the row, and load the file again."
CONFLICT_SENTENCE = "Check which value or book is correct."
ALL_SENTENCES = [
    ISBN_SENTENCE,
    CONFLICT_SENTENCE,
    "Supply an identifying title and author, then load the file again.",
    "Correct the file error and rerun the files.",
]


# ----- Setup and teardown ----------------------------------------------------

def _fingerprint(path):
    """None if the file is missing, otherwise a hash of its bytes."""
    if not os.path.exists(path):
        return None
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


class Workspace:
    """A temporary folder holding test.db, a temporary log and test CSV files."""

    def __init__(self, folder):
        self.folder = folder
        self.db = os.path.join(folder, "test.db")
        self.log = os.path.join(folder, "test-ingestion-log.json")

    def write_csv(self, name, rows):
        """Write a CSV with all 23 headers. Unlisted fields get ordinary values."""
        path = os.path.join(self.folder, name)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADER)
            writer.writeheader()
            for row in rows:
                writer.writerow(full_row(**row))
        return path

    def run(self, csv_path):
        """Run ingest.py on one file and return the log entry it added."""
        ingest.main([csv_path])
        return self.log_entries()[-1]

    def log_entries(self):
        with open(self.log, encoding="utf-8") as handle:
            return json.load(handle)

    def books(self):
        """Every row in test.db, as dictionaries, in a fixed order."""
        connection = sqlite3.connect(self.db)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute("SELECT * FROM books ORDER BY id").fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()


@pytest.fixture
def workspace(monkeypatch):
    real_before = (_fingerprint(REAL_DB), _fingerprint(REAL_LOG))
    folder = tempfile.mkdtemp(prefix="ingest-test-")
    try:
        space = Workspace(folder)
        monkeypatch.setattr(ingest, "HERE", folder)
        monkeypatch.setattr(ingest, "DB_PATH", space.db)
        monkeypatch.setattr(ingest, "LOG_PATH", space.log)
        yield space
    finally:
        # Teardown runs whether the test passed or failed.
        shutil.rmtree(folder, ignore_errors=True)
        assert not os.path.exists(folder), "temporary test files were not removed"
        assert (_fingerprint(REAL_DB), _fingerprint(REAL_LOG)) == real_before, \
            "a test touched the real books.db or ingestion-log.json"


_next_id = [1000]


def full_row(isbn="", isbn13="", title=None, authors=None, book_id=None, **other):
    """A row with a real nonblank title and author and a supplier ID
    (rules.md, "Examples for the tests")."""
    _next_id[0] += 1
    number = _next_id[0]
    row = {column: "" for column in HEADER}
    row.update({
        "book_id": str(number) if book_id is None else book_id,
        "goodreads_book_id": str(number),
        "best_book_id": str(number),
        "work_id": str(number),
        "books_count": "1",
        "isbn": isbn,
        "isbn13": isbn13,
        "authors": "Test Author {}".format(number) if authors is None else authors,
        "original_publication_year": "2000.0",
        "original_title": "Test Book {}".format(number) if title is None else title,
        "title": "Test Book {}".format(number) if title is None else title,
        "language_code": "eng",
        "average_rating": "4.0",
        "ratings_count": "10",
        "work_ratings_count": "10",
        "work_text_reviews_count": "1",
        "ratings_1": "0", "ratings_2": "0", "ratings_3": "2",
        "ratings_4": "4", "ratings_5": "4",
        "image_url": "https://example.com/image.jpg",
        "small_image_url": "https://example.com/small.jpg",
    })
    row.update(other)
    return row


# ----- Reading the log entry ---------------------------------------------------
# rules.md says what the log must show but not the field names. These helpers
# read the names ingest.py writes now, in one place, so they are easy to adjust.

def outcomes(entry):
    return {name: entry[name] for name in ("loaded", "updated", "skipped", "rejected")}


def repair_total(entry):
    return sum(entry["repairs_by_type"].values())


def warning_total(entry):
    return entry["warning_count"]


def entry_text(entry):
    return json.dumps(entry, ensure_ascii=False)


def count_records(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return sum(1 for row in csv.reader(handle) if row) - 1


# ----- One test per row of the examples table -----------------------------------
# rules.md: repair and warning counts must match each example exactly.

LOADED_EXAMPLES = [
    # (isbn, isbn13, stored isbn, stored isbn13, repairs, warnings)
    pytest.param("0439139600", "9780439139601", "0439139600", "9780439139601", 0, 0,
                 id="01-both-agree"),
    pytest.param("043965548X", "", "043965548X", "9780439655484", 1, 0,
                 id="02-calculate-missing-isbn13"),
    pytest.param("031200009x", "9780312000097", "031200009X", "9780312000097", 1, 0,
                 id="03-lowercase-x"),
    pytest.param("0-450-19827-8", "9780450198274", "0450198278", "9780450198274", 1, 0,
                 id="04-hyphens"),
    pytest.param(" 162 001 4750 ", "9781620014752", "1620014750", "9781620014752", 1, 0,
                 id="05-spaces"),
    pytest.param("439023483", "", "0439023483", "9780439023481", 2, 0,
                 id="06-pad-and-calculate"),
    pytest.param("439554934", "9.78043955493e+12", "0439554934", "9780439554930", 2, 0,
                 id="07-pad-and-scientific"),
    pytest.param("439023483", "9.78043902348e+12", "0439023483", "9780439023481", 2, 0,
                 id="08-pad-and-scientific"),
    pytest.param("", "9.78043902348e+12", None, None, 0, 1,
                 id="09-scientific-without-isbn"),
    pytest.param("", "76783609419.0", None, None, 0, 1,
                 id="10-other-code"),
    pytest.param("", "9780439139601.0", None, None, 0, 1,
                 id="11-decimal-not-stripped"),
    pytest.param("9781982147600", "", "1982147601", "9781982147600", 2, 0,
                 id="17-move-to-isbn13"),
    pytest.param("", "9798351220413", None, "9798351220413", 0, 0,
                 id="18-979-no-isbn10"),
    pytest.param("0439139600", "12345", "0439139600", None, 0, 1,
                 id="20-other-code-discarded"),
]


@pytest.mark.parametrize(
    "isbn, isbn13, stored_isbn, stored_isbn13, repairs, warnings", LOADED_EXAMPLES)
def test_example_row_is_loaded(workspace, isbn, isbn13, stored_isbn, stored_isbn13,
                               repairs, warnings):
    path = workspace.write_csv("example.csv", [{"isbn": isbn, "isbn13": isbn13}])

    entry = workspace.run(path)

    assert outcomes(entry) == {"loaded": 1, "updated": 0, "skipped": 0, "rejected": 0}
    books = workspace.books()
    assert len(books) == 1
    # Empty ISBNs are stored as null (rules.md, "Files and the report").
    assert books[0]["isbn"] == stored_isbn
    assert books[0]["isbn13"] == stored_isbn13
    assert repair_total(entry) == repairs
    assert warning_total(entry) == warnings


REJECTED_EXAMPLES = [
    # (isbn, isbn13, action sentence)
    pytest.param("04390A3483", "", ISBN_SENTENCE, id="12-illegal-character"),
    pytest.param("15287463097", "", ISBN_SENTENCE, id="13-overlong"),
    pytest.param("1854433017", "", ISBN_SENTENCE, id="14-bad-checksum"),
    pytest.param("1555550126", "9781555550134", CONFLICT_SENTENCE,
                 id="16-conflicting-isbns"),
    pytest.param("0439139600", "9780061120085", ISBN_SENTENCE,
                 id="19-bad-isbn13-checksum"),
    pytest.param("9780439139601", "9.7804391396e+12", CONFLICT_SENTENCE,
                 id="21-move-conflict"),
]


@pytest.mark.parametrize("isbn, isbn13, sentence", REJECTED_EXAMPLES)
def test_example_row_is_rejected(workspace, isbn, isbn13, sentence):
    path = workspace.write_csv("example.csv", [{"isbn": isbn, "isbn13": isbn13}])

    entry = workspace.run(path)

    assert outcomes(entry) == {"loaded": 0, "updated": 0, "skipped": 0, "rejected": 1}
    assert workspace.books() == []
    assert repair_total(entry) == 0
    assert warning_total(entry) == 0
    text = entry_text(entry)
    assert sentence in text
    for other in ALL_SENTENCES:
        if other != sentence:
            assert other not in text


def test_example_15_blank_and_blank_is_rejected_even_for_a_known_supplier_id(workspace):
    known = {"isbn": "0439139600", "isbn13": "9780439139601", "book_id": "501",
             "title": "Known Book", "authors": "Known Author"}
    first = workspace.write_csv("known.csv", [known])
    workspace.run(first)
    before = workspace.books()

    second = workspace.write_csv("blank.csv", [dict(known, isbn="", isbn13="")])
    entry = workspace.run(second)

    assert outcomes(entry) == {"loaded": 0, "updated": 0, "skipped": 0, "rejected": 1}
    assert workspace.books() == before
    assert repair_total(entry) == 0
    assert warning_total(entry) == 0
    text = entry_text(entry)
    assert ISBN_SENTENCE in text
    for other in ALL_SENTENCES:
        if other != ISBN_SENTENCE:
            assert other not in text


def test_example_22_same_row_again_is_skipped(workspace):
    row = full_row(isbn="0439139600", isbn13="9780439139601")
    path = workspace.write_csv("example.csv", [row, row])

    entry = workspace.run(path)

    assert outcomes(entry) == {"loaded": 1, "updated": 0, "skipped": 1, "rejected": 0}
    assert len(workspace.books()) == 1
    assert repair_total(entry) == 0
    assert warning_total(entry) == 0


# ----- Whole-file tests ---------------------------------------------------------

SUPPLIED_FILES = [pytest.param(BOOKS_CSV, id="books.csv"),
                  pytest.param(BATCH2_CSV, id="books-batch2.csv")]


@pytest.mark.parametrize("csv_path", SUPPLIED_FILES)
def test_running_the_same_file_twice_creates_no_duplicates(workspace, csv_path):
    # rules.md, "When a book comes again": an identical accepted row is
    # skipped and does not add a book.
    workspace.run(csv_path)
    after_first = workspace.books()

    second = workspace.run(csv_path)

    assert workspace.books() == after_first
    assert second["loaded"] == 0
    assert second["updated"] == 0


def test_every_run_adds_a_log_entry_without_overwriting_earlier_ones(workspace):
    # rules.md: "Add each run to ingestion-log.json without losing old entries."
    workspace.run(BATCH2_CSV)
    first = workspace.log_entries()
    assert len(first) == 1

    workspace.run(BATCH2_CSV)
    second = workspace.log_entries()
    assert len(second) == 2
    assert second[0] == first[0]

    workspace.run(BOOKS_CSV)
    third = workspace.log_entries()
    assert len(third) == 3
    assert third[:2] == second


@pytest.mark.parametrize("csv_path", SUPPLIED_FILES)
def test_outcomes_add_up_to_rows_read(workspace, csv_path):
    # rules.md: "The four outcomes must add up to rows read."
    entry = workspace.run(csv_path)

    assert entry["rows_read"] == count_records(csv_path)
    assert sum(outcomes(entry).values()) == entry["rows_read"]


@pytest.mark.parametrize("csv_path", SUPPLIED_FILES)
def test_same_file_on_an_empty_database_gives_the_same_database(monkeypatch, csv_path):
    # rules.md: "I want the same files to get the same decisions every time."
    results = []
    for _ in range(2):
        real_before = (_fingerprint(REAL_DB), _fingerprint(REAL_LOG))
        folder = tempfile.mkdtemp(prefix="ingest-test-")
        try:
            space = Workspace(folder)
            monkeypatch.setattr(ingest, "HERE", folder)
            monkeypatch.setattr(ingest, "DB_PATH", space.db)
            monkeypatch.setattr(ingest, "LOG_PATH", space.log)
            space.run(csv_path)
            results.append(space.books())
        finally:
            shutil.rmtree(folder, ignore_errors=True)
            assert not os.path.exists(folder)
            assert (_fingerprint(REAL_DB), _fingerprint(REAL_LOG)) == real_before

    assert results[0] == results[1]
