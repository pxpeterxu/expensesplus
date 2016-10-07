__author__ = 'Peter Xu'

from xlwings import Range

"""
Utility functions for Excel
"""

def append_to_table(left_top_cell, data):
    """
    Append data to a table, taking care to not overwrite existing rows of data
    :type left_top_cell Range
    """

    row_length = 1 if len(data) == 0 else len(data[0])

    # Find the first empty row
    row = left_top_cell
    row_empty = False
    while not row_empty:
        row_empty = True
        for col in xrange(row_length):
            cell = row.offset(0, col)
            if cell.value is not None:
                row_empty = False

        if not row_empty:
            row = row.offset(1)

    # row should now be the first empty row
    for entry in data:
        row.value = entry
        row = row.offset(1)
