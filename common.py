#Authors:
#Bethany Erin Vanderhoof
#Þórður Ágúst Karlsson

import os
import sys
import json
import datetime
import logging

# er að athuga smá

#a wrapper around the json config
class config:
    def __init__(self, filename):
        self.filename = filename
        self.stamp = 0
        self.config = None
        self._read()

    def __getitem__(self, key):
        return self.config[key]

    def _read(self):
        try:
            config_file = open(self.filename, "r")
            self.config = json.loads(config_file.read())
            config_file.close()
        except Exception as e:
            logging.error(e)
            sys.exit(1)


    def reload(self):
        stamp = os.stat(self.filename).st_mtime

        if(stamp != self.stamp):
            self._read()
            self.stamp = stamp

"""
input: 
data: obspy Stream
inv: obspy Inventory

output:
response corrected(not fully...) copy of the data
"""
def stream_counts_to_um(data, inv):
    import obspy
    result = data.copy()

    for trace in result:
        name = trace.stats.station
        seed_identifier = trace.stats.network + "." + name + ".." + "HHZ"
        response = self.response_inventory.get_response(seed_identifier, fetch_starttime)
        counts_to_um = response.instrument_sensitivity.value / 1000000
        trace.data /= counts_to_um

    return result


def logger_output_path(date):
    return "logger_output/" + str(date.year) + "/" + str(date.month) + "/"


""" Creates file name format: YYYY.MM.DD_[f1,f2].csv from a given timestamp and filter.
    Date is a python datetime object and f is bandpass filter represented as a tuple of floats.
"""
def generate_tremvlog_filename(date, f, component):
    datestr = str(date.year) + "." + str(date.month) + "." + str(date.day)
    return(datestr + "_" + str(f[0]) + "," + str(f[1]) + "_" + str(component) + ".csv")


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


""" Reads in a csv file and returns a dictionary where the keys are the station names.
"""
def read_tremvlog_file(filename,delim):
    result = {}

    if(os.path.exists(filename)):
        input_file = open(filename, "r")
        station_names_in_file = input_file.readline().split(delim)
        station_names_in_file = station_names_in_file[1:] # remove "TIMESTAMP" at position 0

        # removes \n line jump from last station in file and any other erroneous white space
        for i in range(0, len(station_names_in_file)):
            station_names_in_file[i] = station_names_in_file[i].rstrip()

        for name in station_names_in_file:
            result[name] = []

        for line in input_file.readlines():
            values = line.split(delim)

            for i in range(0, len(station_names_in_file)):
                name = station_names_in_file[i]
                # i+1 to ignore timestamp (otherwise error cannot convert strng (timestamp) to float)
                result[name].append(float(values[i+1]))

    #result = dictionary of RSAM results up to current minute for all stations in file
    return(result)


""" Reads csv file and returns list of timestamps.
"""
def read_tremvlog_timestamps(filename,delim):
    timestamp_list = []

    if(os.path.exists(filename)):
        input_file = open(filename, "r")

        for line in input_file.readlines():
            values = line.split(delim)
            timestamp_list.append(values[0])

        timestamp_list.pop(0) # Remove "TIMESTAMP" from position 0, first line
        input_file.close()

    return(timestamp_list)


""" Reads csv file and returns list of station names in file.
"""
def read_tremvlog_stations(filename,delim):

    if(os.path.exists(filename)):
        input_file = open(filename, "r")

        stations = input_file.readline().split(delim)
        stations = stations[1:]  # Remove "TIMESTAMP" text at position 0

        for i in range(0, len(stations)):
            stations[i] = stations[i].rstrip()

        input_file.close()

        return(stations)
