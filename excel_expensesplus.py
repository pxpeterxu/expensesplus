__author__ = 'Peter Xu'
from xlwings import Workbook, Range
import getpass
import client
import os
import settings
import traceback

#
# Data reading functions
#

def read_and_verify_data(sheet, columns, optional_columns=None, errors=None,
                         error_callback=None):
    optional_columns = [] if optional_columns is None else optional_columns
    errors = [] if errors is None else errors

    if Range(sheet, 'A4').value is None or Range(sheet, 'A4').value == '':
        # No expenses of this type exist
        return []

    row_count = len(Range(sheet, 'A4').vertical)
    column_count = len(columns)

    # Check each row for data
    data_range = Range(sheet, (4, 1), (4 + row_count - 1, column_count))

    rows = []
    if data_range.is_row():
        rows = [data_range.value]
    else:  # range.is_table()
        rows = data_range.value

    entries = []
    for index in xrange(len(rows)):
        row = rows[index]
        row_num = 4 + index
        entry = {}
        for i in xrange(column_count):
            field = columns[i]  # Field
            value = row[i]
            entry[field] = value

            if field not in optional_columns and not value:
                column_title = Range(sheet, (3, i + 1)).value
                errors.append('{0}: row {1} - missing entry for {2}'.
                              format(sheet, row_num, column_title))

        if error_callback:
            # For custom validation and errors
            error = error_callback(entry)
            if error:
                errors.append('{0}: row {1} - {2}'.format(sheet, row_num, error))

        entries.append(entry)

    return entries

def read_hotel_data(errors):
    # Hackish, but read the fields for meal0_date, ..., meal9_amount into the fields
    meal_fields = []
    for i in xrange(10):
        for field in ['date', 'type', 'amount']:
            meal_fields.append('meal{0}_{1}'.format(i, field))

    rows = read_and_verify_data(settings.hotel_sheet, [
        'charge_code', 'location', 'check_in', 'check_out', 'total',
        'room_rate', 'tax1', 'tax2', 'tax3', 'tax4', 'tax5',
        'breakfast', 'parking', 'internet',
        'currency', 'notes'
    ] + meal_fields, [
        'tax1', 'tax2', 'tax3', 'tax4', 'tax5', 'breakfast', 'parking', 'internet', 'notes'
    ] + meal_fields, errors)

    # Takes the itemized hotel meal data and put it into an array useful for input into add_hotel_expense

    for row in rows:
        meals = []
        for i in xrange(10):
            meal = {}
            for field in ['date', 'type', 'amount']:
                full_field = 'meal{0}_{1}'.format(i, field)
                meal[field] = row[full_field]
                del row[full_field]

            if meal['date'] and meal['type'] and meal['amount']:
                meals.append({
                    'date': meal['date'],
                    'type': meal['type'],
                    'amount': meal['amount']
                })

        row['meals'] = meals
    return rows


def read_meal1_data(errors):
    return read_and_verify_data(settings.meal1_sheet, [
        'charge_code', 'location', 'date', 'amount', 'meal', 'currency', 'notes'
    ], ['notes'], errors=errors)

def read_meal2_data(errors):
    return read_and_verify_data(settings.meal2_sheet, [
        'charge_code', 'location', 'date', 'amount', 'nature', 'attendee_count', 'currency', 'notes'
    ], ['notes'], errors=errors)

def read_meal3_data(errors):
    data = read_and_verify_data(settings.meal3_sheet, [
        'charge_code', 'location', 'date', 'amount', 'nature', 'meal', 'vendor',
        'attendees', 'currency', 'notes'
    ], ['notes'], errors=errors)

    for entry in data:
        if 'attendees' in entry and entry['attendees']:
            attendee_list = entry['attendees'].split(';')
            attendee_list = [attendee.strip() for attendee in attendee_list]

            entry['attendees'] = attendee_list

    return data

def read_taxi_data(errors):
    def check_taxi_expense(expense):
        if (expense['source'] == 'Home' and expense['destination'] == 'Office') or \
            (expense['source'] == 'Office' and expense['destination'] == 'Home'):

            if not expense['explanation']:
                return 'An explanation is required for travel between Office and Home: ' +\
                    'Must be late, or in excess of normal commute'

        if expense['source'] == 'Other' or expense['destination'] == 'Other':
            if not expense['explanation']:
                return 'An explanation is required for travel to/from "Other" destinations'

    return read_and_verify_data(settings.taxi_sheet, [
        'charge_code', 'location', 'date', 'amount', 'source', 'destination', 'currency',
        'explanation', 'notes'
    ], ['explanation', 'notes'], errors=errors, error_callback=check_taxi_expense)

#
# Data submission functions
#

def submit_data(description_formatter, add_function, entries, errors):
    for entry in entries:
        entry_text = description_formatter(entry)
        try:
            add_function(**entry)
            print 'SUCCESS: created ' + entry_text
        except Exception as e:
            err_text = 'FAILURE: could not create ' + entry_text
            print err_text
            errors.append(err_text + ': ' + e.message)

