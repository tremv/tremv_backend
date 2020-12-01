import os
import random
import time
import obspy
from obspy.clients.seedlink.basic_client import Client
from obspy import UTCDateTime
import tremv_common as common


""" Returns a list of station names from obspy trace object.
"""
def list_station_names(stations):
    result = []

    for trace in stations:
        result.append(trace.stats["station"])

    return(result)


""" Apply lowpass filter to the data and downsample it from 100 points per minute
    to 20 per minute.
"""
def process_station_data(stations):
    result = stations.copy()

    #This is done in order to avoid the phase shift in the decimation process
    result.filter('lowpass', freq=20.0, corners=2, zerophase=True)#this is super slow!
 
    #down sample from 100hz to 20hz (100/5 = 20), no filter to avoid phase shift
    for trace in result:
        trace.decimate(5, no_filter=True)
 
    result.detrend("demean")

    return(result)


""" Iterate through each filter, applys it to each trace and adds the filtered
    trace to a list corresponding to the filter that the iteration is on.
"""
def apply_bandpass_filters(traces, filters):
    passbands = [{} for i in filters]
 
    for i in range(0, len(filters)):
        f = filters[i]
 
        for trace in traces:
            t = trace.copy()
            t.filter("bandpass", freqmin=float(f[0]), freqmax=float(f[1]), corners=4, zerophase=True)
            passbands[i][t.stats["station"]] = t

    return(passbands)


""" Applies rsam to a single trace.
    NOTE: This function assumes the given trace is 1 minute worth of data.
"""
def trace_average(trace):
    value_sum = 0
    pts_per_minute = int(trace.stats.sampling_rate * 60)

    for point in trace.data:
        value_sum += abs(point)

    return(value_sum/pts_per_minute)


def rsam_processing(per_filter_filtered_stations, filters, station_names, received_station_names):
    result = [{} for i in filters]

    for i in range(0, len(filters)):
        for name in station_names:
            result[i][name] = 0.0

    #here we accumulate points
    for i in range(0, len(filters)):
        station_rsam_dict = result[i]
 
        for name in station_names:
            if(name in received_station_names):
                trace = per_filter_filtered_stations[i][name]
                average = trace_average(trace)
                station_rsam_dict[name] = average
            else:
                station_rsam_dict[name] = 0.0

    return(result)

#TODO: clean up this function a little bit perhaps?
""" Creates output files...
"""
def write_tremvlog_file(rsam_results, filters, station_names, timestamp):
    delimeter = " "
    path = common.logger_output_path(timestamp)

    if(os.path.exists(path) == False):
        os.makedirs(path)

    #TODO: rename i to filter index
    for i in range(0, len(filters)):
        filename = common.generate_tremvlog_filename(timestamp, filters[i])
        file_path = path + filename
        file_exists = os.path.exits(file_path)

        if(file_exists == False):
            f = open(file_path, "w")

            for j in range(0, len(station_names)):
                output.write(station_names[j])
                if(j == len(station_names)-1):
                    output.write("\n")
                else:
                    output.write(delimeter)

            minute_of_day = starttime.minute + starttime.hour * 60
            #Fill in empty values in the file if it isn't created at midnight.
            for j in range(0, minute_of_day-1):
                for k in range(0, len(station_names)):
                    output.write(str(0.0))
                    if(k == len(station_names)-1):
                        output.write("\n")
                    else:
                        output.write(delimeter)
            f.close()

        output = open(file_path, "r+")

        station_lists_differ = False
        station_names_in_file = output.readline().split()

        #figure out if there is difference between the station_names list we provide and the one in the file...
        for s in station_names:
            if(s not in station_names_in_file):
                station_list_diff = True
                break

        #Since they differ we will have to read the whole file in and re-write it:
        if(station_list_differ == True):
            data_in_file = common.read_tremvlog_file(file_path)
            minute_count = len(data_in_file[station_names_in_file[0]])

            #account for stations that are not present in the file and fill those with zeroes
            for j in range(0, len(station_names)):
                name = station_names[j]

                if(name not in station_names_in_file):
                    station_names_in_file.insert(j, name)
                    data_in_file[name] = []

                    for k in range(0, minute_count):
                        data_in_file[name].append(0.0)

            #clear the file
            output.seek(0)
            output.truncate()

            for j in range(0, len(station_names_in_file)):
                output.write(station_names_in_file[j])
                if(j == len(station_names)-1):
                    output.write("\n")
                else:
                    output.write(delimeter)

            for j in range(0, minute_count):
                for k in range(0, len(station_names_in_file)):
                    name = station_names_in_file[k]
                    output.write(data_in_file[name][j])

                    if(k == len(station_names_in_file)-1):
                        output.write("\n")
                    else:
                        output.write(delimeter)

        #do the actual appending of new data...
        #check file timestamp
        minutes_since_last_write = int(round((time.time() - os.path.getmtime(file_path)) / 60))

        #fill in missing data
        for j in range(0, minutes_since_last_write-1):
            for k in range(0, len(station_names_in_file)):
                output.write(str(0.0))
                if(k == len(station_names_in_file)-1):
                    output.write("\n")
                else:
                    output.write(delimeter)

        for j in range(0, len(station_names_in_file)):
            name = station_names_in_file[j]
            if(name in rsam_results):
                output.write(str(rsam_results[i][name]))
            else:
                output.write(str(0.0))

            if(j == len(station_names_in_file)-1):
                output.write("\n")
            else:
                output.write(delimeter)

        output.close()


