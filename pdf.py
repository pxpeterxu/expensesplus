__author__ = 'Peter Xu'

from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams

import tempfile

def pdf_to_text(pdf_file):
    fp = open(pdf_file, 'rb')
    parser = PDFParser(fp)

    out_fp = tempfile.TemporaryFile('w+b')

    document = PDFDocument(parser)
    # Check if the document allows text extraction. If not, abort.
    if not document.is_extractable:
        raise Exception('PDF document cannot be extracted as Lyft receipt')
    # Create a PDF resource manager object that stores shared resources.
    rsrcmgr = PDFResourceManager()

    device = TextConverter(rsrcmgr, out_fp, codec='utf-8', laparams=LAParams())

    interpreter = PDFPageInterpreter(rsrcmgr, device)
    page_nos = set()
    for page in PDFPage.get_pages(fp, page_nos):
        interpreter.process_page(page)
    fp.close()
    device.close()

    out_fp.seek(0)
    data = out_fp.read()
    out_fp.close()

    return data.replace('\xc2\xa0', ' ')  # Strip &nbsp;
