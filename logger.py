#Authors:
#Bethany Erin Vanderhoof
#Þórður Ágúst Karlsson

import os
import sys
import time
import schedule
# import netCDF4 as netcdf # unused import statement
import obspy
from obspy.clients.seedlink.basic_client import Client as seedlinkClient
from obspy.clients.fdsn import Client as fdsnClient
from obspy import UTCDateTime
import common
import config
import alert


""" Prints debugging info to stderr
"""
def debug_print(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)
    #print(*args, file=sys.stdout, **kwargs)


""" Apply lowpass filter to the data and downsample it from 100 points per minute
    to 20 per minute.
"""
def process_station_data(stations):
    result = stations.copy()

    #This is done in order to avoid the phase shift in the decimation process
    #It is only 10hz because otherwise we run in to aliasing, since we decimate after(nyquist-shannon theorem)
    result.filter("lowpass", freq=10.0, corners=2, zerophase=True)# this is super slow!
 
    #Down sample from 100hz to 20hz (100/5 = 20), no filter to avoid phase shift
    for trace in result:
        trace.decimate(5, no_filter=True)
 
    result.detrend("demean")

    return(result)


""" Iterate through each filter, applies it to each trace and adds the filtered
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
    pts_per_minute = int(trace.stats.sampling_rate * 60)

    return(sum(abs(trace.data))/pts_per_minute)


""" Averages values for a given station over a minute and prepares the averages as
    an array of dictionaries whose length is equal to the number of filters provided.
    Each dictionary uses station names as keys and the corresponding average is the value.
"""
def rsam_processing(per_filter_filtered_stations, filters, station_names):
    result = [{} for i in filters]

    for i in range(0, len(filters)):
        for name in station_names:
            filtered_stations = per_filter_filtered_stations[i]
            rsam_stations_dict = result[i]

            rsam_stations_dict[name] = 0.0

            if(name in filtered_stations):
                trace = filtered_stations[name]
                average = trace_average(trace)
                rsam_stations_dict[name] = average

    return(result)


""" Determines channel -- z, n, or e -- for which RSAM data is being written.
"""
def determine_channel(selector):

    char_to_check = ["z", "n", "e"]
    for char in char_to_check:
        if(char in selector.lower()):
            return(char)
        break


""" Creates output files... (one per specified bandpass filter)
"""
def write_tremvlog_file(rsam_results, filters, station_names, timestamp, channel):
    delimeter = ","
    path = common.logger_output_path(timestamp)

    if (os.path.exists(path) == False):
        os.makedirs(path)

    for filter_index in range(0, len(filters)):
        filename = common.generate_tremvlog_filename(timestamp, filters[filter_index], channel)
        file_path = path + filename
        file_exists = os.path.exists(file_path)

        # creates file for current filter and day if nonexistent
        station_names.sort()  # sorts station names alphabetically
        if (file_exists == False):
            create_tremvlog_file(file_path, delimeter, timestamp, station_names)

        station_names_in_file = common.read_tremvlog_stations(file_path, delimeter)
        station_names_in_file.sort()  # sorts station names alphabetically
        timestamps = common.read_tremvlog_timestamps(file_path, delimeter)

        stat_diff_data = station_difference(station_names_in_file, station_names, file_path, delimeter, filter_index, filters)

        # If station lists differ, must read the whole file in and re-write it
        if (stat_diff_data != None):
            new_station_names = []
            for key in stat_diff_data:
                new_station_names.append(key)

            new_station_names.sort()  # sorts station names alphabetically
            station_names_in_file = new_station_names  # updates station list in file with added stations
            write_tremvlog_stat_differ(new_station_names, filter_index, path, file_path, delimeter, filters, timestamp,
                                  timestamps, stat_diff_data, channel)

        # "backfills" lines of missing data (as 0.0) if gap between previous and current minute
        write_tremvlog_zeroes(file_path, delimeter, timestamp)

        # writes current minute of RSAM data
        write_tremvlog_rsam(file_path, delimeter, timestamp, station_names_in_file, rsam_results, filter_index)


""" If csv file does not exist for current day and filter, creates file. Writes station list as header.
    Also writes missing data as zeroes from start of day to current minute.
