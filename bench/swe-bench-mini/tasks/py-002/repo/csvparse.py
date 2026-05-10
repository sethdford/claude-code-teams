"""CSV line parser with multiple known bugs."""

def parse_csv_line(line):
    # BUG 1: doesn't handle quoted fields containing commas
    # BUG 2: doesn't strip trailing newline
    # BUG 3: doesn't handle escaped double-quote ("") inside a quoted field
    return line.split(",")
