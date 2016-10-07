__author__ = 'Peter Xu'

from xlwings import Workbook, Range
import settings
import uber
import excel_lib

def main():
    wb = Workbook.caller()

    files = Range(settings.uber_sheet, (settings.lyft_files_row, 1)).horizontal
    if files.is_cell():
        files = [files.value]
    else:
        files = files.value

    receipts = []
    errors = []
    for file in files:
        these_receipts, these_errors = uber.read_uber(file)
        receipts += these_receipts
        errors += these_errors

    receipts_table = [['', '', receipt['date'].strftime('%Y-%m-%d'), receipt['amount'], '', # Column E
        '', '', '', 'Uber trip at ' + receipt['date'].strftime('%I:%M%p')] for receipt in receipts]

    excel_lib.append_to_table(Range(settings.taxi_sheet, (settings.taxi_start_row, 1)), receipts_table)

    print 'Successfully added {0} Uber entries.'.format(len(receipts))
    print 'Press enter to finish...'
    raw_input()

if __name__ == '__main__':
    main()
