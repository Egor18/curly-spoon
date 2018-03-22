import sqlite3
import imaplib
import email
import time
import re
import os
import sys
import logging
import traceback
import checker
import config
from status import Status

class Attachment:
    def __init__(self, filename, data):
        self.filename = filename
        self.data = data
    def __repr__(self):
        return str((self.filename, self.data))

class Message:
    def __init__(self, sender, datetime, task=None, language=None, attachments=None):
        self.sender = sender
        self.datetime = datetime
        self.task = task
        self.language = language
        self.attachments = attachments
    def __repr__(self):
        return str((self.sender, self.task, self.language, self.attachments))

class MailMonitor:
    def __init__(self, server, port, user, password):
        self.solutions_dir = 'solutions'
        self.tasks_dir = config.TASKS_DIR
        self.server = server
        self.port = port
        self.user = user
        self.password = password

    def get_available_tasks(self):
        return os.listdir(self.tasks_dir)

    def connect(self):
        conn = imaplib.IMAP4_SSL(self.server, self.port)
        conn.login(self.user, self.password)
        conn.select()
        return conn

    def find_value(self, text, value):
        regex = '{0}\s*?=\s*?([^<>\s]+)'.format(re.escape(value))
        res = re.findall(regex, text, re.DOTALL | re.IGNORECASE)
        if len(res) == 0:
            return None
        else:
            item = res[0]
            if item.endswith((',', '.', ';')):
                item = item[:-1]
            return item

    def get_message(self, conn, email_id):
        resp, data = conn.fetch(email_id, '(BODY.PEEK[])')
        email_body = data[0][1].decode('utf-8')
        message = email.message_from_string(email_body)
        sender = message['From'].split()[-1]
        sender = re.sub(r'[<>]', '', sender)
        try:
            datetime = email.utils.parsedate(message['Date'])
            datetime = int(time.mktime(datetime))
        except:
            datetime = 0
        task = None
        language = None
        attachments = []
        try:
            for part in message.walk():
                if part.get_content_maintype() == 'text' and part.get('Content-Disposition') is None:
                    text = part.get_payload(decode=True).decode('utf-8')
                    if task is None or language is None:
                        task = self.find_value(text, 'task')
                        language = self.find_value(text, 'language')
                        print('text:', text)
                        print('task:', task)
                        print('language:', language)
                elif part.get('Content-Disposition') is not None:
                    filename = None
                    data = None
                    header = email.header.decode_header(part.get_filename())
                    encoding = header[0][1]
                    filename = header[0][0]
                    if encoding is not None:
                        filename = filename.decode(encoding)
                    data = part.get_payload(decode=True)
                    attachments.append(Attachment(filename, data))
        except:
            return Message(sender, datetime, task, language, attachments)
        if task is None or language is None or not attachments:
            return Message(sender, datetime, task, language, attachments)
        language_ok = False
        for lang in checker.RUN_COMMANDS:
            if lang.lower() == language.lower():
                language_ok = True
                language = lang
        for attachment in attachments:
            if not attachment.filename.endswith(checker.EXTENSIONS[language]):
                attachments.remove(attachment)
        if task not in self.get_available_tasks() or \
           not language_ok or not attachments:
            return Message(sender, datetime, task, language, attachments)
        return Message(sender, datetime, task, language, attachments)

    def get_new_messages(self):
        messages = []
        conn = self.connect()
        res, email_ids = conn.search(None, 'UnSeen')
        if res == 'OK':
            email_ids = email_ids[0].split()
            for email_id in email_ids:
                try:
                    conn.store(email_id, '+FLAGS', '\\Seen')
                    messages.append(self.get_message(conn, email_id))
                except:
                    logging.warning('Failed to process message: ' + traceback.format_exc())
        return messages

    def apply_messages(self, messages):
        if not messages:
            return
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        for m in messages:
            if m.sender in config.BLACKLIST:
                logging.info('Message from blacklisted sender: {0}. Ignoring.'.format(m.sender))
                continue
            if not m.sender or not m.task and not m.language:
                #totally incorrect, don't send response
                status = Status.INVALID_SOLUTION_FORMAT_ERROR
                m.task = m.language = None
            elif not m.task or not m.language or not m.attachments:
                status = Status.INVALID_SOLUTION_FORMAT_WAITING
                m.task = m.language = None
            else:
                status = Status.COPYING
            cur.execute('INSERT INTO solutions (datetime, email, task, language, status) VALUES (?, ?, ?, ?, ?)',
                        (m.datetime, m.sender, m.task, m.language, status))
            conn.commit()
            if status == Status.COPYING:
                solution_id = cur.lastrowid
                solution_dir = self.solutions_dir + '/' + str(solution_id)
                os.mkdir(solution_dir)
                for attachment in m.attachments:
                    file = open(solution_dir + '/' + attachment.filename, 'wb')
                    file.write(attachment.data)
                    file.close()
                cur.execute('UPDATE solutions SET status = ? WHERE id = ?',
                            (Status.WAITING, solution_id))
                conn.commit()
        conn.close()

    def run(self):
        while True:
            try:
                messages = self.get_new_messages()
                self.apply_messages(messages)
            except:
                logging.warning('Failed to process new messages: ' + traceback.format_exc())
            time.sleep(config.MAILMON_UPDATE_PERIOD)

logging.basicConfig(filename='log.txt',
                    format='[%(asctime)s][%(levelname)s]: %(message)s',
                    datefmt='%d %b %Y %H:%M:%S',
                    level=logging.DEBUG)
logging.info('Mail Monitor started')
try:
    mailmon = MailMonitor(config.IMAP_SERVER, config.IMAP_PORT, config.LOGIN, config.PASSWORD)
    mailmon.run()
except KeyboardInterrupt:
    sys.exit(0)
