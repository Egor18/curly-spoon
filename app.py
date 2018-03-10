import sqlite3
import time
import datetime
import os
import sys
import shutil
import logging
import traceback
import smtplib
import email
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import checker
import config
from checker import Checker
from status import Status

#TODO: Limit to 50 attempts per email per day

class App:
    def __init__(self, server, port, user, password):
        self.solutions_dir = 'solutions'
        self.tasks_dir = 'tasks'
        self.temp_dir = 'temp'
        self.report_file = 'report.html'
        self.server = server
        self.port = port
        self.user = user
        self.password = password

    def get_available_tasks(self):
        return os.listdir(self.tasks_dir)

    def try_create_solutions_table(self, conn):
        cur = conn.cursor()
        cur.execute('''
        CREATE TABLE IF NOT EXISTS solutions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            datetime    INTEGER,
            email       TEXT,
            task        TEXT,
            language    TEXT,
            status      INTEGER
        )
        ''')
        conn.commit()
        res = cur.execute("SELECT count(*) FROM solutions")
        size = res.fetchone()[0]
        if size == 0:
            shutil.rmtree(self.solutions_dir)
            os.mkdir(self.solutions_dir)

    def try_create_report_file(self):
        if not os.path.exists(self.report_file):
            file = open(self.report_file, 'w')
            now = datetime.datetime.now()
            text = '''
            <html>
            <head>
            <style>
            table, th, td {{ border: 1px solid black; border-spacing: 1px; }}
            td, th {{ padding: 4px; }}
            </style>
            </head>
            <body>
            <h3>From {0} To [[NOW]]</h3>
            <h3>ACCEPTED SOLUTIONS:</h3>
            No new solutions
            <h3>REJECTED SOLUTIONS:</h3>
            No new solutions
            '''.format(now.strftime('%d-%m-%Y %H:%M'))
            file.write(text)
            file.close()

    #Quick and dirty solution
    def try_make_table(self, text, header):
        regex = '{0}\s*?No new solutions'.format(header)
        res = re.findall(regex, text, re.DOTALL)
        if not res:
            return text
        res = res[0]
        table = '''
        <table>
          <tr>
            <th>User</th>
            <th>Datetime</th>
            <th>Task</th>
            <th>Language</th>
            <th>Result</th>
          </tr>
        </table>
        '''
        replacement = res.replace('No new solutions', table)
        text = text.replace(res, replacement)
        return text

    def rreplace(self, s, old, new, occurrence):
        li = s.rsplit(old, occurrence)
        return new.join(li)

    def add_table_data(self, text, header, user, timestamp, task, language, result, result_color):
        regex = '{0}\s*?<table>.*?</table>'.format(header)
        res = re.findall(regex, text, re.DOTALL)[0]
        new_data = '''
        <tr>
          <td>{0}</td>
          <td>{1}</td>
          <td>{2}</td>
          <td>{3}</td>
          <td><font color="{5}">{4}</font></td>
        </tr>
        '''.format(user, timestamp, task, language, result, result_color)
        replacement = self.rreplace(res, '</tr>', '</tr>' + new_data, 1)
        text = text.replace(res, replacement)
        return text

    def add_solution_to_report(self, user, timestamp, task, language, result):
        file = open(self.report_file, 'r')
        text = file.read()
        file.close()
        if result == Status.OK:
            header = '<h3>ACCEPTED SOLUTIONS:</h3>'
            color = 'green'
        else:
            header = '<h3>REJECTED SOLUTIONS:</h3>'
            color = 'red'
        text = self.try_make_table(text, header)
        result_str = Status.get_string(result)
        timestamp = datetime.datetime.fromtimestamp(timestamp)
        datetime_str = timestamp.strftime('%d-%m-%Y %H:%M')
        language = '-' if not language else language
        task = '-' if not task else task
        text = self.add_table_data(text, header, user, datetime_str, task, language, result_str, color)
        file = open(self.report_file, 'w')
        file.write(text)
        file.close()

    def try_send_daily_report(self):
        report_time = datetime.datetime.strptime(config.REPORT_TIME, '%H:%M').time()
        regex = '<h3>From (.*?) To'
        file = open(self.report_file, 'r')
        text = file.read()
        file.close()
        res = re.findall(regex, text, re.DOTALL)[0]
        from_date = datetime.datetime.strptime(res, '%d-%m-%Y %H:%M').date()
        now = datetime.datetime.now()
        now_date = now.date()
        now_time = now.time()
        if now_time >= report_time and from_date < now_date:
            file = open(self.report_file, 'w')
            text = text.replace('[[NOW]]', now.strftime('%d-%m-%Y %H:%M'), 1)
            file.write(text)
            file.close()
            for admin in config.ADMINS:
                smtp = smtplib.SMTP_SSL(self.server, self.port)
                smtp.login(self.user, self.password)
                msg = MIMEMultipart('alternative')
                msg['Subject'] = 'Daily Report'
                part1 = MIMEBase('application', "octet-stream")
                part1.set_payload(open(self.report_file, "rb").read())
                encoders.encode_base64(part1)
                part1.add_header('Content-Disposition', 'attachment; filename="{0}"'.format(self.report_file))
                msg.attach(part1)
                smtp.sendmail(self.user, admin, msg.as_string())
                smtp.quit()
            os.remove(self.report_file)
            self.try_create_report_file()

    def send_response(self, receiver, task, language, solution_id, new_status, compiler_output, failed_test_num):
        smtp = smtplib.SMTP_SSL(self.server, self.port)
        smtp.login(self.user, self.password)
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'Result'
        message = ''
        if task:
            message += 'Task: {0}\n'.format(task)
        if language:
            message += 'Language: {0}\n'.format(language)
        message += 'Solution Id: {0}\n'.format(solution_id)
        message += '>>> Result: {0} <<<\n'.format(Status.get_string(new_status))
        if failed_test_num != -1 and new_status == Status.WRONG_ANSWER:
            message += 'Failed test: {0}\n'.format(failed_test_num)
        if compiler_output and new_status == Status.COMPILATION_ERROR:
            message += 'Compiler output:\n{0}'.format(compiler_output)
        part1 = MIMEText(message, 'plain', 'utf-8')
        msg.attach(part1)
        smtp.sendmail(self.user, receiver, msg.as_string())
        smtp.quit()
        
    def run(self):
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        self.try_create_solutions_table(conn)
        self.try_create_report_file()
        while True:
            compiler_output = ''
            failed_test_num = -1
            next_solution = cur.execute('SELECT * FROM solutions WHERE status = ? OR status = ? ORDER BY id LIMIT 1',
                                        (Status.WAITING, Status.INVALID_SOLUTION_FORMAT_WAITING)).fetchone()
            if next_solution != None:
                solution_id, datetime, email, task, language, status = next_solution
                logging.info('Got new solution: ' + str((solution_id, datetime, email,
                                                         task, language, Status.get_string(status))))
                if status == Status.INVALID_SOLUTION_FORMAT_WAITING:
                    new_status = Status.INVALID_SOLUTION_FORMAT_ERROR
                else:
                    solution_path = self.solutions_dir + '/' + str(solution_id)
                    task_path = self.tasks_dir + '/' + str(task)
                    solution_files = []
                    if os.path.exists(solution_path):
                        for f in os.listdir(solution_path):
                            if f.endswith(checker.EXTENSIONS[language]):
                                solution_files.append(f)
                    if language not in checker.RUN_COMMANDS or   \
                       task not in self.get_available_tasks() or \
                       not os.path.exists(solution_path) or      \
                       not solution_files:
                        new_status = Status.INVALID_SOLUTION_FORMAT_ERROR
                    else:
                        try:
                            c = Checker(language, solution_path, task_path, self.temp_dir)
                            new_status = c.check()
                            compiler_output = c.get_compiler_output()
                            failed_test_num = c.get_failed_test_num()
                        except Exception as e:
                            logging.warning('Internal error: ' + traceback.format_exc())
                            new_status = Status.INTERNAL_ERROR
                try:
                    cur.execute('UPDATE solutions SET status = ? WHERE id = ?',
                                (new_status, solution_id))
                    conn.commit()
                    try:
                        self.add_solution_to_report(email, datetime, task, language, new_status)
                    except:
                        logging.warning('Unable to update report.html: ' + traceback.format_exc())
                    self.send_response(email, task, language, solution_id, new_status, compiler_output, failed_test_num)
                    logging.info('Checked solution: ' + str((solution_id, datetime, email,
                                                             task, language, Status.get_string(new_status))))
                except:
                    logging.warning('Unable to send response: ' + traceback.format_exc())
            try:
                self.try_send_daily_report()
            except:
                logging.warning('Unable to send daily report: ' + traceback.format_exc())
            time.sleep(config.VERIFIER_UPDATE_PERIOD)

logging.basicConfig(filename='log.txt',
                    format='[%(asctime)s][%(levelname)s]: %(message)s',
                    datefmt='%d %b %Y %H:%M:%S',
                    level=logging.DEBUG)
logging.info('App started')
try:
    app = App(config.SMTP_SERVER, config.SMTP_PORT, config.LOGIN, config.PASSWORD)
    app.run()
except KeyboardInterrupt:
    sys.exit(0)
