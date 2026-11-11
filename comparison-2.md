# Comparison of books.db files

**Result: the databases do NOT hold the same data.**

| Database | Books |
|---|---|
| mine (`books.db`) | 9407 |
| partner-2 (BigStupidTech) (`partner-2/books.db`) | 9404 |

## How books were compared

Following rules.md ("What is the same book"): two rows are the same book if they have the same ISBN-13; a row with only an ISBN-10 is compared through its equivalent ISBN-13; a row with no ISBN is matched by title and authors together, ignoring capitalization and extra spaces. For every book found in more than one database, all 23 source columns are compared by exact stored value (*null* and *empty* are different). Left out: `books.id` (internal insert order) and partner-2's run-log table (`run_history`).

## Summary

| | Count |
|---|---|
| Books in both databases | 9404 |
| Books only in mine | 3 |
| Books in both with a different value | 0 |
| Individual column differences | 0 |

## Books only in mine (3)

| Book identity | Title | Authors | isbn | isbn13 | book_id |
|---|---|---|---|---|---|
| ISBN-13 `9781892213013` | `Sailor Moon, #1 (Sailor Moon, #1)` | `Naoko Takeuchi` | `189221301X` | *null* | `2894` |
| ISBN-13 `9780883681053` | `The Practice of the Presence of God` | `Brother Lawrence` | `0883681056` | *null* | `3689` |
| ISBN-13 `9780789480453` | `Anatomy for the Artist` | `Sarah Simblet` | `078948045X` | *null* | `5268` |

## Books in both with a different value (0 columns in 0 books)

None.

## Why our data differs

Our three databases do not contain exactly the same books. Mine has 9,407 books while both partners have 9,404. The difference is three books that appear only in my database.

These three books came from the original books.csv file. Each one has a valid ISBN-10 in the isbn column, but the isbn13 column contains a number written in scientific notation (for example, 6.45573003012e+11) that is not a real ISBN-13.

When I processed the data, I treated those scientific-notation values as “another kind of code.” I loaded the books anyway (with a warning) and left the isbn13 field empty. Both of my partners rejected the rows completely, so the three books never made it into their databases.

Looking at the rules more carefully, scientific notation in the isbn13 column has its own special handling. The rule says to derive a proper ISBN-13 from the valid ISBN-10, round that result to 12 significant digits, and compare it with the scientific-notation value. If they match, you store the full derived ISBN-13 and count it as a repair. If they do not match, you reject the row.

In these three cases the derived ISBN-13 does not round to the scientific-notation number that was in the CSV, so the special rule says the rows should be rejected. The “another kind of code” rule is meant for things like plain numeric codes or decimal-looking values, not for scientific notation. Under that reading, my partners followed the rules and I did not.

My partners and I all agreed that my database has three books that differ from theirs, and that their two databases agree with each other. Because my two partners' results match each other and mine differs, we are going with their reading of the rules, not mine: these three rows should be rejected.
