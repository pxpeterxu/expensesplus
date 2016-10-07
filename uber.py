__author__ = 'Peter Xu'

import datetime
import pdf
import re

def read_single_uber(text):
    # First number should be total fare
    match = re.search('\$(\d+\.\d+)', text)
    if match is None:
        raise Exception('Could not get $ amount of Uber ride')
    amount = match.group(1)

    match = re.search('\d+/\d+/\d+', text)
    if match is None:
        raise Exception('Could not get date of Uber ride')
    date = match.group(0)

    match = re.search('\d{2}:\d{2} (AM|PM)', text)
    if match is None:
        raise Exception('Could not get time of Uber ride')
    time = match.group(0)

    date_obj = datetime.datetime.strptime(date + ' ' + time, '%m/%d/%Y %I:%M %p')
    return {
        'date': date_obj,
        'amount': amount
    }


def read_uber(receipts_file):
    """
    Given a receipt PDF file, open it, read it, and get the date of the trip(s), amounts paid,
    etc.
    :param receipts_file: Uber receipt PDF file
    :return: [dict with {date, amount}]
    """
    text = pdf.pdf_to_text(receipts_file)

    sections = text.split('Rate Your Driver')
    sections.pop()  # Last section has no data

    results = []
    errors = []
    for i in xrange(len(sections)):
        section = sections[i]
        try:
            result = read_single_uber(section)
            results.append(result)
        except Exception as e:
            error_text = 'Section {0} did not seem to be a valid Uber receipt: {1}'.format(i + 1, e.message)
            errors.append(error_text)
            print e.message


    return results, errors
