python setup.py py2exe
RMDIR ExpensesPlus /Q /S
MKDIR ExpensesPlus
MKDIR ExpensesPlus\dist
COPY dist ExpensesPlus\dist
COPY Expenses.xlsm ExpensesPlus
