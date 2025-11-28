#!/usr/bin/env python
# -*- coding: utf-8 -*-

import calendar
import configparser
import contextlib
import os
import re
import subprocess
import sys
import sys
import termios
import termios
import tty
from datetime import date
from datetime import datetime
from datetime import timedelta

import requests

# Load configuration from ini file
config = configparser.ConfigParser()
config_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "timelog.ini"
)

# Set defaults (will be used if no ini file exists)
default_log_file = os.path.join(
    os.path.expanduser("~"),
    ".timelog",
    "timelog.txt"
)
config["DEFAULT"] = {
    "log_file": default_log_file,
    "editor": "nano",
    "non_billable": "SEN,NAR",
    "price_hour": "170"
}

# Read the config file if it exists
if os.path.exists(config_path):
    try:
        config.read(config_path)
    except (configparser.Error, IOError) as e:
        print("Warning: Could not read config file: {}".format(e))
        print("Using default configuration")

# File where information is stored
LOG_FILE = os.path.expanduser(config.get("DEFAULT", "log_file"))
EDITOR = config.get("DEFAULT", "editor")

# Non-billable projects (comma-separated in config)
non_billable_str = config.get("DEFAULT", "non_billable")
NON_BILLABLE = [
    p.strip() for p in non_billable_str.split(",") if p.strip()
]

# Price per hour
PRICE_HOUR = config.getfloat("DEFAULT", "price_hour")

# Working hours range per day (minimum, optimal, excellent)
HOURS_DAY_RANGE = (4, 6, 8)

# Number of non-working days per week
FREE_DAYS_WEEK = 2

# Number of official non-working days per year (weekends excluded)
FREE_OFFICIAL_DAYS_YEAR = (
    (2025, 11),
)

# Number of non-working days per year (weekends excluded)
FREE_DAYS_YEAR = 22

# Expected productivity (billable vs worked hours)
PRODUCTIVITY = 0.7

# Constants
TAB = '\x09'
INTRO = '\x0a'
BACK = '\x7f'
EOT = '\x04'
CMD = "> "
DAY = "Day"
WEEK = "Week"
MONTH = "Month"
YEAR = "Year"

# Colors
# https://www.geeksforgeeks.org/print-colors-python-terminal/
RED = 91
GREEN = 92
YELLOW = 93
LIGHT_PURPLE = 94
PURPLE = 95
CYAN = 96
LIGHT_GRAY = 97
BLACK = 98

cached = {}
skip = False

@contextlib.contextmanager
def raw_mode(file):
    old_attrs = termios.tcgetattr(file.fileno())
    new_attrs = old_attrs[:]
    new_attrs[3] = new_attrs[3] & ~(termios.ECHO | termios.ICANON)
    try:
        termios.tcsetattr(file.fileno(), termios.TCSADRAIN, new_attrs)
        yield
    finally:
        termios.tcsetattr(file.fileno(), termios.TCSADRAIN, old_attrs)


def read_timelog():
    """Returns a list with all the tasks from the timelog file
    """
    output = []
    with open(LOG_FILE, "r") as reader:
        prev = None
        for line in reader:
            line = line.strip()
            if not line:
                continue
            if is_star(line):
                prev = line
            else:
                if prev:
                    output.append(prev)
                output.append(line)
                prev = None
    if prev:
        output.append(prev)
    return output


def get_quote():
    """
    {"_id":"rHScBNdsDKp","tags":["film"],"author":"Woody Allen",
    "content":"I took a speed reading course and read 'War and Peace' in twenty minutes. It involves Russia.","length":93}
    :return:
    """
    response = requests.get("https://api.quotable.io/random")
    res = response.json()
    return "{}\n.. {}".format(res.get("content"), res.get("author"))

def get_bar(value, max_value, size=15, left_bracket="", right_bracket="", fill_char="■", empty_char="□", header=""):
    completed = int(value * size / max_value)
    remaining = int(size - completed)
    percentage = float(value) * 100 / max_value
    if value < max_value * 0.25:
        color = LIGHT_GRAY
    elif value < max_value * 0.5:
        color = GREEN
    elif value < max_value * 0.75:
        color = YELLOW
    else:
        color = RED
    filled = colorize("{}".format(fill_char*completed), color)
    empty = colorize("{}".format(empty_char*remaining), LIGHT_GRAY)
    left = colorize(left_bracket, LIGHT_GRAY)
    right = colorize(right_bracket, LIGHT_GRAY)
    head = colorize(header, color)
    perc = colorize("{:.1f}%".format(percentage), LIGHT_GRAY)
    return "{}{}{}{}{} {}".format(head, left, filled, empty, right, perc)


