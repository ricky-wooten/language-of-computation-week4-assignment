#!/usr/bin/env python3
"""Load a books CSV file into books.db, following rules.md.

How to run it:
    python3 ingest.py books.csv

This script uses only Python's built-in tools. It does not use AI or the
internet, so the same file always gives the same result. books.db and
ingestion-log.json are kept in the same folder as this script.
"""

import csv
import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "books.db")
LOG_PATH = os.path.join(HERE, "ingestion-log.json")

# Answer 1: books.db stores these 23 columns.
COLUMNS = [
    "book_id", "goodreads_book_id", "best_book_id", "work_id", "books_count",
    "isbn", "isbn13", "authors", "original_publication_year", "original_title",
    "title", "language_code", "average_rating", "ratings_count",
    "work_ratings_count", "work_text_reviews_count", "ratings_1", "ratings_2",
    "ratings_3", "ratings_4", "ratings_5", "image_url", "small_image_url",
]

# Section 2 and answer 6: compared after normalizing.
PLACEHOLDERS = {"unknown", "untitled", "untitled manuscript"}

# Answer 11: one fixed sentence for each kind of rejection.
FIND_ISBN = "Find the correct ISBN, correct the row, and load the file again."
CHECK_CONFLICT = "Check which value or book is correct."

# The kinds of repair counted in the report.
REPAIR_ZEROS = "Added leading zeros"
REPAIR_FORMAT = "Cleaned hyphens, spaces, or lowercase x"
REPAIR_MOVED = "Moved ISBN-13 from isbn to isbn13"
REPAIR_REBUILT = "Rebuilt rounded isbn13 from isbn"
REPAIR_CALCULATED = "Calculated a missing ISBN value"

# Verdicts from section 4 and answer 12.
VERDICT_ALL_LOADED = "Everything loaded"
VERDICT_ATTENTION = "Some rows need attention"
VERDICT_FAILED = "The run failed"

SCIENTIFIC_NUMBER = re.compile(r"^\d+(\.\d+)?[eE]\+?\d{1,3}$")
DECIMAL_NUMBER = re.compile(r"^\d+\.\d+$")
ROUNDING = Context(prec=12, rounding=ROUND_HALF_EVEN)


class UnreadableFile(Exception):
    """Answers 10 and 14: the file cannot be read safely, so the run fails."""


# ----- ISBN math -----------------------------------------------------------

def is_valid_isbn10(value):
    if not re.fullmatch(r"\d{9}[\dX]", value):
        return False
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(value))
    return total % 11 == 0


def is_valid_isbn13(value):
    if not re.fullmatch(r"(978|979)\d{10}", value):
        return False
    total = sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(value))
    return total % 10 == 0


def isbn10_to_isbn13(isbn10):
    start = "978" + isbn10[:9]
    total = sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(start))
    return start + str((10 - total % 10) % 10)


def isbn13_to_isbn10(isbn13):
    """Only an ISBN-13 starting with 978 has an ISBN-10 form."""
    if not isbn13.startswith("978"):
        return ""
    start = isbn13[3:12]
    total = sum((10 - i) * int(c) for i, c in enumerate(start))
    check = (11 - total % 11) % 11
    return start + ("X" if check == 10 else str(check))


def matches_stored_number(isbn13, stored_number):
    """True if this ISBN-13 rounds to the stored number at 12 significant digits."""
    if int(isbn13) == stored_number:
        return True
    return int(ROUNDING.create_decimal(Decimal(isbn13))) == stored_number


# ----- Checking one row's ISBN values ----------------------------------------

def read_isbn(raw):
    """Clean and test the isbn column. Returns a dictionary describing it."""
    cleaned = re.sub(r"[\s-]", "", raw).replace("x", "X")
    repairs = [REPAIR_FORMAT] if cleaned != raw else []

    if cleaned == "":
        return {"kind": "blank", "repairs": []}
    # An illegal character takes priority over "too short" (answer 9).
    if not re.fullmatch(r"\d*X?", cleaned):
        return {"kind": "problem",
                "reason": "isbn contains a character that is not allowed"}
    if len(cleaned) < 10:
        padded = cleaned.zfill(10)
        if is_valid_isbn10(padded):
            return {"kind": "isbn10", "value": padded,
                    "repairs": repairs + [REPAIR_ZEROS]}
        return {"kind": "problem",
                "reason": "isbn is too short and fails the check digit test "
                          "after adding zeros"}
    if len(cleaned) == 10:
        if is_valid_isbn10(cleaned):
            return {"kind": "isbn10", "value": cleaned, "repairs": repairs}
        return {"kind": "problem", "reason": "isbn has a wrong check digit"}
    if re.fullmatch(r"\d{13}", cleaned):
        if is_valid_isbn13(cleaned):
            return {"kind": "isbn13", "value": cleaned,
                    "repairs": repairs + [REPAIR_MOVED]}
        return {"kind": "problem",
                "reason": "isbn has 13 digits but fails the ISBN-13 test"}
    return {"kind": "problem", "reason": "isbn is too long"}


