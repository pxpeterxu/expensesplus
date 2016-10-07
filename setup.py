__author__ = 'Peter Xu'

from distutils.core import setup
import py2exe

# Use by doing python setup.py py2exe

setup(console=['excel_expensesplus.py', 'excel_lyft.py', 'excel_uber.py'])
