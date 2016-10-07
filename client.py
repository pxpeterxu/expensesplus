__author__ = 'Peter Xu'

import requests
import re
import datetime
import time
import os
import string
import HTMLParser
import sys
import urllib

import urls
from codes import codes


class Client:
    def __init__(self, debug = False):
        self.session = requests.session()
        self.jsf_state = 0
        self.debug = debug
        self._location_cache = {} # Maps location strings to location codes
        self.last_resp = None  # Keep the last response for debugging
        self.prev_currency_code = self._translate_code('ALCurrencyFormat', 'USD') # Default currency for the
            # _annotate_fx function

        self._log_file = open('log_' + time.strftime('%Y-%m-%d %H%M%S') + '.txt', 'wb')

    @staticmethod
    def _get_numeric_code(code_type, code):
        try:
            code_num = int(code)
        except ValueError:
            code_num = codes[code_type][code]
        return code_num

    def _translate_code(self, code_type, code):
        """
        Check if code is a text code, and if it is, translate it; if it's already
        a number, just return it directly
        """
        return 'type:{0};id:{1};'.format(code_type, self._get_numeric_code(code_type, code))

    @staticmethod
    def _format_date(date):
        """
        Convert dates to the correct, needed string format
        """
        if isinstance(date, datetime.datetime):
            return date.strftime('%m/%d/%y')

        # Assume it's in an okay format otherwise
        return date


    def log(self, *args):
        for arg in args:
            print >> self._log_file, arg


    def _update_state(self, resp):
        # Get the jsf_tree_64 and jsf_state_64 variables to be used next
        match = re.search('jsf_tree_64" value="(\d+)', resp.text)
        orig_resp = resp

        if match is None:
            # Some pages return a window.location redirect
            match = re.search('window.location = "([^"]*)', resp.text)
            if match is not None:
                sso_url = match.group(1)
                resp = self.session.get(sso_url, verify=False)
                self.log('Opening SSO URL: ' + sso_url)

            # Some pages return a frame, and we need to get the contents of that frame to get the ER
            elif resp.text.find(urls.TAB_FRAME_PATH) != -1:
                resp = self.session.get(urls.TAB_FRAME, verify=False)
                self.log('Opening tab frame: ' + urls.TAB_FRAME)

                match = re.search('jsf_tree_64" value="(\d+)', resp.text)
                jsf_state = match.group(1)

                match2 = re.search('XM_FORM_TOKEN" value="([^"]+)', resp.text)
                xm_form_token = match2.group(1)

                match2 = re.search('XM_FORM_NAME" value="([^"]+)', resp.text)
                xm_form_name = match2.group(1)

                resp = self.session.post(urls.TAB_FRAME, {
                    'jsf_tree_64': jsf_state,
                    'jsf_state_64': jsf_state,
                    'XM_FORM_TOKEN': xm_form_token,
                    'XM_FORM_NAME': xm_form_name,
                    'jsf_viewid': "/suite/common/initial_tab_frame.jsp",
                    'startForm_SUBMIT': '1'
                }, verify=False)

        match = re.search('jsf_tree_64" value="(\d+)', resp.text)
        if match is None:
            raise Exception('Could not find jsf_tree_64 for response to {0} ({1}): {2}'.format(
                resp.url, orig_resp.url, resp.text))
        self.jsf_state = match.group(1)

        # Get the AJAX token
        match = re.search('XM_FORM_TOKEN" value="([^"]+)', resp.text)
        if match is None:
            raise Exception('Could not find XM_FORM_TOKEN for response to {0} ({1}): {2}'.format(
                resp.url, orig_resp.url, resp.text))
        self.xm_form_token = match.group(1)

        # Get the AJAX token
        match = re.search('XM_FORM_NAME" value="([^"]+)', resp.text)
        if match is None:
            raise Exception('Could not find XM_FORM_NAME for response to {0} ({1}): {2}'.format(
                resp.url, orig_resp.url, resp.text))
        self.xm_form_name = match.group(1)

    def _get(self, url, update_state = True, **kwargs):
        self.log('GET: ' + url)
        resp = self.session.get(url, verify=False, **kwargs)
        self.log('GET response: ' + resp.text)

        self.last_resp = resp

        if update_state:
            self._update_state(resp)

        return resp

    def _post(self, url, post_fields = None, update_state = True, **kwargs):
        if post_fields is None:
            post_fields = {}

        post_fields['jsf_tree_64'] = self.jsf_state
        post_fields['jsf_state_64'] = self.jsf_state

        if self.xm_form_token and self.xm_form_name:
            post_fields['XM_FORM_TOKEN'] = self.xm_form_token
            post_fields['XM_FORM_NAME'] = self.xm_form_name

        self.log('POST: ' + url)
        self.log('POST fields: ', post_fields)

        resp = self.session.post(url, post_fields, verify=False, **kwargs)
        self.last_resp = resp
        self.log('Response: ' + resp.text)

        if update_state:
            self._update_state(resp)

        return resp

    def login_expenses(self, username, tracking_num = None):
        s = self.session

        # Log in to expenses
        params = {
            'externalURL': '/ExtnWebApplication?documentType=100',
            'userLogin': username
        }
        if tracking_num is not None:
            params['trackingNum'] = tracking_num

        r = s.get(urls.ER_AUTHENTICATION, verify=False, params=params)

        # Do Javascript redirect manually
        match = re.search('window.location = "([^"]*)', r.text)
        if match is None:
            raise Exception('Could not log in to expense reporting')

        sso_url = match.group(1)
        resp = self._get(sso_url)

        return resp

    @staticmethod
    def _get_form_data(resp_text):
        """
        Given a page's HTML, get the form values and submit URL
        :param resp_text: page's HTML
        :return: tuple of (url, dict with form values)
        """
        h = HTMLParser.HTMLParser()

        # Get the submission URL
        match = re.search('action="([^"]+)', resp_text)
        url = h.unescape(match.group(1))

        # Get the form fields
        matches = re.findall('<input[^>]* name="([^"]+)"[^>]* value="([^"]+)', resp_text)
        form_fields = {match[0]: h.unescape(match[1]) for match in matches}

        return (url, form_fields)

    def login(self, username, password):
        # Submit analytics
        self.submit_analytics(username)

        s = self.session

        # SSO login
        r = s.get(urls.LOGIN, verify=False)

        if r.text.find('Access rights validated') == -1:
            raise Exception('Could not log in; please make sure you are logged in on McKinsey VPN')

        (url, form_fields) = self._get_form_data(r.text)

        # Re-request as POST
        r = s.post(url, form_fields, verify=False)

        # VPN login required since we don't have proxy pre-installed
        r = s.post(urls.VPN_LOGIN, {
            'username': username,
            'password': password,
            'vhost': 'standard'
        })

        match = re.search('input type="hidden" name="dummy" value="([^"]+)', r.text)
        if match is None:
            print >> sys.stderr, r.text
            raise Exception('Could not log in to proxy; make sure you\'re connected on McKinsey VPN and your password is correct')
        dummy = match.group(1)

        # Finish login by doing SSO again
        r = s.post(url, {
            'dummy': dummy
        }, verify=False)

        (url, form_fields) = self._get_form_data(r.text)
        r = s.post(url, form_fields, verify=False)

        # Final login to expenses tool with SSO password
        (url, form_fields) = self._get_form_data(r.text)
        r = s.post(urls.AUTHENTICATION, form_fields, verify=False)

        self.username = username

        # Log in to expenses
        self.login_expenses(username)

    def submit_analytics(self, username):
        s = self.session
        r = s.get(urls.ANALYTICS, params={'user': username})

    def open_expense_report(self, tracking_num):
        self.login_expenses(self.username, tracking_num)
        resp = self._post(urls.START_APP, {
            'jsf_viewid': '/app/document/startApp.jsp',
            'startForm:RealUserLoginInput': '',
            'startForm:copyDocInput': 'false',
            'startForm:DocNumInput': tracking_num,
            'startForm:HtmlAuditInput': 'false',
            'startForm:StartWithSpreadsheetImportInput': 'false',
            'startForm:QuickItemInput': 'false',
            'startForm:VoiceItemInput': 'false',
            'startForm:startBtn': 'StartApp',
            'startForm_SUBMIT': '1',
            'startForm:_link_hidden_': ''
        })

        if resp.text.find(tracking_num) == -1:
            raise Exception('Could not open ER step 1 ' + str(tracking_num) + ': ' + resp.text)

        first_jsf_state = self.jsf_state

        resp = self._post(urls.TAB_FRAME, {
            'jsf_viewid': '/suite/common/initial_tab_frame.jsp',
            'startForm_SUBMIT': '1',
            'autoScroll': '',
            'startForm:_link_hidden_': ''
        })

        if self.jsf_state <= first_jsf_state:
            # This should have incremented the jsf_state by 1
            raise Exception('Could not open ER step 2 '+ resp.text)

        return resp


    def close_expense_report(self, tracking_num, skip_open = False):
        if not skip_open:
            self.open_expense_report(tracking_num)

        # First load the prerequisite page
        resp = self._post(urls.CLOSE_EXPENSE_REPORT, {})

        # Actually close the expense report
        resp = self._post(urls.CLOSE_EXPENSE_REPORT, {
            'mainForm_SUBMIT': '1',
            'mainForm:_link_hidden_': 'mainForm:closeBtn2'
        }, False)

        # Check for correct response
        if resp.text.find('Closing window!') == -1:
            raise Exception('Error while closing expense report: ' + resp.text)

        return resp

    def create_expense_report(self, title):
        # Do the start form
        resp = self._post(urls.START_APP)
        if resp.status_code >= 400:
            raise Exception('Error while starting app: ' + resp.text)

        # Create expense report
        resp = self._post(urls.CREATE_ER, {
            'headerForm:title-PFAField': title,
            'headerForm:ADC_1210321500': '', # Charge code ID
            'headerForm:ADC_1210321500_input': '', # Charge code
            'headerForm_SUBMIT': '1',
            'headerForm:continueBtn2': 'Continue'
        })

        if resp.status_code >= 400:
            raise Exception('Error while starting app: ' + resp.text)

        # Return the ER code
        match = re.search('ER\d+', resp.text)
        if match is None:
            raise Exception('Error while getting Expense Report ID: ' + resp.text)

        return match.group(0)

    def delete_expense_report(self, er, skip_close=False):
        if not skip_close:
            self.close_expense_report(er)

        resp = self._get(urls.REAL_INDEX)

        # Get the form submission URL
        pattern = 'action="([^"]*)"'
        match = re.search(pattern, resp.text)

        if match is None:
            raise Exception('Unexpected HTML while getting list of reports; could not find form submission URL')
        form_submit_url = match.group(1)

        # Split it based on the tr
        split_text = re.split('<tr class="itemTable_Row\d">', resp.text)

        # Find the entry corresponding to our ER
        for text in split_text:
            if text.find(er) != -1:
                pattern = "(myDocumentsForm:workItemsListId_\d+:_id\d+)';" +\
                    "document.forms\['myDocumentsForm'\].elements\['trackingNo'\].value='([\d-]+)'"
                match = re.search(pattern, text)

                if match is None:
                    raise Exception('Unexpected HTML while getting list of reports: could not find trackingNo: ' +
                                    pattern + ' in ' + text)

                listId = match.group(1)
                trackingNo = match.group(2)

                resp = self._post(form_submit_url, {
                    'recallMessage': 'Are you sure you want to recall this document?',
                    'jsf_viewid': '/portal/inbox/mydocuments.jsp',
                    'myDocumentsForm_SUBMIT': '1',
                    'trackingNo': trackingNo,
                    'skipRequiredValidations': '',
                    'workitemId': '',
                    'navPath': '',
                    'myDocumentsForm:_link_hidden_': str(listId)
                })

                if resp.text.find('You cannot delete this document') != -1:
                    # Get the actual error message if possible
                    pattern = 'You cannot delete this document at this time.[^<]*'
                    match = re.search(pattern, resp.text)
                    if match is not None:
                        raise Exception('Could not delete document: ' + match.group(0))
                    else:
                        raise Exception('Could not delete document: ' + resp.text)

                return

        raise Exception('Could not find the report with code ' + str(er))


    def create_entry(self, expenseType):
        """
        Create an expense entry
        :param expenseType: string of the expense type (e.g. "Hotel", "Meals 1 - Travel Dining Alone")
        :rtype response
        """
        # Initial load of the page to set state
        self.log('Initial add expense page load')
        resp = self._post(urls.ADD_EXPENSE)

        self.log('Creating expense: ' + expenseType)
        resp = self._post(urls.ADD_EXPENSE, {
            'expenseTypeId': self._get_numeric_code('ExpenseType', expenseType),
            'mainForm_SUBMIT': '1',
            'mainForm:_link_hidden_': "mainForm:headerExpenseTypesList_3:headerExpenseTypeSelectLink"
        })

        if resp.status_code >= 400 or resp.text.find('Expense Item') == -1:
            raise Exception('Error while creating expense: ' + resp.text)

        return resp

    def confirm_line_warnings(self, resp):
        """
        Check if we have line warnings from submitting a request, and if it does,
        auto-accept it
        """
        if resp.text.find('lineViolationForm') != -1:
            new_resp = self._post(urls.SKIP_VIOLATION, {
                'lineViolationForm:continueBtn2': 'Continue',
                'lineViolationForm_SUBMIT': '1',
                'lineViolationForm:_link_hidden_': ''
            })
            return new_resp

        return resp


    suggestions_cache = {}

    def _get_suggestions(self, field, value):
        # Use the cache when possible
        if field in self.suggestions_cache and value in self.suggestions_cache[field]:
            return self.suggestions_cache[field][value]

        resp = self._post(urls.LOOKUP_CODE + '?affectedAjaxComponent=' + field,
                          {field: value}, False)
        matches = re.findall('id="[^"]*:([^:"]*)">([^<]*)</li>', resp.text)

        if field not in self.suggestions_cache:
            self.suggestions_cache[field] = {}

        if value not in self.suggestions_cache[field]:
            self.suggestions_cache[field][value] = matches

        return matches

    def _get_ajax_suggestions(self, field, value):
        # Use the cache when possible
        if field in self.suggestions_cache and value in self.suggestions_cache[field]:
            return self.suggestions_cache[field][value]

        resp = self._post(urls.LOOKUP_CODE, {
            'affectedAjaxComponent': field,
            'affectedAjaxComponentValue': value
        }, update_state=False)

        # Build the cache structures
        if field not in self.suggestions_cache:
            self.suggestions_cache[field] = {}

        results = resp.json()

        matches = []
        for result in results:
            code = result['value']
            label = urllib.unquote(result['label']).decode('utf8')

            if label != '':
                matches.append((code, label))

        self.suggestions_cache[field][value] = matches

        return matches


    def _get_location_suggestions(self, location):
        """
        Given a string for a location, returns the list of all matches and codes
        :param location: city name (e.g. "San Francisco")
        :return: [(code, locationName), (code2, locationName2), ...]
        :rtype: list
        """
        return self._get_ajax_suggestions('editItemForm:ADC_3048906', location)

    @staticmethod
    def _clarify(suggestions, strings, allow_none = False):
        """
        Prompt the user for clarification from a list of options
        :param suggestions: list of suggestions
        :return: the item in the list the user eventually selects
        """

        for i in xrange(len(suggestions)):
            print '[{0}] {1}'.format(i + 1, strings[i])

        if allow_none:
            print '[0] NONE of the above'

        confirmed = False
        selection = -1
        while not confirmed:
            while not ((selection >= 1 and selection <= len(suggestions)) or (allow_none and selection == 0)):
                try:
                    print 'Enter the number: '
                    selection = int(raw_input())
                except:
                    print 'That was not a number: please try again'

            selected_string = strings[selection - 1] if selection != 0 else 'None of the above'

            print 'You selected "{0}"; is that correct?'.format(selected_string)
            print '(Enter y for yes, n for no) '
            confirm = raw_input()

            if confirm == 'y':
                confirmed = True

        if selection >= 1:
            return suggestions[selection - 1]

        return None # allow_none is true

    def _get_location(self, location, prompt = True):
        """
        Get the code for a location, prompting the user to clarify if multiple
        options
        :param location: city name string
        :return: a tuple of the code and the name (e.g. (3001280, 'San Salvador/El Salvador'))
        """
        if location in self._location_cache:
            return self._location_cache[location]

        suggestions = self._get_location_suggestions(location)

        while len(suggestions) == 0:
            print 'We could not find a location starting with "' + location + '"; did you misspell it? Try another:'
            new_location = raw_input()
            suggestions = self._get_location_suggestions(location)

        if len(suggestions) == 1:
            # Single suggestion: just use it
            self._location_cache[location] = suggestions[0]
        else:
            # Multiple suggestions: clarify with user
            strings = [suggestion[1] for suggestion in suggestions]
            print 'Which of the above did you mean by "{0}"'.format(location) + '?'
            self._location_cache[location] = self._clarify(suggestions, strings)

        return self._location_cache[location]



    def _get_charge_code_suggestions(self, charge_code):
        return self._get_ajax_suggestions('editItemForm:allocation_panel:multipleAllocationTable_0:projectChoice',
                                     charge_code)

    def _get_charge_code(self, charge_code):
        charge_codes = self._get_charge_code_suggestions(charge_code)
        if len(charge_codes) == 0:
            raise Exception('"{0}" is not a valid charge code'.format(charge_code))

        return charge_codes[0]

    def _get_exchange_rate(self, date, amount, currency=None, currency_code=None):
        """
        Get the exchange rate and amount
        :param currency: currency of the payment (optional; either this or currency_code)
        :param currency_code: currency code of the payment (optional; this or currency)
        :param date: date of the payment
        :param amount: amount, in local currency, to convert
        :return: (amount_paid, exchange_rate)
        """
        if currency:
            currency_code = self._translate_code('ALCurrencyFormat', currency)

        resp = self._post(urls.AJAX_REQUEST, {
            'execute': 'editItemForm:currencyVal-PFAChoice editItemForm:date-PFAField editItemForm:amountVal-PFAField',
            'method': 'form.setFXRate',
            'render': 'editItemForm:paidAmountPanelGroup editItemForm:fxRatePanelGroup',
            'action': 'updateTarget',
            'componentId': 'editItemForm:currencyVal-PFAChoice',
            'editItemForm:currencyVal-PFAChoice': currency_code,
            'editItemForm:date-PFAField': date,
            'editItemForm:amountVal-PFAField': amount,
            'jsf_viewid': '/app/er_line.jsp'
        }, update_state=False)

        usd_code = self._translate_code('ALCurrencyFormat', 'USD')
        if currency_code == usd_code:
            # US$ is the default currency; it won't be present
            return amount, '1'

        match1 = re.search('editItemForm:paidAmountVal" type="text" value="([\d.]+)',
            resp.text)
        if match1 is None:
            raise Exception('Could not get amount / exchange rate for currency {0} on {1}:\n{2}'.format(
                currency_code, date, resp.text))

        amount_paid = match1.group(1)

        match2 = re.search('editItemForm:fxRateVal-PFAField" type="text" value="([\d.]+)',
            resp.text)
        if match2 is None:
            raise Exception('Could not get exchange rate for currency {0} on {1}:\n{2}'.format(
                currency_code, date, resp.text))
        exchange_rate = match2.group(1)

        return amount_paid, exchange_rate

    def _annotate_fx(self, post_request):
        """
        Annotate a POST request with the needed currency conversion codes
        :param post_request: post_request to annotate: we use the
            - editItemForm:date-PFAField
            - editItemForm:amountVal-PFAField
            - editItemForm:currencyVal-PFAChoice
            to build the actual request
        :return: None
        """
        currency_code = post_request['editItemForm:currencyVal-PFAChoice']
        amount = post_request['editItemForm:amountVal-PFAField']
        date = post_request['editItemForm:date-PFAField']
        usd_code = self._translate_code('ALCurrencyFormat', 'USD')

        if currency_code == usd_code and self.prev_currency_code == usd_code:
            # Even if we're using USD, if we're switching back from another currency, we HAVE to make the
            # _get_exchange_rate request
            post_request['editItemForm:fxRateVal-PFAField'] = '1'
            post_request['editItemForm:paidAmountVal'] = amount
            return post_request

        self.prev_currency_code = currency_code

        amount_paid, exchange_rate = self._get_exchange_rate(date, amount, currency_code=currency_code)
        post_request['editItemForm:fxRateVal-PFAField'] = exchange_rate
        post_request['editItemForm:paidAmountVal'] = amount_paid

        return post_request

    def create_hotel_entry(self, charge_code, location, check_in, check_out, total,
                           room_rate, tax1=None, tax2=None, tax3=None, tax4=None, tax5=None,
                           breakfast=None, parking=None, internet=None,
                           currency='USD', notes='', meals=None):
        if meals is None:
            meals = []  # Array of (date, meal, amount)

        self.create_entry('Hotel')

        check_in_str = self._format_date(check_in)
        check_out_str = self._format_date(check_out)
        currency_code = self._translate_code('ALCurrencyFormat', currency)
        (location_code, location_name) = self._get_location(location)
        (charge_code_code, charge_code) = self._get_charge_code(charge_code)

        # Go to the itemize page
        submit_post_request = {
            'editItemForm:date-PFAField': check_out_str,
            'editItemForm:amountVal-PFAField': total,
            'editItemForm:currencyVal-PFAChoice': currency_code,
            'editItemForm:ADC_3048906_input': location_name,
            'editItemForm:ADC_3048906': location_code,
            'editItemForm:receipt-PFAField': 'true',
            'editItemForm:allocation_panel:multipleAllocationTable_0:projectChoice_input': charge_code,
            'editItemForm:allocation_panel:multipleAllocationTable_0:projectChoice': charge_code_code,
            'editItemForm:ADC_-1999999888': 'type:SubExpenseType;id:-1999992755;', # Hotel for Firm Member
            'editItemForm:ADC_3048902': '',
            'editItemForm:note_panel:noteFld': notes,
            'editItemForm_SUBMIT': '1',
            'editItemForm:_link_hidden_': ''
        }
        submit_post_request = self._annotate_fx(submit_post_request)

        itemize_post = submit_post_request.copy()
        itemize_post['editItemForm:_link_hidden_'] = 'editItemForm:addItemizeBtn'

        resp = self._post(urls.SUBMIT_EXPENSE, itemize_post)
        resp = self.confirm_line_warnings(resp)

        if resp.text.find('Quick Itemize') == -1:
            raise Exception('Could not open the itemize screen for hotels: instead got response ' + resp.text)

        # Open the Quick Itemize page
        # resp = self._post(urls.LINE_ITEMIZE, {
        #     'editItemizationsForm:newExpenseTypeVal': '',
        #     'editItemizationsForm:quickItemizationBtn': 'Quick Itemize',
        #     'editItemizationsForm_SUBMIT': '1',
        #     'editItemizationsForm:_link_hidden_': 'editItemForm:addItemizeBtn'
        # })
        #
        # if resp.text.find('Daily Lodging Charges') == -1:
        #     raise Exception('Could not open the quick itemize screen: instead got response ' + resp.text)

        start = datetime.datetime.strptime(check_in_str, '%m/%d/%y')
        end = datetime.datetime.strptime(check_out_str, '%m/%d/%y')
        delta = end - start
        number_days = delta.days

        # Submit the itemizations
        resp = self._post(urls.QUICK_ITEMIZE_SUBMIT, {
            'editItemizationsForm:hotelQISubview:endDateVal': check_out_str,
            'editItemizationsForm:hotelQISubview:numberDaysVal': number_days,
            'editItemizationsForm:hotelQISubview:lodgingChargesGroup_46021': room_rate, # Taxes
            'editItemizationsForm:hotelQISubview:lodgingChargesGroup_46029': tax1 if tax1 else '',
            'editItemizationsForm:hotelQISubview:lodgingChargesGroup_46029_1': tax2 if tax2 else '',
            'editItemizationsForm:hotelQISubview:lodgingChargesGroup_46029_2': tax3 if tax3 else '',
            'editItemizationsForm:hotelQISubview:lodgingChargesGroup_46029_3': tax4 if tax4 else '',
            'editItemizationsForm:hotelQISubview:lodgingChargesGroup_46029_4': tax5 if tax5 else '',
            'editItemizationsForm:hotelQISubview:otherChargesGroup_-1999586252': breakfast if breakfast else '', # Breakfast
            'editItemizationsForm:hotelQISubview:otherChargesGroup_46025': parking if parking else '', # Parking / Toll / Other
            'editItemizationsForm:hotelQISubview:otherChargesGroup_-1999898515': internet if internet else '', # Internet - Wifi
            'editItemizationsForm:hotelQISubview:continue2Btn': 'Continue',
            'editItemizationsForm_SUBMIT': '1',
            'editItemizationsForm:_link_hidden_': ''
        })

        resp = self.confirm_line_warnings(resp)

        if resp.text.find('Finish Itemization') == -1 and resp.text.find('Save Itemization') == -1:
            raise Exception('Could not do quick itemize: instead got response ' + resp.text)

        # Itemize meals individually
        for meal in meals:
            resp = self._post(urls.LINE_ITEMIZE, {
                'editItemizationsForm:_link_hidden_': 'editItemizationsForm:expenseTypesList_2:expenseTypeSelectLink',
                'editItemizationsForm_SUBMIT': '1',
                'expenseTypeId': self._get_numeric_code('ExpenseType', 'Meals 1 - Travel Dining Alone')
            })

            if resp.text.find('Meal Type') == -1:
                raise Exception('Could not itemize meal as a part of a hotel bill: instead got response ' + resp.text)

            itemize_post_fields = {
                'editItemForm:date-PFAField': self._format_date(meal['date']),
                'editItemForm:amountVal-PFAField': meal['amount'],
                'editItemForm:ADC_-1999999878': self._translate_code('MealType', meal['type']),
                'editItemForm:allocation_panel:multipleAllocationTable_0:projectChoice_input': charge_code,
                'editItemForm:allocation_panel:multipleAllocationTable_0:projectChoice': charge_code_code,
                'editItemForm:note_panel:noteFld': '',
                'editItemForm:saveBtn2': 'Save',
                'editItemForm_SUBMIT': '1',
                'editItemForm:_link_hidden_': 'editItemForm:saveBtn'
            }
            resp = self._post(urls.LINE_ITEMIZE_SUBMIT, itemize_post_fields)
            resp = self.confirm_line_warnings(resp)

            if resp.text.find('Save Itemization') == -1 and resp.text.find('Finish Itemization') == -1:
                raise Exception('Could not itemize meal: instead got response ' + resp.text)

        # Close the itemization screen
        resp = self._post(urls.LINE_ITEMIZE, {
            'editItemizationsForm:saveBtn2': 'Save+Itemization',
            'editItemizationsForm_SUBMIT': '1',
            'editItemizationsForm:_link_hidden_': ''
        })

        if resp.text.find('Currency') == -1:
            raise Exception('Error while finishing itemization: ' + resp.text)

        # Do the final submissions
        submit_post = submit_post_request.copy()
        submit_post['editItemForm:_link_hidden_'] = 'editItemForm:saveBtn'

        resp = self._post(urls.SUBMIT_EXPENSE, submit_post)

        resp = self.confirm_line_warnings(resp)

        if resp.text.find('My Receipts') == -1:
            raise Exception('Error while submitting added hotel expense: ' + resp.text)

    def create_meal1_entry(self, charge_code, location, date, amount, meal, currency = 'USD', notes=''):
        self.create_entry('Meals 1 - Travel Dining Alone')

        date_str = self._format_date(date)
        currency_code = self._translate_code('ALCurrencyFormat', currency)
        (location_code, location_name) = self._get_location(location)
        (charge_code_code, charge_code) = self._get_charge_code(charge_code)
        meal_type = self._translate_code('MealType', meal)

        resp = self._post(urls.SUBMIT_EXPENSE, self._annotate_fx({
            'editItemForm:date-PFAField': date_str,
            'editItemForm:amountVal-PFAField': amount,
            'editItemForm:currencyVal-PFAChoice': currency_code,
            'editItemForm:ADC_-1999999878': meal_type,
            'editItemForm:ADC_3048906_input': location_name,
            'editItemForm:ADC_3048906': location_code,
            'editItemForm:receipt-PFAField': 'true',
            'editItemForm:allocation_panel:multipleAllocationTable_0:projectChoice_input': charge_code,
            'editItemForm:allocation_panel:multipleAllocationTable_0:projectChoice': charge_code_code,
            'editItemForm:ADC_3048902': '',
            'editItemForm:note_panel:noteFld': notes,
            'editItemForm_SUBMIT': '1',
            'editItemForm:_link_hidden_': 'editItemForm:saveBtn'
        }))

        resp = self.confirm_line_warnings(resp)

        if resp.text.find('My Receipts') == -1:
            raise Exception('Error while submitting added Meals 1 expense: ' + resp.text)

    def create_meal2_entry(self, charge_code, location, date, amount, nature, attendee_count,
                           currency='USD', notes=''):
        self.create_entry('Meals 2 - In Office')

        date_str = self._format_date(date)
        currency_code = self._translate_code('ALCurrencyFormat', currency)
        (location_code, location_name) = self._get_location(location)
        (charge_code_code, charge_code) = self._get_charge_code(charge_code)
        nature_and_relevance = self._translate_code('SubExpenseType2', nature)

        resp = self._post(urls.SUBMIT_EXPENSE, self._annotate_fx({
            'editItemForm:date-PFAField': date_str,
            'editItemForm:amountVal-PFAField': amount,
            'editItemForm:currencyVal-PFAChoice': currency_code,
            'editItemForm:ADC_1000080050': nature_and_relevance,
            'editItemForm:ADC_3048909': str(int(attendee_count)),
            'editItemForm:ADC_3048906_input': location_name,
            'editItemForm:ADC_3048906': location_code,
            'editItemForm:ADC_-1999999888': 'type:SubExpenseType;id:-1999992755;', # Meal for firm member
            'editItemForm:receipt-PFAField': 'true',
            'editItemForm:allocation_panel:multipleAllocationTable_0:projectChoice_input': charge_code,
            'editItemForm:allocation_panel:multipleAllocationTable_0:projectChoice': charge_code_code,
            'editItemForm:ADC_3048902': '', # Vendor
            'editItemForm:note_panel:noteFld': notes,
            'editItemForm_SUBMIT': '1',
            'editItemForm:_link_hidden_': 'editItemForm:saveBtn'
        }))

        resp = self.confirm_line_warnings(resp)

        if resp.text.find('My Receipts') == -1:
            raise Exception('Error while submitting added Meals 2 expense: ' + resp.text)

    @staticmethod
    def _get_existing_vendors(resp_text):
        """
        Get a dict of {'vendor': 'code'} based on the HTML on a certain page
        @param resp_text: HTML response for a page
        @return:
        """
        matches = re.findall('(type:Vendor;id:[^"]*)"(?: selected="selected")?>([^<]*)', resp_text)
        matches_dict = {vendor: id for id, vendor in matches}
        return matches_dict

    people_cache = {}

    def create_meal3_entry(self, charge_code, location, date, amount, nature, meal,
                           vendor, attendees, currency = 'USD', notes=''):
        """
        By far the most complex meal type: add a Team Dinner style meal
        """
        resp = self.create_entry('Meals 3 - Group Outside Office')
        existing_vendors = self._get_existing_vendors(resp.text)

        date_str = self._format_date(date)
        currency_code = self._translate_code('ALCurrencyFormat', currency)
        (location_code, location_name) = self._get_location(location)
        (charge_code_code, charge_code) = self._get_charge_code(charge_code)
        nature_and_relevance = self._translate_code('SubExpenseType3', nature)
        meal_type = self._translate_code('MealType', meal)

        # Final submission data
        post_data = {
            'editItemForm:date-PFAField': date_str,
            'editItemForm:amountVal-PFAField': amount,
            'editItemForm:currencyVal-PFAChoice': currency_code,
            'editItemForm:ADC_1000080051': nature_and_relevance,
            'editItemForm:ADC_-1999999878': meal_type,
            'editItemForm:ADC_3048902': '', # Vendor
            'editItemForm:ADC_3048906_input': location_name,
            'editItemForm:ADC_3048906': location_code,
            'editItemForm:receipt-PFAField': 'true',
            'editItemForm:allocation_panel:multipleAllocationTable_0:projectChoice_input': charge_code,
            'editItemForm:allocation_panel:multipleAllocationTable_0:projectChoice': charge_code_code,
            'editItemForm:note_panel:noteFld': notes,
            'editItemForm_SUBMIT': '1',
            'editItemForm:_link_hidden_': 'editItemForm:saveBtn'
        }
        post_data = self._annotate_fx(post_data)

        # Add the vendors, if needed
        if vendor not in existing_vendors:
            add_vendor_post_data = post_data.copy()
            add_vendor_post_data['editItemForm:_link_hidden_'] = 'editItemForm:ADC_3048902Btn'
            add_vendor_post_data['targetName'] = "form.currentERLineItem.extensions['vendorName']'"

            resp = self._post(urls.SUBMIT_EXPENSE, add_vendor_post_data)

            if resp.text.find('Add Vendor / Establishment') == -1:
                raise Exception('Could not open Add Vendor page; got error: ' + resp.text)

            resp = self._post(urls.ADD_VENDOR, {
                'addCorpDataScreenForm:addCorpDataVal': vendor,
                'addCorpDataScreenForm:saveBtn': 'Save',
                'addCorpDataScreenForm_SUBMIT': '1',
                'addCorpDataScreenForm:_link_hidden_': ''
            })

            existing_vendors = self._get_existing_vendors(resp.text)
            if vendor not in existing_vendors:
                raise Exception('Failed to add Vendor {0}; instead got: '.format(vendor) + resp.text)

        vendor_id = existing_vendors[vendor]
        post_data['editItemForm:ADC_3048902'] = vendor_id

        # Add the attendees
        # 1. Open up the screen
        add_attendee_post_data = post_data.copy()
        add_attendee_post_data['editItemForm:_link_hidden_'] = \
            'editItemForm:guest_wrapper_panel:guestQuickAddBtnChooserBtn'
        add_attendee_post_data['editItemForm:guest_wrapper_panel:addBtn'] = 'Add'

        resp = self._post(urls.SUBMIT_EXPENSE, add_attendee_post_data)
        if resp.text.find('Find Guests') == -1:
            raise Exception('Could not open Find Guests screen: ' + resp.text)

        # 2. Search for attendees
        guest_chooser_base = {
            'guestForm:guestChooserTabbedPane_indexSubmit': '',
            'guestForm:guest_chooser_search_tab:namesVal': '',
            'guestForm:guest_chooser_search_tab:guestType-PFAChoice': '',
            'guestForm:guest_chooser_search_tab:title-PFAField': '',
            'guestForm:guest_chooser_search_tab:company-PFAField': '',
            'guestForm:guest_chooser_search_tab:addressChoice': '',
            'guestForm:guest_chooser_search_tab:isPersonal-PFAChoice': '',
            'guestForm:guest_chooser_search_tab:guestListChoice': '',
            'guestForm:guest_chooser_recent_tab:recentRadio': 'true',
            'pagingEnabled': 'false',
            'guestForm_SUBMIT': '1'
        }

        search_guests = guest_chooser_base.copy()
        attendee_string = ';'.join(attendees)  # Search uses colon-separated attendees
        search_guests['guestForm:guest_chooser_search_tab:namesVal'] = attendee_string
        search_guests['guestForm:guest_chooser_search_tab:searchBtn'] = 'Search'
        resp = self._post(urls.GUEST_CHOOSER, search_guests)

        if resp.text.find('Guest Details') == -1:
            raise Exception('Couldn\'t successfully search for guests: ' + resp.text)

        # Extract the attendee data
        def extract_people(resp_text):
            """
            :rtype : list
            """
            html_parts = re.split('name="guestForm:guest_chooser_search_tab:_id[^:]*:searchSelectCheckbox', resp_text)
            del html_parts[0]

            def extract_info(html_part):
                """
                Extracts the ID, name, and position within McKinsey from the attendee search data
                :param html_part: HTML for the particular person's entry
                :return: a dict with all matching people's information
                """
                match = re.search('value="([^"]+)', html_part)
                id = match.group(1)
                match = re.search('col3143086Val">([^<]*)', html_part)
                first_name = match.group(1)
                match = re.search('col3143087Val">([^<]*)', html_part)
                last_name = match.group(1)
                match = re.search('col3143088Val">([^<]*)', html_part)
                company = match.group(1)

                pattern = 'guestForm:guest_chooser_search_tab:_id\d+_\d+:searchSelectCheckbox'
                match = re.search(pattern, html_part)
                checkbox_id = match.group(0)

                # Whether checkbox is checked; boxes for just-added people
                # are automatically checked
                checked = html_part.find('checked="checked"') != -1

                return {
                    'id': id,
                    'first_name': first_name,
                    'last_name': last_name,
                    'name': '{0} {1}'.format(first_name, last_name),
                    'company': company,
                    'checked': checked,
                    'checkbox_id': checkbox_id
                }

            return [extract_info(html) for html in html_parts]

        people = extract_people(resp.text)

        def key_by_name(people):
            """
            Convert the people from extract_text to be keyed by name, with
            multiple people with the same name under an array
            :param people: people from extract_people
            :return: dict { 'First Last': [person1, person2], ...}
            :rtype: dict
            """
            people_by_name = {}
            for person in people:
                name = person['name']
                if name not in people_by_name:
                    people_by_name[name] = []
                people_by_name[name].append(person)
            return people_by_name

        existing_attendees = re.findall('guestParentGuestsLabel\d+">([^<]+)', resp.text)

        # Remove all attendees who are auto-added (normally, only oneself)
        missing_attendees = [attendee for attendee in attendees if attendee not in existing_attendees]

        relevant_people = key_by_name(people)

        matched_people = [relevant_people[name][0] for name in missing_attendees if\
                          name in relevant_people and len(relevant_people[name]) == 1]
        missing_people = [name for name in missing_attendees if name not in relevant_people]
        ambiguous_people = [name for name in missing_attendees if\
                            name in relevant_people and len(relevant_people[name]) > 1]

        # Clarify the ambiguous people
        for name in ambiguous_people:
            print 'Which of the following do you mean by "{0}"?'.format(name)
            relevant = relevant_people[name]
            strings = ['{0} ({1} at {2})'.format(person['name'], person['position'], person['company']) for\
                       person in relevant]
            selected = self._clarify(relevant, strings, True)

            if selected is None:
                missing_people.append(name)
            else:
                matched_people.append(selected)

        # Add all matched people first
        def add_guests(people):
            """
            Add all the matched people by making server requests
            :param people: all the guests to add to the invitees list
            """
            add_guest = guest_chooser_base.copy()
            add_guest['guestForm:guest_chooser_search_tab:addBtn1'] = 'Add'
            for person in people:
                add_guest[person['checkbox_id']] = person['id']
            resp = self._post(urls.GUEST_CHOOSER, add_guest)

            missing_names = []
            for person in people:
                name = person['name']
                if resp.text.find(name) == -1:
                    missing_names.append(name)

            if missing_names:
                raise Exception('Failed to add guests {0}: '.format(', '.join(missing_names)) + '\n'
                                + resp.text)

        # Add everyone matched so far
        add_guests(matched_people)

        # Add the missing people
        for name in missing_people:
            print 'We need to add a new entry for "{0}"'.format(name)
            print 'Is {0} a McKinsey employee? ("y" for yes, anything else for no) '.format(name)
            is_internal_input = raw_input()
            is_internal = is_internal_input.upper() == 'Y'

            if is_internal:
                company = 'McKinsey'
            else:
                print 'What company does {0} work for? '.format(name)
                company = raw_input()

            new_guest = guest_chooser_base.copy()
            new_guest['guestForm:guest_chooser_search_tab:createBtn1'] = 'New'
            resp = self._post(urls.GUEST_CHOOSER, new_guest)

            if resp.text.find('New Guest') == -1:
                raise Exception('Could not open the "New Guest" screen: ' + resp.text)

            space_index = name.rfind(' ')
            first_name = name[0:space_index]
            last_name = name[space_index + 1:]

            resp = self._post(urls.GUEST_ENTRY, {
                'guestEntryForm:firstName-PFAField': first_name,
                'guestEntryForm:lastName-PFAField': last_name,
                'guestEntryForm:guestType-PFAChoice': '0' if is_internal else '1',
                'guestEntryForm:title-PFAField': '',
                'guestEntryForm:company-PFAField': company,
                'guestEntryForm:guestAddressesToggleState': 'true',
                'guestEntryForm:saveBtn': 'Save',
                'guestEntryForm_SUBMIT': '1',
                'guestEntryForm:_link_hidden_': ''
            })

            search_results = extract_people(resp.text)
            existing_attendees = re.findall('guestParentGuestsLabel\d+">([^<]+)', resp.text)

            if name not in existing_attendees:
                raise Exception('Could not add person "{0}": '.format(name) + resp.text)

        # Close the save dialog
        close_dialog = guest_chooser_base.copy()
        close_dialog['guestForm:saveBtn2'] = 'Save'

        resp = self._post(urls.GUEST_CHOOSER, close_dialog)
        if resp.text.find('date-PFAField') == -1:
            raise Exception('Failed to close add guests dialog: ' + resp.text)

        # Finally submit:
        resp = self._post(urls.SUBMIT_EXPENSE, self._annotate_fx(post_data))
        resp = self.confirm_line_warnings(resp)

        if resp.text.find('My Receipts') == -1:
            raise Exception('Error while submitting added Meals 3 expense: ' + resp.text)

    def create_taxi_entry(self, charge_code, location, date, amount, source, destination,
                          explanation=None, currency='USD', notes=''):
        self.create_entry('Taxi / Car Services')

        date_str = self._format_date(date)
        currency_code = self._translate_code('ALCurrencyFormat', currency)
        (location_code, location_name) = self._get_location(location)
        (charge_code_code, charge_code) = self._get_charge_code(charge_code)
        from_code = self._translate_code('FromTo', string.capwords(source))
        to_code = self._translate_code('FromTo', string.capwords(destination))

        resp = self._post(urls.SUBMIT_EXPENSE, self._annotate_fx({
            'editItemForm:date-PFAField': date_str,
            'editItemForm:amountVal-PFAField': amount,
            'editItemForm:currencyVal-PFAChoice': currency_code,
            'editItemForm:ADC_-1999888637': from_code,
            'editItemForm:ADC_-1999888627': to_code,
            'editItemForm:ADC_3048906_input': location_name,
            'editItemForm:ADC_3048906': location_code,
            'editItemForm:receipt-PFAField': 'true',
            'editItemForm:allocation_panel:multipleAllocationTable_0:projectChoice_input': charge_code,
            'editItemForm:allocation_panel:multipleAllocationTable_0:projectChoice': charge_code_code,
            'editItemForm:note_panel:noteFld': notes,
            'editItemForm_SUBMIT': '1',
            'editItemForm:_link_hidden_': 'editItemForm:saveBtn'
        }))

        if resp.text.find('Explanation') != -1:
            # We need an explanation for Home <-> Office or Other <-> x
            if explanation is None:
                # Reverse lookup
                from_numeric = self._get_numeric_code('FromTo', source)
                to_numeric = self._get_numeric_code('FromTo', destination)
                from_text = [location for location, code in codes["FromTo"].iteritems() if
                             code == from_numeric][0]
                to_text = [location for location, code in codes["FromTo"].iteritems() if
                           code == to_numeric][0]

                print 'An explanation is needed for travel from {0} to {1}'.format(from_text, to_text)
                print 'Enter the explanation: '
                explanation = raw_input()

            resp = self._post(urls.SKIP_VIOLATION, {
                'lineViolationForm:explanationVal': explanation,
                'lineViolationForm:continueBtn2': 'Continue',
                'lineViolationForm_SUBMIT': '1',
                'lineViolationForm:_link_hidden_': ''
            })

        resp = self.confirm_line_warnings(resp)

        if resp.text.find('My Receipts') == -1:
            raise Exception('Error while submitting Taxi / Car Services expense: ' + resp.text)
        pass

    def _upload_receipts(self, files):
        """
        Internal uploads receipt implementation, which only takes up to 10 files
        at a time
        """

        # Initialize

        self.log('Initial add expense page load')
        resp = self._post(urls.ADD_EXPENSE)

        self.log('Opening up expenses page')
        resp = self._post(urls.ADD_EXPENSE, {
            'mainForm_SUBMIT': '1',
            'mainForm:_link_hidden_': 'mainForm:documentReceiptsTabBtn'
        })
        if resp.text.find('Attached Receipts') == -1:
            raise Exception('Error while opening up receipts tab: ' + resp.text)

        resp = self._get(urls.UPLOAD_RECEIPTS)
        if resp.text.find('The following file types are supported') == -1:
            raise Exception('Error while opening receipts page: ' + resp.text)

        post_fields = {
            'receiptDocForm:uploadDocReceiptBtn': 'Attach',
            'receiptDocForm_SUBMIT': '1',
            'receiptDocForm:attachedFlag': 'false',
            'receiptDocForm:attachLevelFlag': '',
            'receiptDocForm:_link_hidden_': ''
        }

        file_fields = {'receiptDocForm:uploadedFile{0}'.format(i + 1):
                           (os.path.basename(files[i]), open(files[i], 'rb'))
                       for i in xrange(len(files))}

        resp = self._post(urls.UPLOAD_RECEIPTS, post_fields=post_fields, files=file_fields)

        if resp.text.find('inlineerror') != -1:
            # print resp.text
            raise Exception('Got error while upload receipts: ' + resp.text)

        elif resp.text.find('name="receiptDocForm:attachedFlag" value="true"') == -1:
            raise Exception('Receipt upload didn\'t seem to register: ' + resp.text)



    def upload_receipts(self, files):
        """
        Upload a number of receipts, and raise an exception if any of them failed
        """
        errors = []

        for i in xrange(0, len(files), 10):
            sub_files = files[i:i+10]

            try:
                self._upload_receipts(sub_files)
            except Exception as e:
                errors.append(e.message)

        if errors:
            raise Exception('Some receipts may not have been uploaded')
