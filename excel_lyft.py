__author__ = 'Peter Xu'

from xlwings import Workbook, Range
import settings
import lyft
import excel_lib

def main():
    wb = Workbook.caller()

    files = Range(settings.lyft_sheet, (settings.lyft_files_row, 1)).horizontal
    if files.is_cell():
        files = [files.value]
    else:
        files = files.value

    receipts = []
    for file in files:
         receipts += lyft.read_lyft(file)

    receipts_table = [['', '', receipt['date'].strftime('%Y-%m-%d'), receipt['amount'], '', # Column E
        '', '', '', 'Lyft trip at ' + receipt['date'].strftime('%I:%M%p')] for receipt in receipts]

    excel_lib.append_to_table(Range(settings.taxi_sheet, (settings.taxi_start_row, 1)), receipts_table)

    print 'Successfully added {0} Lyft entries.'.format(len(receipts))
    print 'Press enter to finish...'
    raw_input()

if __name__ == '__main__':
    main()
