__author__ = 'Peter Xu'

import os
import client
import random

cli = client.Client()

print 'Starting test script!'
print 'Please enter your Windows username (e.g. "John Doe"): '
username = raw_input()  # raw_input doesn't seem to print text to screen
print 'Please enter your Windows password: '
password = raw_input()
print 'Please enter a charge code to use in testing: '
charge_code = raw_input()

cli.login(username, password)

expense_id = cli.create_expense_report('ExpensesPlus Test')

print 'Testing domestic transactions'
cli.create_meal1_entry(charge_code, 'San Francisco', '5/2/15', '20.15', 'Breakfast', 'USD')
cli.create_meal2_entry(charge_code, 'San Francisco', '5/3/15', '12.34', 'Working Meetings', 3)
cli.create_meal3_entry(charge_code, 'San Francisco', '5/4/15', '23.45', 'Occasional Team Celebration', 'Dinner', 'Chipotle', ['Peter Xu', 'Sarah Lorenzana'])
cli.create_hotel_entry(charge_code, 'San Francisco', '5/5/15', '5/8/15', '600', 150, tax1=50)
cli.create_taxi_entry(charge_code, 'San Francisco', '5/9/15', '12.34', 'Home', 'Client')
cli.create_taxi_entry(charge_code, 'San Francisco', '5/9/15', '24.68', 'Office', 'Home', 'Working late')

# Foreign currency tests
print 'Testing foreign transactions'
cli.create_meal1_entry(charge_code, 'Hong Kong', '5/2/15', '20.15', 'Breakfast', 'HKD')
cli.create_meal2_entry(charge_code, 'Hong Kong', '5/3/15', '12.34', 'Working Meetings', 3, 'HKD')
cli.create_meal3_entry(charge_code, 'Hong Kong', '5/4/15', '23.45', 'Occasional Team Celebration', 'Dinner', 'Chipotle', ['Peter Xu', 'Sarah Lorenzana'], 'HKD')
cli.create_hotel_entry(charge_code, 'Hong Kong', '5/5/15', '5/8/15', '600', 150, tax1=50, currency='HKD')
cli.create_taxi_entry(charge_code, 'Hong Kong', '5/9/15', '12.34', 'Home', 'Client', currency='HKD')
cli.create_taxi_entry(charge_code, 'Hong Kong', '5/9/15', '24.68', 'Office', 'Home', 'Working late', currency='HKD')

# Special tricky transactions tests
print 'Testing special transactions'
print '1. Location disambiguation'
cli.create_meal1_entry(charge_code, 'Tokyo', '5/2/15', '1435', 'Breakfast', 'JPY')
print '2a. Itemized meals hotel'
cli.create_hotel_entry(charge_code, 'Hong Kong', '8/29/15', '9/6/15', '20043.10', '2475', currency='HKD', meals=[
    {'date': '9/2/15', 'type': 'Dinner', 'amount': '243.10'}
])
print '2b. Itemized meals hotel with wrong currency'
cli.create_hotel_entry(charge_code, 'Hong Kong', '9/1/15', '9/3/15', '550', '250', currency='USD', meals=[
    {'date': '9/2/15', 'type': 'Dinner', 'amount': '50'}
])
print '3. Wrong currency'
cli.create_meal1_entry(charge_code, 'Hong Kong', '5/2/15', '10.15', 'Breakfast', 'USD')
print '4. Creating a team celebration with a new name'
cli.create_meal3_entry(charge_code, 'San Francisco', '5/4/15', '23.45', 'Occasional Team Celebration', 'Dinner', 'Chipotle', ['Peter Xu', 'Random Name{0}'.format(random.randint(1, 10000))])

dir = os.path.dirname(os.path.realpath(__file__))

# Receipt
receipt_files = [os.path.join(dir, 'test', 'Lyft home-airport receipt.pdf')]

print 'Uploading receipts'
cli.upload_receipts(receipt_files)