def main():
    """Application entry-point
    """
    cached = {}
    skip = False

    # Timelog header
    now = datetime.now()
    week_idx = datetime.now().strftime("%W")
    work_days = get_working_days(now.year)
    year_days = get_year_days(now.year)
    day_of_year = datetime.now().timetuple().tm_yday

    out(colorize("[TIMELOG - W{} - {} wd/year]".format(int(week_idx), work_days), LIGHT_PURPLE))

    # BARS
    day_bar = get_bar(now.hour, 24, header="D:")
    days_month = calendar.monthrange(now.year, now.month)[1]
    month_bar = get_bar(now.day, days_month, header="M:")
    year_bar = get_bar(day_of_year, year_days, header="Y:")

    out("{} {} {}".format(day_bar, month_bar, year_bar))


    # Print last 7 tasks from timelog file
    #less(limit=7)

    # Print a nice quote?
    #print("\n"+colorize(get_quote(), LIGHT_GRAY))

    # Print summary
    show_summary()

    # Assume autocomplete
    out("")
    tasks = show_matches(term="", limit=10)

    # Prompt
    prompt()

    text = ""
    while True:
        key = wait_for_key()

        # Press 'q' without text
        if not text and is_quit(key):
            exit()

        # Press Enter without text
        if not text and is_intro(key):
            continue

        # Press Back without text
        if not text and is_back(key):
            continue

        # Press whitespace without text
        if not text and is_whitespace(key):
            continue

        # Press a number without text
        if not text and is_num(key):
            task = tasks.get(to_int(key))
            if task:
                write(get_task(task))
                prompt(newline=True)
                tasks = {}
            continue

        # Back key
        if text and is_back(key):
            text = text[:-1]
            out("\x1b[2K\r{}{}".format(CMD, text), newline=False)
            continue

        # Auto-complete
        if is_autocomplete(key):
            newline()
            if text:
                tasks = show_matches(term=text, limit=10)
            prompt()
            text = ""
            continue

        # Plain text
        if not is_intro(key):
            text = "{}{}".format(text, key)
            prompt(key)
            continue

        # ---------------------------------------------
        # ENTER PRESSED - HANDLE TEXT FROM HERE ONWARDS
        # ---------------------------------------------

        if is_quit(text):
            exit()

        elif is_list_tasks(text):
            less(limit=20)

        elif is_summary(text):
            show_summary()

        elif is_arrived(text):
            write("arrived**")

        elif is_edit(text):
            # Open editor and jump directly to last line
            subprocess.check_call([EDITOR, "+9999999", LOG_FILE])

        elif is_search(text):
            # Autocomplete
            newline()
            tasks = show_matches(term=text, limit=10)

        else:
            # store the task
            write(text)

        # flush the text and prompt again
        text = ""
        prompt(newline=True)


def prompt(val="> ", newline=False):
    """Writes the prompt to the stdout
    """
    if newline:
        sys.stdout.write("\n")
    # Print the prompt and flush immediately to ensure it shows up before input
    sys.stdout.write(val)
    sys.stdout.flush()


def wait_for_key():
    """Captures a single keypress without requiring the user to press Enter.
    Returns the character of the key pressed.
    """
    # Save the original terminal settings
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        # Switch the terminal to raw mode
        tty.setraw(fd)
        # Read a single character
        key = sys.stdin.read(1)
    finally:
        # Restore the original terminal settings
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return key

LIST_TASKS = ("l", "list")
AUTO_COMPLETE = ("\t", TAB, )

def is_quit(key):
    return key.lower() in [EOT, 'q', 'quit', 'exit']

def is_intro(key):
    return key.lower() in [INTRO, "\r", "\n"]

def is_back(key):
    return key.lower() in [BACK]

def is_autocomplete(key):
    return key.lower() in AUTO_COMPLETE

def is_whitespace(key):
    return key.lower() == " "

def is_list_tasks(text):
    return text.lower() in LIST_TASKS

def is_summary(text):
    return text in ["s", "summary"]

def is_arrived(text):
    return text in ["a*", "*"]

def is_edit(text):
    return text in ["e", "edit"]

def is_search(val):
    tokens = [":", "**"]
    return not any([t in val for t in tokens])

def write(task):
    pre = ""
    if task == "arrived**":
        pre = "\n"
        task = "{}".format(task)
    now = datetime.now()
    msg = "{}{}: {}\n".format(pre, now.strftime("%Y-%m-%d %H:%M"), task)
    with open(LOG_FILE, "a") as file1:
        file1.write(msg)

    out("\nTask added: {}".format(green(msg.strip())))

