#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import datetime
from datetime import timedelta
import smtplib
from functools import cmp_to_key

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

smtp_port = 25
smtp_server = "mail.example.com"
sender_email = "timelog@example.com"
sender_pass = "secret"
recipients = [
    "me@example.com",
]

FILE_IN = "/home/jordi/.timelog/timelog.txt"

LINE_WIDTH = 80

# Month to report (YESTERDAY, CURRENT, PREVIOUS, LASTWEEK)
REPORT_MONTH = "PREVIOUS"

SINCE = None # datetime(2025,9,1)


def get_since():
    """Returns the since date
    """
    if SINCE:
        return SINCE

    now = datetime.now()
    if REPORT_MONTH == "YESTERDAY":
        today = datetime(now.year, now.month, now.day)
        yesterday = today - timedelta(days=1)
        return datetime(yesterday.year, yesterday.month, 1)

    if REPORT_MONTH == "CURRENT":
        return datetime(now.year, now.month, 1)

    if REPORT_MONTH == "PREVIOUS":
        prev = datetime(now.year, now.month, 1)
        prev = prev - timedelta(days=1)
        return datetime(prev.year, prev.month, 1)

    if REPORT_MONTH == "LASTWEEK":
        today = datetime(now.year, now.month, now.day)
        last_week = today - timedelta(days=7)
        return datetime(last_week.year, last_week.month, 1)

    return None


def get_until():
    since = get_since()
    tmp = datetime(since.year, since.month, 1)
    tmp = tmp + timedelta(days=32)
    tmp = datetime(tmp.year, tmp.month, 1)
    return tmp - timedelta(seconds=1)


def report_hours():
    start_from = None
    report = {}
    with open(FILE_IN, 'r') as reader:
        for line in reader:
            if not line:
                continue

            line = line.strip()
            if not is_task(line):
                continue

            if not start_from:
                start_from = get_datetime(line)

            project = get_project(line)
            if project:
                task_dt = get_datetime(line)
                seconds = get_diff_seconds(start_from, task_dt)
                if seconds > 0:
                    base_info = get_project_base_info()
                    proj_info = report.get(project, base_info)

                    # Task hours
                    task_detail = get_task_detail(line)
                    task_seconds = proj_info.get("tasks").get(task_detail, 0)
                    proj_info["tasks"].update({
                        task_detail: task_seconds + seconds,
                    })

                    # Accumulated hours
                    acumm = proj_info.get("seconds", 0)
                    proj_info.update({
                        "seconds": acumm + seconds,
                    })
                    report.update({project: proj_info})

                    hs = "{:.2f}".format(float(seconds/60/60))
                    print("{}: {}".format(line, hs))

            start_from = get_datetime(line)

    if report:
        send_report(report)


def get_project_base_info():
    return {
        "seconds": 0,
        "tasks": {}
    }


def get_diff_seconds(start_date, end_date):
    diff = (end_date - start_date)
    return diff.total_seconds()


def get_diff_hours(start_date, end_date):
    diff = end_date - start_date

    days, seconds = diff.days, diff.seconds
    hours = days * 24 + seconds // 3600
    minutes = (seconds % 3600) // 60
    return hours + (minutes/60)


def format_report(report):
    since = get_since()
    until = get_until()
    month_str = since.strftime("%y-%m (%B %Y)")
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    until_str = until.strftime("%Y-%m-%d %H:%M:%S")
    print("{} --> {}".format(since_str, until_str))
    output = []

    def sort_task(a, b):
        a = a.lower().strip()
        b = b.lower().strip()
        if a.startswith("-") and b.startswith("-"):
            return sort_task(a.strip("-"), b.strip("-"))
        elif a.startswith("-"):
            return -1
        elif b.startswith("-"):
            return 1
        return (a > b) - (a < b)



    total_seconds = 0
    projects = sorted(report.keys())
    for project in projects:
        proj_info = report[project]
        seconds = proj_info["seconds"]
        hours = float(seconds) / 60.0 / 60.0
        hours = "{:.2f}".format(hours)
        header = "{}".format(project).ljust(LINE_WIDTH)
        header = "{} hrs".format(header)
        output.append(header)
        tasks = proj_info.get("tasks")
        tasks_names = sorted(tasks.keys(), key=cmp_to_key(sort_task))
        #tasks_names = sorted(tasks.keys())
        for task_name in tasks_names:
            task_seconds = tasks.get(task_name)
            task_hours = float(task_seconds) / 60.0 / 60.0
            task_hours = "{:.2f}".format(task_hours)
            task_out = "  {}".format(task_name)[:LINE_WIDTH]
            task_out = task_out.ljust(LINE_WIDTH, ".")
            task_out = "{} {}".format(task_out, task_hours)
            output.append(task_out)

        total = "TOTAL".rjust(LINE_WIDTH)
        output.append("{} {}".format(total, hours))
        output.append("")
        output.append("")
        total_seconds += proj_info.get('seconds', 0)

    output.append("")

    total_hours = float(total_seconds) / 60.0 / 60.0
    total_hours = "{:.2f}".format(total_hours)
    report_out = [
        "Detall mensual d'hores {}".format(month_str),
        "Periode: {} - {}".format(since_str, until_str),
        "Total: {}h".format(total_hours),
        "",
    ]
    report_out.extend(output)
    return "\n".join(report_out)


def send_report(report):
    since = get_since()
    month_str = since.strftime("%y-%m (%B %Y)")
    text = format_report(report)
    subject = "Detall mensual d'hores {}".format(month_str)

    # Try to log in to server and send email
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.login(sender_email, sender_pass)  # user & password
        message = MIMEMultipart("related")
        message["Subject"] = subject
        message["From"] = sender_email
        message["To"] = ",".join(recipients)
        #message.preamble = 'This is a multi-part MIME message.'
        message.attach(MIMEText(text, 'plain'))
        # The msg['To'] needs to be a string
        # While recipients in sendmail needs to be a list
        server.sendmail(sender_email, recipients,  message.as_string())
    except Exception as e:
        # Print any error messages to stdout
        print(e)
    finally:
        server.quit()


def is_task(line):
    if not line:
        return False
    line = line.strip()
    if not line:
        return False
    if len(line) < 19:
        return False

    task_dt = get_datetime(line)
    if not task_dt:
        return False

    if task_dt < get_since():
        return False

    if task_dt > get_until():
        return False

    return True


def is_start(line):
    if not line or len(line) < 19:
        return False
    return line[18:].endswith("*")


def get_project(line):
    line = line[18:].split(":")
    if not line or len(line) < 2:
        return None
    project = line[0]
    if project.endswith("*"):
        return None
    return project


def get_task_detail(line):
    line = line[18:].split(":")
    if not line or len(line) < 2:
        return None
    return "".join(line[1:]).strip()


def get_datetime(line):
    try:
        return datetime.strptime(line[:16], "%Y-%m-%d %H:%M")
    except:
        return None


if __name__ == "__main__":

    report_hours()
