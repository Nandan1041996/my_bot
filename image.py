import io
import fitz  # PyMuPDF
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

def is_scanned_pdf(pdf_path):
    with fitz.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf, start=1):
            # Check for embedded text
            text = page.get_text()
            if text.strip():
                print('False')
                return False
    print('True')
    return True

def convert_pdf_to_text(pdf_path):
    # Set path to Tesseract executable if it's not in PATH
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
    poppler_path = r"D:\G01889\Documents\Downloads\Release-24.08.0-0\poppler-24.08.0\Library\bin"
    
    if is_scanned_pdf(pdf_path):
        # Extract images from PDF
        images = convert_from_path(pdf_path, dpi=300, poppler_path=poppler_path)
        # Initialize a variable to hold all extracted text
        all_text = ""
        # Perform OCR on each image
        for idx, image in enumerate(images):
            # Perform OCR on the current page
            ocr_text = pytesseract.image_to_string(image, lang='eng')
            all_text+=ocr_text + '\n'
    else:
        print("The PDF contains embedded text.")
        # open the file
        pdf_file = fitz.open(pdf_path)

        all_text = ""
        for page_index in range(len(pdf_file)):
            # get the page itself
            page = pdf_file.load_page(page_index)  # load the page
            # extract text 
            page_text = page.get_text()

            if page_text:
                all_text+= page_text +'\n'
        
            image_list = page.get_images(full=True)  # get images on the page

            if image_list:
                for image_index, img in enumerate(image_list, start=1):
                    # get the XREF of the image
                    xref = img[0]
                    # extract the image bytes
                    base_image = pdf_file.extract_image(xref)
                    image_bytes = base_image["image"]
                    imgs = Image.open(io.BytesIO(image_bytes))
                    image_str = pytesseract.image_to_string(imgs)
                    print('image_str::',image_str)
                    if len(image_str)!=0:
                        all_text+=image_str+ '\n'
    return all_text


# Specify your PDF file
# pdf_path = r"D:\G01889\Documents\Downloads\pdf_to_scan_676539eb027f6_temp_676539e9607c4.pdf"
pdf_path = r"D:\G01889\Documents\Downloads\img_txt.pdf"

        
text = convert_pdf_to_text(pdf_path)
print(text)