def cmd():
    out(CMD, newline=False)

def out(txt, newline=True):
    txt = newline and "{}\n".format(txt) or txt
    sys.stdout.write(txt)

def newline():
    out("")


def is_num(val):
    try:
        int(val)
        return True
    except:
        return False

def to_int(val, default=0):
    try:
        return int(val)
    except:
        return default

def get_since_date(period):
    now = datetime.now()
    today = datetime(now.year, now.month, now.day)
    if period == DAY:
        return today
    elif period == WEEK:
        return today - timedelta(days=today.weekday())
    elif period == MONTH:
        return datetime(today.year, today.month, 1)
    elif period == YEAR:
        return datetime(today.year, 1, 1)

def get_diff_seconds(start_date, end_date):
    diff = (end_date - start_date)
    return diff.total_seconds()

def show_summary():
    out(colorize("ALL::", PURPLE))
    period_summary(DAY)
    period_summary(WEEK)
    period_summary(MONTH)
    period_summary(YEAR)
    out(colorize("BILLABLE::", PURPLE))
    period_summary(DAY, billable_only=True)
    period_summary(WEEK, billable_only=True)
    period_summary(MONTH, billable_only=True)
    period_summary(YEAR, billable_only=True)

def period_summary(period=DAY, billable_only=False):
    total = 0
    since_start = get_since_date(period)
    since = since_start
    with open(LOG_FILE, "r") as reader:
        for line in reader:
            line = line.strip()
            if not line:
                continue

            task_date = get_task_date(line)
            if task_date < since:
                continue

            if is_star(line):
                since = task_date
                continue

            if not billable_only or is_billable(line):
                total += get_diff_seconds(since, task_date)

            since = task_date

    msg_period = period
    #if billable_only:
    #    msg_period = "{} (B)".format(period)

    hm = get_hm(total)
    if hm:
        msg = "{}: {}".format(msg_period, hm)
    else:
        msg = "{}: No work done yet".format(msg_period)

    avg = get_avg_hours_day(since_start, float(total) / 60 / 60)
    # Colouring
    # https://www.geeksforgeeks.org/print-colors-python-terminal/
    if not billable_only and period != DAY:
        msg = "{} [~{}h/wday]".format(msg, "{:.1f}".format(avg))
    elif billable_only:
        total_hours = total/60/60
        msg = "{} [~{} Eur]".format(msg, "{:,.0f}".format(total_hours*PRICE_HOUR))

    range = HOURS_DAY_RANGE
    if billable_only:
        range = [float(r)*PRODUCTIVITY for r in HOURS_DAY_RANGE]

    #suffix = period == DAY and "]" or "/wday]".format(msg)
    if avg < range[0]:
        msg = colorize(msg, RED)
    elif avg < range[1]:
        msg = colorize(msg, YELLOW)
    elif avg < range[2]:
        msg = colorize(msg, GREEN)
    else:
        msg = colorize(msg, CYAN)

    out(msg)

def get_avg_hours_day(since, worked_hours):
    if not worked_hours:
        return 0

    now = datetime.now()
    diff_days = (now - since).days + 1

    # Number of days current year
    days_year = get_year_days(now.year)

    # Number of days current month
    days_month = calendar.monthrange(now.year, now.month)[1]

    #out("{}\n".format(diff_days))
    if diff_days <= 1:
        # Per day
        pass

    elif diff_days <= 7:
        # Per week
        diff_days = 7 - FREE_DAYS_WEEK

    elif diff_days <= days_month:
        # Per month
        free_days = FREE_DAYS_WEEK * 4
        diff_days = days_month - free_days

    elif diff_days <= days_year:
        # Per year
        diff_days = get_working_days(now.year)

    #out("{} {}/{}\n".format(since.isoformat(), worked_hours, diff_days))
    return float(worked_hours)/diff_days

def get_hm(seconds):
    val = float(seconds)/60/60
    output = ["hours", "minutes"]
    values = [int(val), int((val-int(val))*60)]
    values = list(zip(output, values))
    values = [v for v in values if v[1] > 0]
    values = ["{} {}".format(v[1], v[0]) for v in values] or []
    return " ".join(values)


def to_task_info(raw_task, start_date):
    task = get_task(raw_task)
    task_end = get_task_date(raw_task)
    seconds = get_diff_seconds(start_date, task_end)
    project = task.split(":")[0].strip()
    return {
        "start": start_date,
        "end": task_end,
        "seconds": seconds,
        "task": get_task(task),
        "raw": raw_task,
        "project": project,
    }


