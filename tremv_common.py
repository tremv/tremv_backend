import os
import json
import datetime


def read_tremv_config(filename):
    config_file = open(filename, "r")
    result = json.loads(config_file.read())
    config_file.close()

    return(result)


def generate_output_path(date):
    return "tremv_output/" + str(date.year) + "/" + str(date.month) + "/"


""" Creates file name format: YYYY.MM.DD_[f1,f2].tremvlog from a given timestamp and filter.
    Date is a python datetime object and f is bandpass filter represented as a tuple of floats.
"""
def generate_tremvlog_filename(date, f):
    datestr = str(date.year) + "." + str(date.month) + "." + str(date.day)
    return(datestr + "_" + str(f[0]) + "," + str(f[1]) + ".tremvlog")


""" Parses an iso format date string to python datetime object.
"""
def parse_isoformat_to_datetime(date_str):
#NOTE:  We use this instead of datetime.datetime.fromisoformat since it is only support
#       for python version 3.7 and up.
    yy = int(date_str[0:4])
    mm = int(date_str[5:7])
    dd = int(date_str[8:10])

    h = int(date_str[11:13])
    m = int(date_str[14:16])
    s = int(date_str[17:19])

    return(datetime.datetime(year=yy, month=mm, day=dd, hour=h, minute=m, second=s))


""" Reads in a tremvlog file and returns a dictionary where the keys are the station names.
"""
def read_tremvlog_file(filename, station_names):
    result = {}

    for name in station_names:
        result[name] = []

    if(os.path.exists(filename)):
        input_file = open(filename, "r")
        lines = input_file.readlines()
        station_names_in_file = lines[0].split()

        prev_minute = 0

        for i in range(1, len(lines), 2):#step size is 2, because then we can process lines 2 at a time, because there is always a timestamp and then values
            timestamp = parse_isoformat_to_datetime(lines[i].rstrip())
            minute_of_day = timestamp.hour*60 + timestamp.minute

            #NOTE:-1 because we usually have a delta of 1, but we would like to input zeroes in place of the missing values
            minute_delta = minute_of_day - prev_minute - 1

            #fills in missing data
            for j in range(0, minute_delta):
                for name in station_names:
                    if(name in station_names_in_file):
                        result[name].append(0.0)

            values = lines[i+1].split()

            for j in range(0, len(values)):
                if(station_names_in_file[j] in station_names):
                    value = float(values[j])
                    result[station_names_in_file[j]].append(value)

            prev_minute = minute_of_day
        
        input_file.close()
    else:
        date = datetime.datetime.now()
        for name in station_names:
            for i in range(0, date.hour * 60 + date.minute):
                result[name].append(0.0)

    return(result)
