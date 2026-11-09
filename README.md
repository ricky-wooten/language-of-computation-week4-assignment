# Language of Computation: Week 4 Assignment

This is my Module 4 assignment for MSAI-5523.

Partners: John and Micaiah

## Running the tests

The tests use Python 3 and pytest. `ingest.py` itself needs only Python's standard library; pytest is needed only to run the tests. Run every command below in a terminal, from inside the `week4-assignment` folder.

Install (once). This creates a private Python environment in a `.venv` folder and installs pytest into it:

```bash
python3 -m venv .venv
```

```bash
.venv/bin/python -m pip install pytest
```

Run the tests:

```bash
.venv/bin/python -m pytest
```

pytest finds every `test_*.py` file in this folder and prints a summary such as `22 passed`. The tests use their own temporary `test.db` and log files and delete them afterwards; they never touch `books.db` or `ingestion-log.json`.

## Running ingest.py

Each run loads one CSV file into `books.db` and adds an entry to `ingestion-log.json`, both in this folder. Run these three commands in this order.

Load books.csv:

```bash
python3 ingest.py books.csv
```

Load books.csv again (every row is checked again; rows accepted the first time should be skipped as unchanged, and no duplicates should be added):

```bash
python3 ingest.py books.csv
```

Load books-batch2.csv:

```bash
python3 ingest.py books-batch2.csv
```

To see the results, open `report.html` in a web browser and choose `ingestion-log.json`.

To start over from an empty catalog, delete `books.db` and `ingestion-log.json` before the first command.