"""
def create_tremvlog_file(filename, delim, t, stations):
    output = open(filename, "w")
    output.write("TIMESTAMP" + str(delim))

    # Writes station names at top of CSV file
    for i in range(0, len(stations)):
        output.write(stations[i])
        if (i == len(stations) - 1):
            output.write("\n")
        else:
            output.write(delim)

    minute_of_day = t.minute + t.hour * 60

    # Fill in empty values in the file if it isn't created at midnight.
    for i in range(0, minute_of_day):
        output.write(str(t - 60 * (minute_of_day - i)) + str(delim))

        for j in range(0, len(stations)):
            output.write(str(0.0))
            if (j == len(stations) - 1):
                output.write("\n")
            else:
                output.write(delim)

    output.close()


""" Returns list of lists with added stations and removed stations, comparing station names in config vs. output file.
"""
def station_difference(file_stats, stats, fp, delim, filt_index, filt):
    station_lists_differ = False

    # For added stations: determine if there is difference between config station_names list and output stations
    added_stats = []
    for name in stats:
        # Checks if config file station names are same as data file station names
        if (name not in file_stats):
            station_lists_differ = True
            added_stats.append(name)

    # For removed stations: data and station header will remain in output file until next day.
    removed_stats = []
    for name in file_stats:
        # Checks if station names in file are same as config file station names
        if (name not in stats):
            station_lists_differ = True
            removed_stats.append(name)

    if (station_lists_differ == True):
        data_in_file = common.read_tremvlog_file(fp, delim)  # AKA "result"
        minute_count = len(data_in_file[file_stats[1]])  # At 1 to ignore TIMESTAMP + stat names (first line)

        # account for stations that are not present in the file and fill those with zeroes in dictionary
        for i in range(0, len(stats)):
            name = stats[i]

            if (name not in file_stats):
                file_stats.insert(i, name)
                data_in_file[name] = []

                for j in range(0, minute_count):
                    data_in_file[name].append(0.0)

        # writes in debug log which stations have been removed/added
        if (filt_index == len(filt) - 1):
            if (len(added_stats) > 0):
                debug_print("Added stations: " + str(added_stats))
            if (len(removed_stats) > 0):
                debug_print("Removed stations: " + str(removed_stats))

        return (data_in_file)


""" Reads and rewrites station data from file to include new stations. Inputs zeros for removed stations.
    Writes note in log debug file to state which stations added or removed.
"""
def write_tremvlog_stat_differ(stations, filt_index, p, fp, delim, filt, t, times, data, stat_channel):
    # Writes to an different file so that information isn't lost if the code crashes here
    temp_path = p + "temp" + common.generate_tremvlog_filename(t, filt[filt_index], stat_channel)
    output = open(temp_path, "w")

    output.write("TIMESTAMP" + str(delim))
    stations.sort()  # sorts stations alphabetically for writing
    for i in range(0, len(stations)):
        output.write(stations[i])

        if (i == len(stations) - 1):
            output.write("\n")
        else:
            output.write(delim)

    for i in range(0, len(times)):
        output.write(times[i] + delim)  # adds timestamp at beginning of lines in new file

        for j in range(0, len(stations)):
            name = stations[j]
            output.write(str(data[name][i]))

            if (j == len(stations) - 1):
                output.write("\n")
            else:
                output.write(delim)

    output.close()

    # swap files
    os.rename(fp, fp + "old")
    os.rename(temp_path, fp)
    os.remove(fp + "old")


""" Reads most recent timestamp of file and compares this to the current minute.
    If there is more than one minute difference, input zeroes for missing data.