def submit_hotel(cli, entries, errors):
    return submit_data(lambda entry: ('Hotel entry for stay from {0.year}-{0.month}-{0.day} ' +
                                      'to {1.year}-{1.month}-{1.day}').
                       format(entry['check_in'], entry['check_out']),
                       cli.create_hotel_entry, entries, errors)

def submit_meal1(cli, entries, errors):
    return submit_data(lambda entry: 'Meals 1 entry for {0} on {1.year}-{1.month}-{1.day}'.
                       format(entry['meal'], entry['date']),
                       cli.create_meal1_entry, entries, errors)

def submit_meal2(cli, entries, errors):
    return submit_data(lambda entry: 'Meals 2 entry for {0} on {1.year}-{1.month}-{1.day}'.
                       format(entry['nature'], entry['date']),
                       cli.create_meal2_entry, entries, errors)

def submit_meal3(cli, entries, errors):
    return submit_data(lambda entry: 'Meals 3 entry for {0} on {1.year}-{1.month}-{1.day}'.
                       format(entry['meal'], entry['date']),
                       cli.create_meal3_entry, entries, errors)

def submit_taxi(cli, entries, errors):
    return submit_data(lambda entry: 'Taxi ride on {0.year}-{0.month}-{0.day} from {1} to {2}'.
                       format(entry['date'], entry['source'], entry['destination']),
                       cli.create_taxi_entry, entries, errors)

def output_errors(errors):
    """
    Write the errors onto the worksheet
    """
    for i in xrange(len(errors)):
        row = i + settings.warning_errors_row_start
        cell = Range(settings.instructions_sheet, (row, 1))
        cell.value = errors[i]

def main():
    cli = client.Client()

    print '|=========================================================|'
    print '| Welcome to ExpensesPlus, the easier way to do expenses! |'
    print '| Authored by Peter Xu, Business Analyst, SVO             |'
    print '|=========================================================|'
    print ''

    wb = Workbook.caller()

    # Clear error and output cells
    Range(settings.instructions_sheet, (settings.warning_errors_row_start, 1)).vertical.clear_contents()
    Range(settings.instructions_sheet, settings.er_cell).clear_contents()

    # Check for errors, missing data while reading in all the data
    errors = []
    hotel_data = read_hotel_data(errors)
    meal1_data = read_meal1_data(errors)
    meal2_data = read_meal2_data(errors)
    meal3_data = read_meal3_data(errors)
    taxi_data = read_taxi_data(errors)

    if not (hotel_data or meal1_data or meal2_data or meal3_data or taxi_data):
        errors.append('You have not entered any expenses yet!')

    title = Range(settings.instructions_sheet, settings.title_cell).value
    if not title:
        errors.append('Please enter an expense report title (on the Instructions worksheet)')

    if errors:
        output_errors(errors)
        return

    print 'Logging into My Time & Exp:'

    logged_in = False
    while not logged_in:
        print
        print 'Please enter your Windows username (e.g. "John Doe"): '
        username = raw_input()  # raw_input doesn't seem to print text to screen
        print
        print 'Please enter your password:'
        print '(it will not show up as you type for security reasons; press enter once done)'
        password = getpass.getpass()

        try:
            print 'Please wait; attempting login...'
            cli.login(username, password)
            logged_in = True
            print 'Logged in'
        except Exception as e:
            print e.message

    try:
        print '1. Creating expense report'
        er = cli.create_expense_report(title)

        Range(settings.instructions_sheet, settings.er_cell).value = er

        print '2. Submitting Hotels entries'
        submit_hotel(cli, hotel_data, errors)

        print '3. Submitting Meals 1 entries'
        submit_meal1(cli, meal1_data, errors)

        print '4. Submitting Meals 2 entries'
        submit_meal2(cli, meal2_data, errors)

        print '5. Submitting Meals 3 entries'
        submit_meal3(cli, meal3_data, errors)

        print '6. Submitting Taxi entries'
        submit_taxi(cli, taxi_data, errors)
    except Exception as e:
        print e.message
        print traceback.format_exc()
        print 'Press enter to exit...'
        raw_input()
        exit()


    print ''
    print 'Uploading receipts...'

    # Look for .pdf files in the directory
    receipt_dir = Range(settings.instructions_sheet, settings.receipt_location_cell).value
    receipt_files = []
    try:
        for file in os.listdir(receipt_dir):
            print file
            file_lower = file.lower()
            if file_lower.endswith('.pdf') or file_lower.endswith('.tif') or\
                    file_lower.endswith('.tiff') or file_lower.endswith('jpg') or\
                    file_lower.endswith('.gif'):
                receipt_files.append(os.path.join(receipt_dir, file))
    except:
        # Invalid receipt directory
        pass

    if receipt_files:
        # Print for user confirmation
        try:
            cli.upload_receipts(receipt_files)
        except:
            print 'Some receipts may not have successfully uploaded. Please check if all of them were uploaded'

    if not errors:
        errors = ['No errors! You\'re good to go.']
    output_errors(errors)

    print
    print 'Done! Press enter to finish...'
    raw_input()
    # cli.delete_expense_report(er)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print 'We encountered an unexpected error:'
        print e.message
        print traceback.format_exc()
        print 'Press enter to exit...'
        raw_input()
        exit()
