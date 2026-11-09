# Rules for the books

I want the same files to get the same decisions every time. Leave the original CSVs alone. This file is the source of truth for the new code and tests. The old Module 3 code and results do not yet follow these rules.

## Checking ISBNs

Keep ISBNs as text. ISBN-10 has nine digits and a final digit or uppercase X. Its weighted sum, using weights 10 down to 1 and X as 10, must divide evenly by 11. ISBN-13 has 13 digits, starts with 978 or 979, and its alternating 1 and 3 weighted sum must divide evenly by 10. There is no extra 9790 exclusion in this project's check. Passing these tests does not prove the ISBN belongs to the title.

Clean spaces and ordinary hyphens and turn lowercase x into X. Count a changed value as a formatting repair. For a plain short isbn of 2 through 9 characters, with digits and possibly a final X, add zeros on the left to reach 10 characters. Keep it only if the checksum passes. Never add zeros to make an ISBN-13. Cleanup can be followed by this padding before deciding that it failed.

Reject the whole row for an illegal character after permitted cleanup, a bad checksum at the correct ISBN length, or an overlong isbn that is not a valid ISBN-13. Do not guess replacement letters, remove digits, or change a wrong check digit. These errors are not rescued by a good value in the other column. Record every problem. Illegal characters take priority over too short for the same value.

Use valid values and calculate a missing equivalent when possible. To convert ISBN-10, add 978 to its first nine digits and calculate the ISBN-13 check digit. To convert a 978 ISBN-13, remove 978 and calculate the ISBN-10 check digit. A 979 ISBN-13 has no ISBN-10 equivalent, so leave isbn blank. Count filling a missing equivalent as a repair.

A valid ISBN-13 in isbn should move to isbn13. Count the move as a repair and calculate ISBN-10 when possible. If a nonblank destination differs after whitespace/hyphen cleanup, reject the row rather than overwrite it. For this move rule, a scientific-notation destination is different from a full digit string and is rejected. Do this check before the scientific-notation rule.

If both usable ISBN values identify different books, reject the row and report both. If both incoming fields are blank, reject even if that book already exists. Whitespace-only counts as blank.

Scientific notation in isbn13 has a special rule. First require a valid ISBN-10 in isbn, after permitted cleanup and padding. Derive its complete ISBN-13 and round that number to 12 significant digits using exact decimal arithmetic, with ties rounded to even. Compare that rounded number numerically with the supplied scientific value. Use exactly 12 significant digits regardless of how many the supplied value displays. If they agree, store the full derived ISBN-13 and count a repair. If not, reject. Never store the rounded number or test its expanded checksum as a substitute for this confirmation.

If isbn is blank and isbn13 is scientific notation, do not repair it. Use the no-ISBN rule below with a warning. Scientific notation and decimal notation in isbn are not permitted repairs; reject them as invalid isbn formatting.

In isbn13, a numeric code with the wrong length or a prefix other than 978 or 979 is another kind of code. A decimal-looking value, including one ending in .0, also uses this rule. Do not remove its decimal part. If isbn is valid, load with a warning and leave isbn13 blank. If isbn is blank, use the no-ISBN rule. A numeric ISBN-10 in isbn13 is also another code, not something to rescue as ISBN-10. A correctly shaped 13-digit 978/979 value with a bad checksum is still rejected, not treated as another code.

Recognize scientific and decimal notation before generic character checks, and before removing hyphens that might be exponent signs. A leading plus or minus on an ordinary identifier is invalid. The special isbn13 code fallback is not permission to replace arbitrary letters in ISBNs.

A blank made by discarding another code is not an originally missing equivalent: do not immediately fill it again. Keep the original field states while deciding. This also explains why an originally blank/blank row is rejected, but a row containing a nonblank other code can load with both stored ISBNs empty.

The listed repairs are the only repairs allowed. Checking a proposed value gives evidence. Choosing missing digits just so a checksum passes is not independent evidence. Leading-zero padding is an explicit permitted assumption, not proof that the identifier belongs to the book.