""" Accumulate traces in a station that is found in a directory, handle gaps in
    data and append the output to a list of stations.
"""
def read_mseed_from_dir(path):
    stations = obspy.Stream()
    files = os.listdir(os.getcwd() + "/" + path)

    for f in files:
        station_in = obspy.read(path + "/" + f)
        trace_acc = station_in[0]

        #starts from one so we can splice the traces together with the + operator
        for i in range(1, len(station_in)):
            trace = station_in[i]
            trace_acc = trace_acc + trace

        #This creates a Stream object with one trace object that is gapless
        gapless_stream = trace_acc.split()
        stations.append(gapless_stream[0])

    return(stations)


""" Writes out preprocessed station data(without filtering) to a miniseed file for the given date.
"""
def write_to_mseed(stations, timestamp):
    path = common.logger_output_path(timestamp)

    if(os.path.exists(path) == False):
        os.makedirs(path)

    ts_str = str(timestamp)
    filedate = ts_str[0:4] + "." + ts_str[5:7] + "." + ts_str[8:10]
    filename = filedate + "_pp.mseed"
    file_path = path + filename

    if(os.path.exists(file_path)):
        stations_pp = obspy.read(file_path)

        #TODO: currently this doesn't work for some reason because of obspy...
        for s_pp in stations_pp:
            for s in stations:
                if(s_pp.stats["station"] == s.stats["station"]):
                    s_pp = s_pp + s

        stations_pp.write(file_path, format="MSEED")

    else:
        stations.write(file_path, format="MSEED")


""" Opens a file for debug purposes.
"""
#TODO: make sure we are using datetime of timestamps everywhere in this file for the common function calls
def open_debug_log(timestamp):
    path = common.logger_output_path(timestamp)

    if(os.path.exists(path) == False):
        os.makedirs(path)

    return open(common.logger_output_path(timestamp) + "debug.log", "a")


#NOTE: what if this is more like a library so people can customize the loop: for example if they want a 10min rsam instead?
def main():
    config_filename = "tremv_config.json"
    config = common.read_tremv_config(config_filename)
    config_stamp = os.stat(config_filename).st_mtime

    seedlink_connection = Client(config["server"], config["port"], 5, False)
    filters = config["filters"]

    SEC_TO_NANO = 1000*1000*1000
    min_in_ns = 60 * SEC_TO_NANO

    while(True):
        print("Sleeping until next minute.")
        #NOTE:  This makes it so the sleep time is the duration from now to the next minute.
        #       Thus calculations happen every minute, according to the system clock(assuming calculations take less than a minute).
        #       Would use time.time_ns() but it is only available in python 3.7 and up.
        sleeptime_in_sec = (min_in_ns - (int(time.time() * SEC_TO_NANO) % min_in_ns)) / SEC_TO_NANO
        time.sleep(sleeptime_in_sec)

        fetch_starttime = UTCDateTime()
        data_starttime = fetch_starttime - 60

        debug_log = open_debug_log(data_starttime)
        debug_log.write("Fetch start time: " + str(fetch_starttime))
        debug_log.write("Data fetch duration: ")

        #TODO:Maybe the station parameter(the one after "VI") could be longer than 3 chars???
        received_stations = seedlink_connection.get_waveforms(config["network"], "???", "??", "HHZ", data_starttime, fetch_starttime)

        debug_log.write(str(UTCDateTime() - fetch_starttime) + "\n")

        station_names = config["station_names"]
        rsam_st = UTCDateTime()

        #TODO:  Try to abstract this part because we could use it to spawn a process when we want to
        #       lazy fill data that isn't there. Then when a we get a request for data that hasn't been
        #       filtered yet with the requested filter, we can spawn it and then deliver the data
        #       when it is ready...
        received_station_names = list_station_names(received_stations)
        pre_processed_stations = process_station_data(received_stations)
        per_filter_filtered_stations = apply_bandpass_filters(pre_processed_stations, filters)

        rsam_results = rsam_processing(per_filter_filtered_stations, filters, station_names, received_station_names)

        debug_log.write("Rsam calculation duration: " + str(UTCDateTime() - rsam_st) + "\n")

        write_tremvlog_file(rsam_results, filters, station_names, data_starttime)
        #TODO: this is currently broken because of obspy or something :(
        write_to_mseed(pre_processed_stations, data_starttime)#Done so the pre processed data can be filtered with different filters at a later date.

        datestr = str(data_starttime.year) + "." + str(data_starttime.month) + "." + str(data_starttime.day)
        debug_log.write("Wrote to files " + datestr + " at: " + str(UTCDateTime()) + "\n")
        debug_log.write("\n")

        debug_log.close()

        #reload the config file if it has changed
        stamp = os.stat(config_filename).st_mtime

        if(stamp != config_stamp):
            config = common.read_tremv_config(config_filename)
            config_stamp = stamp


main()