def get_tasks(term=None, since=None, until=None, purge=False, limit=10, sort="ascending"):
    """Searches for tasks that match with the term passed-in
    """
    output = []
    matches = []

    # We reverse because in case of duplicates, we want to always display the
    # latest date of that task.
    for raw_task in reversed(read_timelog()):

        # Get the date of the task
        task_date = get_task_date(raw_task)

        # Do not include older tasks
        if since and task_date < since:
            # Since we are iterating reverse, all remaining tasks are older
            break

        # Do not include younger tasks
        if until and task_date > until:
            continue

        # Find a match for the term
        if term and term.lower() not in raw_task.lower():
            continue

        # Remove terms ending with ** and dups
        if purge:
            if is_star(raw_task):
                continue

            # Remove duplicates
            if get_task(raw_task) in matches:
                continue

        # Add the match
        output.append(raw_task)
        matches.append(get_task(raw_task))

        if 0 < limit == len(output):
            break

    if sort != "descending":
        output = list(reversed(output))

    return output


def show_matches(term, limit=10):
    """Displays a list in the stdout for selection
    """
    tasks = get_tasks(term=term, limit=limit, purge=True)

    # Cache them with an index
    cached = dict([(l[0], l[1]) for l in enumerate(tasks)])

    # Display matches in green
    colored = green(term)
    esc = re.compile(re.escape(term), re.IGNORECASE)
    tasks = [esc.sub(colored, get_task(l)) for l in tasks]
    tasks = ["{}: {}".format(yellow(l[0]), l[1]) for l in enumerate(tasks)]

    # Join the tasks
    tasks = "\n".join(tasks)
    if term:
        out(colorize("{} last matches for '{}':".format(limit, term), PURPLE))
    out(tasks)
    return cached


def less(limit=10):
    """Returns the last lines of the LOG FILE
    """
    # Get the tasks
    tasks = get_tasks(limit=limit)

    # Join the tasks
    tasks = "\n".join(tasks)
    out(tasks)


def colorize(val, color):
    return "\033[{}m{}\033[00m".format(color, val)

def green(val):
    return colorize(val, GREEN)

def yellow(val):
    return colorize(val, YELLOW)

def red(val):
    return colorize(val, RED)

def blue(val):
    return colorize(val, CYAN)

def is_star(line):
    """Returns whether this task is an **start** task
    """
    return line.strip().endswith("**")

def is_billable(line):
    """Returns whether this task is billable or not
    """
    if is_star(line):
        return False
    task = get_task(line).strip()
    task_project = task.split(":")
    if task_project[0].upper() in NON_BILLABLE:
        return False
    
    if task_project[1].strip().startswith("-"):
        return False

    return True

    #bill = map(lambda t: not task.startswith("{}:".format(t)), NON_BILLABLE)
    #return all(bill)


def get_task(line):
    """Returns the task without the Date part
    """
    task = line.strip()
    try:
        get_task_date(line)
        task = len(line) > 18 and line[18:] or None
    except Exception:
        # This is a cleaned task already
        pass
    return task


def get_task_date(line):
    """Returns the date part of the task
    """
    return datetime.strptime(line[:16], "%Y-%m-%d %H:%M")

def get_year_days(year):
    """Returns the number of days in the year
    """
    return 365 + calendar.isleap(year)


def get_working_days(year):
    """Returns the number of working days of the year
    """
    # Total de días del año: 2025 tiene 365 días, ya que no es bisiesto.
    # Días de fin de semana: Se restan los fines de semana (sábados y domingos).
    # Días festivos: Se eliminan los días festivos nacionales y los específicos de cada comunidad autónoma.

    # number of total days of the year
    days = get_year_days(year)

    # remove the weekends (saturdays and sundays)
    for num_day in range(FREE_DAYS_WEEK):
        days -= len(list(all_weekdays(year, weekday=6-num_day)))

    # remove the official free days (defaults to 12)
    days -= dict(FREE_OFFICIAL_DAYS_YEAR).get(year, 12)

    # remove the non-working days
    days -= FREE_DAYS_YEAR

    return days


def all_weekdays(year, weekday):
    """Return a list of dates for the given year and weekday, where Monday == 0 ... Sunday == 6
    """
    # Set dt to January 1st of the given year
    dt = date(year, 1, 1)
    # Move dt to the first Sunday of the given year
    dt += timedelta(days=weekday - dt.weekday())
    # Iterate through all Sundays of the given year
    while dt.year == year:
        # Yield the current date (dt) as a result
        yield dt
        # Move to the next Sunday by adding 7 days
        dt += timedelta(days=7)


if __name__ == "__main__":
    main()
