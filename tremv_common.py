import os
import json
import datetime


def read_tremv_config(filename):
    config_file = open(filename, "r")
    result = json.loads(config_file.read())
    config_file.close()

    return(result)


def logger_output_path(date):
    return "logger_output/" + str(date.year) + "/" + str(date.month) + "/"


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
def read_tremvlog_file(filename):
    result = {}

    if(os.path.exists(filename)):
        input_file = open(filename, "r")
        station_names_in_file = input_file.readline().split()

        for name in station_names_in_file:
            result[name] = []

        for line in input_file.readlines():
            values = line.split()

            for i in range(0, len(station_names_in_file)):
                name = station_names_in_file[i]
                result[name].append(float(values[i]))

    return(result)