def read_isbn13(raw):
    """Clean and test the isbn13 column. Returns a dictionary describing it."""
    cleaned = re.sub(r"[\s-]", "", raw)

    if cleaned == "":
        return {"kind": "blank", "repairs": []}
    if re.fullmatch(r"\d+", cleaned):
        # Answers 2 and 13: only 13 digits starting 978 or 979 looks real.
        if not re.fullmatch(r"(978|979)\d{10}", cleaned):
            return {"kind": "other_code"}
        if is_valid_isbn13(cleaned):
            return {"kind": "valid", "value": cleaned,
                    "repairs": [REPAIR_FORMAT] if cleaned != raw else []}
        return {"kind": "problem", "reason": "isbn13 has a wrong check digit"}
    if SCIENTIFIC_NUMBER.match(cleaned):
        # rules.md: scientific notation in isbn13 always uses its special rule.
        # It is confirmed against the ISBN-13 derived from a valid isbn, and the
        # row is rejected if they do not agree. Agreed with partners in Part 5:
        # a scientific value that is not an ISBN is not "another kind of code".
        return {"kind": "rounded", "number": Decimal(cleaned)}
    if DECIMAL_NUMBER.match(cleaned):
        number = Decimal(cleaned)
        if number != number.to_integral_value():
            return {"kind": "other_code"}
        whole_number = int(number)
        if re.fullmatch(r"(978|979)\d{10}", str(whole_number)):
            return {"kind": "rounded", "number": whole_number}
        return {"kind": "other_code"}
    return {"kind": "problem",
            "reason": "isbn13 contains a character that is not allowed"}


def conflict_problem(raw_isbn, raw_isbn13):
    return {"reason": "Columns conflict: isbn {!r} and isbn13 {!r} point to "
                      "different numbers".format(raw_isbn, raw_isbn13),
            "what_to_do": CHECK_CONFLICT}


def apply_isbn_rules(raw_isbn, raw_isbn13):
    """Apply section 1 of the rules to one row's two ISBN values."""
    # rules.md: if both incoming fields are blank (whitespace-only counts as
    # blank), reject even if that book already exists. It is an ISBN error.
    if is_blank(raw_isbn) and is_blank(raw_isbn13):
        return {"problems": [{"reason": "Both isbn and isbn13 are blank",
                              "what_to_do": FIND_ISBN}]}

    first = read_isbn(raw_isbn)
    second = read_isbn13(raw_isbn13)

    problems = []
    for result in (first, second):
        if result["kind"] == "problem":
            problems.append({"reason": result["reason"], "what_to_do": FIND_ISBN})
    if problems:
        return {"problems": problems}

    repairs = first.get("repairs", []) + second.get("repairs", [])
    warnings = []
    isbn = ""
    isbn13 = ""

    if first["kind"] == "isbn13":
        # A valid ISBN-13 was found in the isbn column.
        # rules.md: a nonblank destination must be the same full digit string
        # after cleanup. A scientific-notation destination counts as different.
        moved = first["value"]
        same_value = (
            second["kind"] == "blank"
            or (second["kind"] == "valid" and second["value"] == moved)
        )
        if not same_value:
            return {"problems": [conflict_problem(raw_isbn, raw_isbn13)]}
        isbn13 = moved
        isbn = isbn13_to_isbn10(moved)
        if isbn:
            repairs.append(REPAIR_CALCULATED)

    elif first["kind"] == "isbn10":
        isbn = first["value"]
        calculated = isbn10_to_isbn13(isbn)
        if second["kind"] == "valid":
            if second["value"] != calculated:
                return {"problems": [conflict_problem(raw_isbn, raw_isbn13)]}
            isbn13 = second["value"]
        elif second["kind"] == "rounded":
            if not matches_stored_number(calculated, second["number"]):
                return {"problems": [conflict_problem(raw_isbn, raw_isbn13)]}
            isbn13 = calculated
            repairs.append(REPAIR_REBUILT)
        elif second["kind"] == "other_code":
            warnings.append("isbn13 held a code that is not an ISBN ({}), so "
                            "it was left empty".format(raw_isbn13))
        else:
            isbn13 = calculated
            repairs.append(REPAIR_CALCULATED)

    else:
        # The isbn column is blank.
        if second["kind"] == "valid":
            isbn13 = second["value"]
            isbn = isbn13_to_isbn10(isbn13)
            if isbn:
                repairs.append(REPAIR_CALCULATED)
        else:
            warnings.append("This row has no usable ISBN, so it adds no ISBN values")

    return {"problems": [], "isbn": isbn, "isbn13": isbn13,
            "repairs": repairs, "warnings": warnings}


