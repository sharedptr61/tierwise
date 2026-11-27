Add a CSV export to the shop command line tool.

- `python3 -m shop export <orders.json> --out <file.csv>` writes a CSV file with the header `id,customer,amount,status`, then one row per order in the input order, then a final row `TOTAL,,<amount>,` whose amount is the sum of all orders that are not cancelled.
- Amounts are written with two decimals, from `amount_cents` (the existing `format_amount` does this).
- Customer names can contain commas, double quotes and line breaks; the file must read back correctly with a standard CSV reader.
- Protect against spreadsheet formula injection: a customer value that starts with `=`, `+`, `-` or `@` is written with a leading single quote (`'`).
- Exit status 0 on success. A missing input file or invalid JSON prints an error to stderr and exits with status 1.
- Put the logic in a function `export_csv(orders, out_path)` in `shop/export.py`; the command line uses it.
- Include tests.

Make reasonable decisions yourself; do not stop to ask me.
