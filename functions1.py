import textwrap
import gc
import re
import smtplib
import psycopg2
from deep_translator import GoogleTranslator
from langchain.chains.conversational_retrieval.base import ConversationalRetrievalChain
import io
import fitz  # PyMuPDF
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import os
import tempfile
from PyPDF2 import PdfReader
from langchain_core.messages import HumanMessage, AIMessage
# Define text wrapping function
def wrap_text_preserve_new_line(text, width=110):

    lines = text.split('\n')
    wrapped_lines = [textwrap.fill(line, width=width) for line in lines]
    wrapped_text = '\n'.join(wrapped_lines)

    del[lines,wrapped_lines]
    gc.collect()
    return wrapped_text 

def get_chain(llm,prompt,vector_index,chat_memory):

    chain = ConversationalRetrievalChain.from_llm(
                                                llm=llm, retriever=vector_index.as_retriever(),
                                                memory = chat_memory,
                                                return_source_documents=False,
                                                combine_docs_chain_kwargs={'prompt': prompt})
      
    del [llm,prompt,vector_index]
    gc.collect()
    return chain

# convert link if available in response
def convert_links_to_hyperlinks(text):
    response =  re.sub(
        r'(https?://\S+)',
        r'<a href="\1" target="_blank">\1</a>',
        text
    )
    return response

def is_scanned_pdf_from_memory(file_content):
    """Check if a PDF is scanned or not directly from in-memory content."""
    # Verify that file_content is binary
    if not isinstance(file_content, bytes):
        raise ValueError("file_content is not binary data.")

    # Use a BytesIO object to handle the binary content as a file-like object
    pdf_stream = io.BytesIO(file_content)

    # Open the PDF using PyMuPDF, specifying it as a PDF stream
    with fitz.open(stream=pdf_stream, filetype="pdf") as pdf:
        for page_num, page in enumerate(pdf, start=1):
            # Check for embedded text
            text = page.get_text()
            if text.strip():
                return False
            # Check for image objects
            image_list = page.get_images(full=True)
            if image_list:
                print(f"Page {page_num}: Images found.")
            else:
                print(f"Page {page_num}: No text or images found.")
    return True

## convert scanned pdf and text embedded pdf contained images into text:
def convert_pdf_to_text(file_content):
    # Set path to Tesseract executable if it's not in PATH
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
    poppler_path = r"D:\G01889\Documents\Downloads\Release-24.08.0-0\poppler-24.08.0\Library\bin"
    
    if is_scanned_pdf_from_memory(file_content):
        print("Processing as scanned PDF...")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
            temp_pdf.write(file_content)
            temp_pdf_path = temp_pdf.name
        
        try:
            images = convert_from_path(temp_pdf_path, dpi=300, poppler_path=poppler_path)
            all_text = ""
            for idx, image in enumerate(images):
                ocr_text = pytesseract.image_to_string(image, lang='eng')
                all_text += ocr_text + '\n'
            return all_text
        finally:
            os.remove(temp_pdf_path)
    else:
        print("The PDF contains embedded text.")
        # Assuming file_content is a byte object
        pdf_file = fitz.open(stream=file_content, filetype='pdf')
        all_text = ""
        for page_index in range(len(pdf_file)):
            page = pdf_file[page_index]
            # Extract text
            page_text = page.get_text()
            if page_text:
                all_text += page_text + '\n'
            
            # Extract images and OCR them
            image_list = page.get_images(full=True)
            if image_list:
                for img in image_list:
                    xref = img[0]
                    base_image = pdf_file.extract_image(xref)
                    image_bytes = base_image["image"]
                    imgs = Image.open(io.BytesIO(image_bytes))
                    image_str = pytesseract.image_to_string(imgs)
                    if image_str:
                        all_text += image_str + '\n'
    return all_text

def sql_connection():
    connection_string = 'postgres://postgres:postgres@localhost:5432/ChatBot'
    # connection_string = 'postgres://postgres:postgres@128.91.31.73:5432/chatbotdb'
    connection = psycopg2.connect(connection_string)

    curr = connection.cursor()
    return curr,connection

import json

# Convert chat_history to a serializable format (extracting content)
def convert_to_serializable_format(data):
    # Extract content from HumanMessage and AIMessage objects
    serialized_data = {
        'question': data['question'],
        'chat_history': [
            {'role': 'HumanMessage', 'content': message.content} if isinstance(message, HumanMessage)
            else {'role': 'AIMessage', 'content': message.content}
            for message in data['chat_history']
        ],
        'answer': data['answer']
    }
    return serialized_data