## What is the same book

Match repaired ISBN-13 first, then ISBN-10 if ISBN-13 is absent. Convert between equivalent ISBN forms when comparing, so the same edition is not duplicated just because one row has only ISBN-10. Different usable ISBNs are different editions. Publication year is a detail, not an identity key.

For an allowed no-ISBN row, require a nonblank title and authors. Reject if either whole field, ignoring case and extra spaces, is Unknown, Untitled, or Untitled Manuscript. Match these rows by title and authors together. If there is no match, insert a book with empty ISBN fields and a warning. If several entries match, reject as ambiguous. If exactly one matches, use that entry. A row with an ISBN and a row without one can match this way; do not use title/author matching to merge two different usable ISBNs.

For comparisons, ignore capitalization, trim the ends and collapse repeated whitespace. Do not remove punctuation or accents or rearrange author names. Store authors as one field. Keep original display values except when an accepted update replaces them.

For an ISBN match, if both title and author differ, reject and leave the old entry alone. If only one differs, accept with a warning and update that field if the incoming value is nonblank. Case or whitespace differences alone do not change the stored title or authors. If both are the same under comparison, keep their existing display spelling.

Supplier book_id is source information, not the book's unique identity. Keep it as supplied, without requiring a positive number. Different books may share a supplier ID; warn when an ID already appears on a different catalog entry. Give books separate internal database IDs. Do not match or reject solely because supplier IDs match. Title and author are required for no-ISBN fallback; do not add a separate missing-title/author rejection for ISBN-bearing rows beyond the identity rules above.

## When a book comes again

Check every row every time, including duplicates and previously loaded files. Validate before matching or skipping. An identical accepted row is skipped, including a repeat within the same file. It does not add a physical copy or increase books_count.

For a matched book, replace ordinary fields only with changed nonblank incoming values. Whitespace-only is blank for this decision. Never erase a good stored value with a blank. Keep original text for stored non-ISBN values. An accepted later ISBN can fill a previously missing identifier, but cannot overwrite a different valid identifier. Rejected rows make no changes.

Process files in the order given and records in file order. Treat later accepted data as newer because the files do not give us reliable delivery dates. Count each accepted row once as inserted, updated or skipped. A new identifier or changed stored field counts as updated. Warnings and repairs are additional counts, not extra outcomes.

## Files and the report

Require all 23 headers from the supplied books.csv, without duplicates; header order may differ. Reject the file if one is missing or an unexpected header is present. Store all 23 source fields, with ISBNs replaced by the results of these rules and empty ISBNs represented consistently as null in the database. Keep other source values as text. Read UTF-8 with or without its byte-order mark. Ignore completely empty lines. Too many or too few fields, unreadable input or broken CSV means the whole run fails. Roll back changes from every file in that run. Report where reading stopped and do not claim unread records were checked.

Run offline with Python's standard library, without AI or internet. Put books.db and ingestion-log.json beside ingest.py. Accept CSV paths in the order supplied. Do not run two imports at once. Tests must use isolated test.db files and temporary logs, never the real books.db or ingestion-log.json, and remove their temporary files after passing or failing.

Add each run to ingestion-log.json without losing old entries. Stop without modifying the catalog if the existing log is unreadable. Keep a recovery copy of run entries in SQLite so an interrupted JSON write can be recovered. Keep original values needed to explain warnings, rejections and changes in the log. Do not add original-ISBN columns to the catalog or keep a separate itemized history of every repair. Count repairs by type. A field can have several repair types; also count distinct rows with repairs.

For every run, show time, files in order, their hashes, completion status and catalog count before and after. Show rows read, newly loaded, updated, skipped and rejected, for each file and overall. Loaded means inserted. The four outcomes must add up to rows read. Say plainly if totals do not match. For a failed run, count fully parsed rows as rejected because the run was rolled back; give a separate file error for the damaged or unread portion.

