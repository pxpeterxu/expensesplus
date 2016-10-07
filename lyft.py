__author__ = 'Peter Xu'

import datetime
import pdf
import re

def read_single_lyft(text):
    # Get the date string through a 2-step process
    # 1. Get the day and time of the ride
    match = re.search('ending(.*)at(.*)', text)
    if match is None:
        raise Exception('Could not find date from Lyft receipt')

    date_str = match.group(1).strip()
    time_str = match.group(2).strip()

    match = re.search('20\d{2}', text)
    if match is None:
        raise Exception('Could not find year from Lyft receipt')

    year = match.group(0)
    date = datetime.datetime.strptime(date_str + ' ' + year + ' ' + time_str, '%B %d %Y %I:%M %p')

    # 2. Get the amount of the ride
    if text.find('Total charged') == -1:
        raise Exception('Could not get amount of Lyft ride')

    parts = text.split('Total charged')
    match = re.search('\n\n\$([\d.]+)\n\n', parts[1])
    if match is None:
        raise Exception('Could not find amount of Lyft ride')

    amount = match.group(1)
    return {
        'date': date,
        'amount': amount
    }

def read_lyft(receipts_file):
    """
    Given a receipt PDF file, open it, read it, and get the date of the trip, amounts paid,
    etc.
    :param receipts_file: Lyft receipt PDF file
    :return: [dict with {date, amount}]
    """
    text = pdf.pdf_to_text(receipts_file)

    sections = text.split('Work at Lyft')
    sections.pop()  # Last section has no data

    results = []
    errors = []
    for i in xrange(len(sections)):
        section = sections[i]
        try:
            result = read_single_lyft(section)
            results.append(result)
        except:
            errors.append('Failed while reading section {0} of receipt: '.format(i + 1, ))

    return results