"""
def write_tremvlog_zeroes(filename, delim, time):
    # Read list of specific timestamps for file rewrite with station addition/removal
    file_path = filename  # to import variable into read timestamp function below

    timestamps = common.read_tremvlog_timestamps(file_path, delim)  #### import this timestamps variable
    station_names_in_file = common.read_tremvlog_stations(file_path, delim)

    # file_exists = os.path.exists(filename)

    # do the actual appending of new data...
    output = open(filename, "a")
    start_timestamp = str(time)  # string of UTC starttime

    if (os.path.exists(filename)):

        last_timestamp = timestamps[-1]

        last_timestamp_min = int(last_timestamp[14:16])  # most recently written timestamp minute
        timestamp_min = int(start_timestamp[14:16])  # current timestamp minute to be written
        check_timestamp_min = last_timestamp_min + 1  # should be equal to timestamp_min if one minute has passed

        last_timestamp_hr = int(last_timestamp[11:13])  # most recently written timestamp hour
        timestamp_hr = int(start_timestamp[11:13])  # current timestamp hour to be written
        check_timestamp_hr = last_timestamp_hr + 1  # should be equal to timestamp_hr if one hour has passed

        # check difference between current timestamp and file timestamp
        min_since_last_write = (timestamp_min - last_timestamp_min) + (timestamp_hr - last_timestamp_hr) * 60 - 1

        # accounts for uninterrupted data progression
        if (timestamp_min == check_timestamp_min and timestamp_hr == last_timestamp_hr):
            pass

        # accounts for uninterrupted hour boundry
        elif (timestamp_min == 00 and last_timestamp_min == 59 and timestamp_hr == check_timestamp_hr):
            pass

        elif (timestamp_min != check_timestamp_min or timestamp_hr != check_timestamp_hr):
            i = min_since_last_write

            while i != 0:
                output.write(str(time - i * 60) + str(delim))  # time was timestamps
                i = i - 1

                for j in range(0, len(station_names_in_file)):
                    output.write(str(0.0))

                    if (j == len(station_names_in_file) - 1):
                        output.write("\n")
                    else:
                        output.write(delim)

        output.close()


""" Called by write_tremvlog_file. Writes current minute of RSAM data to csv file.
"""
def write_tremvlog_rsam(filename, delim, time, stations, rsam, filt_index):
    # open output to append new data
    output = open(filename, "a")

    # Writes current RSAM data
    output.write(str(time) + str(delim))
    for i in range(0, len(stations)):

        name = stations[i]
        result_dict = rsam[filt_index]

        if (name in result_dict):
            output.write(str(result_dict[name]))
        else:
            output.write(str(0.0))

        if (i == len(stations) - 1):
            output.write("\n")
        else:
            output.write(delim)

    output.close()


#TODO:  there is an unchecked assumption here that each trace in the recieved waveforms includes only one station,
#       which seems to be true, but we never actually verify it...

#TODO: the name 'network' in the config file is ambiguous
class program:
    def __init__(self):
        self.config = config.config("config.json")
        self.seedlink = seedlinkClient(self.config["seedlink_address"], self.config["seedlink_port"], 5, False)
        self.fdsn = fdsnClient(self.config["fdsn_address"])
        self.response_inventory = None
        self.fetch_inventory()

    #TODO: schedule this function to execute every day on a seperate thread
    def fetch_inventory(self):
        print("getting response inventory...")
        inventory = self.fdsn.get_stations(network=self.config["network"], station="*", level="response")#TODO station wildcard from config file?
        self.response_inventory = inventory

    def main(self):
        self.config.reload()
        fetch_starttime = UTCDateTime()
        data_starttime = fetch_starttime - 60

        stations_in_network = []

        #TODO:  make this a little nicer
        #TODO:  The station regex isn't consistent with the config, so what do we do?
        #       Maybe we just don't have a station regex and always ask for all stations and then just exclude
        #       the once in on the blacklist?
        fdsn_station_metadata = self.fdsn.get_stations(network=self.config["network"], station="*", starttime=data_starttime, endtime=fetch_starttime)
        for s in fdsn_station_metadata.networks[0]:
            if(s not in self.config["station_blacklist"]):
                stations_in_network.append(s.code)

        log_path = common.logger_output_path(fetch_starttime)

        if(os.path.exists(log_path) == False):
            os.makedirs(log_path)

        debug_print("\nFetch start time: " + str(fetch_starttime))
        debug_print("Data fetch duration: ", end="")

        #TODO: subscribe to the seedlink server instead of doing this??
        received_station_waveforms = self.seedlink.get_waveforms(self.config["network"], self.config["station_wildcard"], self.config["location_wildcard"], self.config["channels"], data_starttime, fetch_starttime)

        debug_print(str(UTCDateTime() - fetch_starttime))

        filters = self.config["filters"]
        rsam_st = UTCDateTime()

        pre_processed_stations = process_station_data(received_station_waveforms)

        for trace in received_station_waveforms:
            name = trace.stats.station
            seed_identifier = self.config["network"] + "." + name + ".." + self.config["channels"]
            response = self.response_inventory.get_response(seed_identifier, fetch_starttime)
            counts_to_um = response.instrument_sensitivity.value / 1000000
            trace.data /= counts_to_um

        per_filter_filtered_stations = apply_bandpass_filters(pre_processed_stations, filters)
        rsam_results = rsam_processing(per_filter_filtered_stations, filters, stations_in_network)

        debug_print("Rsam calculation duration: " + str(UTCDateTime() - rsam_st))

        station_channel = determine_channel(self.config["channels"])
        write_tremvlog_file(rsam_results, filters, stations_in_network, data_starttime, station_channel)

        datestr = str(data_starttime.year) + "." + str(data_starttime.month) + "." + str(data_starttime.day)
        debug_print("Wrote to files " + datestr + " at: " + str(UTCDateTime()))

        if(self.config["alert_on"] == "True"):
            try:
                # Runs tremv_alert module
                alert.main(data_starttime, filters, station_channel)
            except:
                debug_print("Alert module could not be run.")


if __name__ == "__main__":
    p = program()

    #TODO: do the tasks queue up if they take longer than a minute for example?
    scheduler = schedule.Scheduler()
    scheduler.every().minute.at(":00").do(p.main)

    while(True):
        scheduler.run_pending()
        time.sleep(1)