def get_answer(chain,query_text,email):
    ''' this function is used to retrive answer of given query_text

    Args:
    llm : Pretrained Model
    PROMPT : If query_text related question is not available in csv file then it return dont know
    vector_index : Used for faster search of sementic query_text from data
    query_text : Question

    Returns : Answer
    '''
    # insert if email id not present and update if email id present 
    sql_query = f"""select answer from  public.user_que_ans where email_id = '{email}';"""
    curr,conn = sql_connection()
    curr.execute(sql_query)
    res = curr.fetchall()
    conn.close()

    # when chat history 
    if len(res) !=0:
        chat_memory = {}
        messages = []
        chat_lst = json.loads(res[0][0])
        chat_memory = chat_lst[-1]
        # chat_keys = list(chat_lst[-1].keys())
        # chat_memory[chat_keys[0]] = chat_lst[-1][chat_keys[0]]

        # for i in range(len(chat_lst)):
        #     for i in chat_lst[i]['chat_history']:
        #         if i['role'] == 'HumanMessage':
        #             messages.append(HumanMessage(content=i['content']))
        #         elif i['role'] == 'AIMessage':
        #             messages.append(AIMessage(content=i['content']))

        # chat_memory[chat_keys[1]] = messages
        # chat_memory[chat_keys[-1]] = chat_lst[-1][chat_keys[-1]]
    else:
        # when chat history for user is not available 
        chat_memory = ''

    # answer_dict = chain.invoke({'question': query_text,'chat_history':memory})
    answer_dict = chain.invoke({'question': query_text,'chat_history':chat_memory})

    # to store chat in database 
    final_answer_dict = convert_to_serializable_format(answer_dict)
    # insert if email id not present and update if email id present 
    sql_query = f"""select answer from  public.user_que_ans where email_id = '{email}';"""
    curr,conn = sql_connection()
    curr.execute(sql_query)
    res = curr.fetchall()
    conn.close()
    if len(res) !=0:
        ans_lst = [final_answer_dict]
        # ans_lst = eval(res[0][0])
        # ans_lst.append(final_answer_dict)
        final_answer_json = json.dumps(ans_lst)
        # to excape the single quote , pgadmin gives error 
        final_answer_json_escaped = final_answer_json.replace("'", "''")

        sql_query = f"""update public.user_que_ans set answer = '{final_answer_json_escaped}'
                        where email_id = '{email}'
                    """
        curr,conn = sql_connection()
        curr.execute(sql_query)
        conn.commit()
        conn.close()
        del[final_answer_json]
        gc.collect()

    else:
        final_answer_json = json.dumps([final_answer_dict])
        # insert if email id not present and update if email id present 
        sql_query = f"""INSERT INTO public.user_que_ans (email_id, answer)
                            VALUES (%s, %s);
                        """
        curr,conn = sql_connection()
        curr.execute(sql_query, (email, final_answer_json))
        conn.commit()
        conn.close()

        del[sql_query, final_answer_json]
        gc.collect()

    res_dict = {'en':answer_dict['answer']}
    answer = answer_dict['answer']
    answer = convert_links_to_hyperlinks(answer)
     
    # To translate
    tgt_lang_lst = ['gu','hi','ta']
    for tgt_lang in tgt_lang_lst:
        translated = GoogleTranslator(source='en', target = tgt_lang).translate(answer)

        res =wrap_text_preserve_new_line(translated)
        res_dict[tgt_lang] = res

    del [chain,answer_dict,tgt_lang_lst,answer]
    gc.collect()
    return res_dict

def send_mail(receiver_email_id,message):
    try:
        sender_email_id = 'mayurnandanwar@ghcl.co.in'
        password = 'uvhr zbmk yeal ujhv'
        # creates SMTP session
        s = smtplib.SMTP('smtp.gmail.com', 587)
        # start TLS for security
        s.starttls()
        # Authentication
        s.login(sender_email_id, password)
        # message to be sent
        # sending the mail
        s.sendmail(sender_email_id, receiver_email_id, str(message))
        # terminating the session
        s.quit()
        return 0
    except:
        return ' The Message cannot be Sent.'
    