# ----- Comparing books -------------------------------------------------------

def normalize(text):
    """Ignore capitalization and extra spaces when comparing."""
    return re.sub(r"\s+", " ", text).strip().casefold()


def name_key(title, authors):
    return (normalize(title), normalize(authors))


def is_blank(text):
    return text is None or text.strip() == ""


def cannot_be_identified(title, authors):
    return any(
        is_blank(field) or normalize(field) in PLACEHOLDERS
        for field in (title, authors)
    )


class Library:
    """The books in books.db, plus quick ways to look them up."""

    def __init__(self, connection):
        self.connection = connection
        self.by_isbn13 = {}
        self.by_isbn = {}
        self.by_name = {}
        cursor = connection.execute(
            "SELECT id, {} FROM books".format(", ".join(COLUMNS)))
        for row in cursor:
            book = {column: ("" if row[i + 1] is None else row[i + 1])
                    for i, column in enumerate(COLUMNS)}
            book["id"] = row[0]
            self._remember(book)

    def _remember(self, book):
        if book["isbn13"]:
            self.by_isbn13[book["isbn13"]] = book
        if book["isbn"]:
            self.by_isbn[book["isbn"]] = book
        self.by_name.setdefault(name_key(book["title"], book["authors"]), []).append(book)

    def _forget(self, book):
        self.by_isbn13.pop(book["isbn13"], None)
        self.by_isbn.pop(book["isbn"], None)
        self.by_name[name_key(book["title"], book["authors"])].remove(book)

    def find_by_isbn(self, isbn, isbn13):
        if isbn13 and isbn13 in self.by_isbn13:
            return self.by_isbn13[isbn13]
        if isbn and isbn in self.by_isbn:
            return self.by_isbn[isbn]
        return None

    def find_no_isbn_book_by_name(self, title, authors):
        """Answer 3: a row with an ISBN can match a book that has none."""
        return [book for book in self.by_name.get(name_key(title, authors), [])
                if not book["isbn"] and not book["isbn13"]]

    def find_all_by_name(self, title, authors):
        return list(self.by_name.get(name_key(title, authors), []))

    def add(self, values):
        placeholders = ", ".join("?" for _ in COLUMNS)
        stored = [values[column] or None if column in ("isbn", "isbn13") else values[column]
                  for column in COLUMNS]
        cursor = self.connection.execute(
            "INSERT INTO books ({}) VALUES ({})".format(", ".join(COLUMNS), placeholders),
            stored)
        book = dict(values)
        book["id"] = cursor.lastrowid
        self._remember(book)

    def update(self, book, values):
        """Section 3: copy only changed values. A blank never erases a value."""
        changes = []
        for column in COLUMNS:
            new_value = values[column]
            if not is_blank(new_value) and new_value != book[column]:
                changes.append({"field": column, "old": book[column], "new": new_value})
        if not changes:
            return changes
        self._forget(book)
        for change in changes:
            book[change["field"]] = change["new"]
            self.connection.execute(
                "UPDATE books SET {} = ? WHERE id = ?".format(change["field"]),
                (change["new"], book["id"]))
        self._remember(book)
        return changes


# ----- Reading the file and the log ------------------------------------------