Show skipped and rejected rows separately. Give each its file, CSV record number, title, supplier ID, relevant original/interpreted ISBNs and reason. Row numbers count CSV records including the header as 1, not physical lines inside quoted text. List warnings and updates too, with old and new values for each update. Count rejection reasons and repair types. Explain that warning and repair counts overlap the outcomes.

Every rejection gets an action sentence. ISBN errors say: Find the correct ISBN, correct the row, and load the file again. Identity or column conflicts say: Check which value or book is correct. Missing no-ISBN identity says: Supply an identifying title and author, then load the file again. File errors say: Correct the file error and rerun the files. A row whose isbn and isbn13 are both blank is an ISBN error and uses the ISBN sentence, even when its title and author are usable; the missing-identity sentence is for a no-ISBN row whose title or author is blank or a placeholder. These action sentences are fixed and must appear word for word. The wording of the reason itself is not fixed. Source corrections should be made in a separately named corrected delivery so the originals stay unchanged.

Use the verdict Completed when a successful run has no rejected rows, Some rows need attention when it has rejections, and Failed when the run fails. Warnings alone do not change the verdict. Both JSON and HTML must contain updates, warnings and repair counts. The HTML opens without a server, has a button to select ingestion-log.json, shows newest runs first and lets the reader expand row details.

## Examples for the tests

Each example below is a new row with a real nonblank title and author, a supplier ID, and no existing conflicting match unless stated. Blank means empty. Load means insert; repairs are counted, and warnings are included only where required by the rules. Repair and warning counts must match each example exactly: a row gets only the repairs its example names, none if it names none, and a warning only where its example says so. Do not silently add requirements from the old rules or old code.

| isbn | isbn13 | Expected result |
|---|---|---|
| 0439139600 | 9780439139601 | Load. Both agree; no ISBN repair or warning. |
| 043965548X | blank | Load; calculate the missing ISBN-13 and count a repair. |
| 031200009x | 9780312000097 | Change x to X, count formatting repair, load. |
| 0-450-19827-8 | 9780450198274 | Remove hyphens, count formatting repair, load. |
| ` 162 001 4750 ` | 9781620014752 | Remove spaces, count formatting repair, load. |
| 439023483 | blank | Pad to 0439023483, calculate 9780439023481, count both repairs, load. |
| 439554934 | 9.78043955493e+12 | Pad ISBN-10; confirm rounded agreement; store 9780439554930 and load. Count padding and scientific-notation repairs. |
| 439023483 | 9.78043902348e+12 | Pad ISBN-10; confirm rounded agreement; store 9780439023481 and load. Count both repairs. |
| blank | 9.78043902348e+12 | Load without ISBNs, using title/author identity, with a warning. Do not repair the rounded number. |
| blank | 76783609419.0 | Treat as another code. Load without ISBNs with a warning. |
| blank | 9780439139601.0 | Do not strip .0. Load without ISBNs with a warning. |
| 04390A3483 | blank | Reject illegal character. |
| 15287463097 | blank | Reject overlong isbn. |
| 1854433017 | blank | Reject bad checksum. |
| blank | blank | Reject, including when the supplier ID belongs to a known book. |
| 1555550126 | 9781555550134 | Reject conflicting ISBNs. |
| 9781982147600 | blank | Move to isbn13, calculate ISBN-10, load and count both repairs. |
| blank | 9798351220413 | Load. Leave isbn blank; no missing-equivalent repair or warning is required. |
| 0439139600 | 9780061120085 | Reject bad checksum in isbn13 even though isbn is good. |
| 0439139600 | 12345 | Load with warning and leave isbn13 null. Do not fill the discarded field afterward. |
| 9780439139601 | 9.7804391396e+12 | Reject the move conflict: the cleaned destination is not the same full digit string. |
| 0439139600, same row again | 9780439139601 | Skip unchanged after validation; no duplicate book. |
