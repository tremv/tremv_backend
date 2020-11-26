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


""" Creates output files...
"""
def write_tremvlog_file(rsam_results, filters, station_names, starttime):
    print("writing to file...")
    starttime_datetime = starttime.datetime
    path = common.generate_output_path(starttime_datetime)

    if(os.path.exists(path) == False):
        os.makedirs(path)

    for i in range(0, len(filters)):
        filename = common.generate_tremvlog_filename(starttime_datetime, filters[i])
        file_path = path + filename
        file_exists = os.path.exists(file_path)

        output = open(file_path, "a")
 
        if(file_exists):
            output.write("\n" + starttime_datetime.isoformat() + "\n")
 
            for name in station_names:
                output.write(str(rsam_results[i][name])+" ")
        else:
            for name in station_names:
                output.write(str(name)+" ")
 
            output.write("\n"+ starttime_datetime.isoformat() +"\n")

            for name in station_names:
                output.write(str(rsam_results[i][name])+" ")
 
        output.close()
    print("wrote to tremvlog!")
    print()


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


#TODO: this might not be complete?
def write_to_mseed(stations, timestamp):
    path = common.generate_output_path(timestamp)

    if(os.path.exists(path) == False):
        os.makedirs(path)

    ts_str = str(timestamp)
    filedate = ts_str[0:4] + "." + ts_str[5:7] + "." + ts_str[8:10]
    filename = filedate + "_pp.mseed"
    file_path = path + filename

    if(os.path.exists(file_path)):
        stations_pp = obspy.read(file_path)

        for s_pp in stations_pp:
            for s in stations:
                if(s_pp.stats["station"] == s.stats["station"]):
                    s_pp = s_pp + s

        stations_pp.write(file_path, format="MSEED")

    else:
        stations.write(file_path, format="MSEED")


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

        starttime = UTCDateTime()
        print("Fetching data...")
        #TODO:Maybe the station parameter(the one after "VI") could be longer than 3 chars???
        received_stations = seedlink_connection.get_waveforms(config["network"], "???", "??", "HHZ", starttime - 60, starttime)
        print("Fetch duration: " + str(UTCDateTime() - starttime))
        print()

        station_names = config["station_names"]

        rsam_st = UTCDateTime()

        received_station_names = list_station_names(received_stations)
        pre_processed_stations = process_station_data(received_stations)
        per_filter_filtered_stations = apply_bandpass_filters(pre_processed_stations, filters)

        rsam_results = rsam_processing(per_filter_filtered_stations, filters, station_names, received_station_names)

        write_tremvlog_file(rsam_results, filters, station_names, starttime)
        write_to_mseed(pre_processed_stations, starttime)#Done so the pre processed date can be filtered with different filters at a later date.

        print("Rsam calculation duration: " + str(UTCDateTime() - rsam_st))
        print("Total duration: " + str(UTCDateTime() - starttime))
        print()

        #reload the config file if it has changed
        stamp = os.stat(config_filename).st_mtime

        if(stamp != config_stamp):
            config = common.read_tremv_config(config_filename)
            config_stamp = stamp

main()