def read_rows(path):
    """Yield each row. Answer 14: a damaged row makes the whole file unreadable."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise UnreadableFile("The file is empty and has no header row")
        missing = [column for column in COLUMNS if column not in header]
        extra = [column for column in header if column not in COLUMNS]
        if missing or extra or len(header) != len(COLUMNS):
            raise UnreadableFile(
                "The header does not match the 23 expected columns "
                "(missing: {}; extra: {})".format(missing, extra))
        for row in reader:
            if len(row) != len(header):
                raise UnreadableFile(
                    "Line {} has {} columns, but {} were expected".format(
                        reader.line_num, len(row), len(header)))
            yield reader.line_num, dict(zip(header, row))


def read_log():
    """Earlier runs must never be overwritten, so a damaged log stops the run."""
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, encoding="utf-8") as handle:
        runs = json.load(handle)
    if not isinstance(runs, list):
        raise ValueError("the file does not contain a list of runs")
    return runs


def write_log(runs):
    """Write to a temporary file first, so a crash can't damage the log."""
    descriptor, temporary = tempfile.mkstemp(dir=HERE, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(runs, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.chmod(temporary, 0o644)
        os.replace(temporary, LOG_PATH)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


def open_database():
    connection = sqlite3.connect(DB_PATH, isolation_level=None)
    columns = ", ".join(
        "{} TEXT".format(column) for column in COLUMNS)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS books "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, {})".format(columns))
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS books_isbn13 ON books(isbn13) "
        "WHERE isbn13 IS NOT NULL")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS books_isbn ON books(isbn) "
        "WHERE isbn IS NOT NULL")
    return connection


# ----- Handling one row ------------------------------------------------------

def find_same_book(library, result, raw):
    """Section 2. Returns (book or None, rejection problem or None, warnings)."""
    title = raw["title"]
    authors = raw["authors"]
    has_isbn = bool(result["isbn"] or result["isbn13"])

    if has_isbn:
        book = library.find_by_isbn(result["isbn"], result["isbn13"])
        if book is not None:
            title_differs = normalize(book["title"]) != normalize(title)
            authors_differ = normalize(book["authors"]) != normalize(authors)
            if title_differs and authors_differ:
                return None, {
                    "reason": "Same ISBN as a different book already in the "
                              "database: {!r} by {!r}".format(book["title"], book["authors"]),
                    "what_to_do": CHECK_CONFLICT,
                }, []
            if title_differs or authors_differ:
                field = "Title" if title_differs else "Author"
                return book, None, [
                    "{} differs from the existing book with the same ISBN: "
                    "{!r} by {!r}".format(field, book["title"], book["authors"])]
            return book, None, []
        matches = library.find_no_isbn_book_by_name(title, authors)
        if len(matches) == 1:
            return matches[0], None, []
        if len(matches) > 1:
            raise RuntimeError("Several books with no ISBN share a title and author")
        return None, None, []

    if cannot_be_identified(title, authors):
        return None, {
            "reason": "No usable ISBN, and the title or author is blank or a placeholder",
            "what_to_do": FIND_ISBN,
        }, []
    matches = library.find_all_by_name(title, authors)
    if len(matches) > 1:
        return None, {
            "reason": "No usable ISBN, and the title and author match {} existing "
                      "books".format(len(matches)),
            "what_to_do": CHECK_CONFLICT,
        }, []
    return (matches[0] if matches else None), None, []


def new_entry(file_path):
    return {
        "ran_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "file": file_path,
        "verdict": None,
        "error": None,
        "rows_read": 0,
        "loaded": 0,
        "updated": 0,
        "skipped": 0,
        "rejected": 0,
        "totals_add_up": None,
        "totals_message": None,
        "repair_count": 0,
        "repairs_by_type": {},
        "warning_count": 0,
        "rejected_rows": [],
        "skipped_rows": [],
        "updates": [],
        "warnings": [],
    }


def describe(file_path, line, raw):
    return {"file": file_path, "line": line, "title": raw["title"],
            "isbn": raw["isbn"], "isbn13": raw["isbn13"]}


def process_row(library, entry, file_path, line, raw):
    entry["rows_read"] += 1
    result = apply_isbn_rules(raw["isbn"], raw["isbn13"])

    problems = result["problems"]
    book = None
    warnings = []
    if not problems:
        book, problem, warnings = find_same_book(library, result, raw)
        if problem:
            problems = [problem]
    if problems:
        rejected = describe(file_path, line, raw)
        rejected["problems"] = problems
        entry["rejected_rows"].append(rejected)
        entry["rejected"] += 1
        return

    # Repairs and warnings count only for rows that were not rejected.
    for repair in result["repairs"]:
        entry["repairs_by_type"][repair] = entry["repairs_by_type"].get(repair, 0) + 1
        entry["repair_count"] += 1
    for warning in result["warnings"] + warnings:
        flagged = describe(file_path, line, raw)
        flagged["warning"] = warning
        entry["warnings"].append(flagged)
        entry["warning_count"] += 1

    values = dict(raw)
    values["isbn"] = result["isbn"]
    values["isbn13"] = result["isbn13"]

    if book is None:
        library.add(values)
        entry["loaded"] += 1
        return

    changes = library.update(book, values)
    if changes:
        updated = describe(file_path, line, raw)
        updated["changes"] = changes
        entry["updates"].append(updated)
        entry["updated"] += 1
    else:
        skipped = describe(file_path, line, raw)
        skipped["reason"] = "Already in the database, and nothing changed"
        entry["skipped_rows"].append(skipped)
        entry["skipped"] += 1


def finish_entry(entry):
    total = entry["loaded"] + entry["updated"] + entry["skipped"] + entry["rejected"]
    entry["totals_add_up"] = total == entry["rows_read"]
    if entry["totals_add_up"]:
        entry["totals_message"] = (
            "Rows read ({}) = new books ({}) + updated books ({}) + unchanged "
            "duplicates ({}) + rejected rows ({})".format(
                entry["rows_read"], entry["loaded"], entry["updated"],
                entry["skipped"], entry["rejected"]))
    else:
        entry["totals_message"] = (
            "THE TOTALS DO NOT ADD UP: {} rows were read, but {} are accounted "
            "for. Something went wrong.".format(entry["rows_read"], total))
    if entry["rejected"] > 0 or not entry["totals_add_up"]:
        entry["verdict"] = VERDICT_ATTENTION
    else:
        entry["verdict"] = VERDICT_ALL_LOADED


def mark_failed(entry, error):
    """Answer 10: the changes were undone, so nothing from this run counts."""
    rows_read = entry["rows_read"]
    file_path = entry["file"]
    ran_at = entry["ran_at"]
    entry.clear()
    entry.update(new_entry(file_path))
    entry["ran_at"] = ran_at
    entry["rows_read"] = rows_read
    entry["verdict"] = VERDICT_FAILED
    entry["error"] = str(error)
    entry["totals_message"] = "The run failed, so all of its database changes were undone."


def print_summary(entry):
    print("{}: {}".format(entry["verdict"], entry["file"] or "(no file named)"))
    if entry["error"]:
        print("Error: {}".format(entry["error"]))
    print("Rows read: {}".format(entry["rows_read"]))
    print("Loaded:    {}".format(entry["loaded"]))
    print("Updated:   {}".format(entry["updated"]))
    print("Skipped:   {}".format(entry["skipped"]))
    print("Rejected:  {}".format(entry["rejected"]))
    print("Repairs:   {}".format(entry["repair_count"]))
    print("Warnings:  {}".format(entry["warning_count"]))
    print(entry["totals_message"])
    print("Open report.html and choose ingestion-log.json to see the details.")


def main(arguments):
    try:
        runs = read_log()
    except (OSError, ValueError) as error:
        print("Stopped: ingestion-log.json could not be read ({}).".format(error))
        print("Nothing was changed, so earlier runs are still in that file.")
        return 1

    file_path = arguments[0] if len(arguments) == 1 else None
    entry = new_entry(file_path)
    connection = None
    try:
        if file_path is None:
            raise UnreadableFile("Name one file to load, for example: python3 ingest.py books.csv")
        connection = open_database()
        connection.execute("BEGIN")
        library = Library(connection)
        for line, raw in read_rows(file_path):
            process_row(library, entry, file_path, line, raw)
        connection.execute("COMMIT")
        finish_entry(entry)
    except Exception as error:
        # Answer 10: any failure undoes this run's changes and is logged.
        if connection is not None and connection.in_transaction:
            connection.execute("ROLLBACK")
        mark_failed(entry, error)
    finally:
        if connection is not None:
            connection.close()

    runs.append(entry)
    write_log(runs)
    print_summary(entry)
    return 1 if entry["verdict"] == VERDICT_FAILED else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
