#Authors:
#Bethany Erin Vanderhoof
#Þórður Ágúst Karlsson

import errno
import os
import sys
import time
import schedule
import obspy
from obspy.clients.seedlink.basic_client import Client as seedlinkClient
from obspy.clients.fdsn import Client as fdsnClient
from obspy import UTCDateTime
import common
import alert
import threading
import logging


""" 
Apply lowpass filter to the data and downsample it from 100 points per minute to 20 per minute.

Parameters:
    stations: a obspy trace with the stations to pre process.

Returns:
    trace object which has been filtered, decimated and demeaned.
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


""" 
Applies each bandpass filter to each station trace. 
Each trace is added to a dictionary corresponding to the filter that was applied.

Parameters:
    traces: Obspy Stream object(list of traces)
    filters: A list of tuples which describe the bandpass filters to be applied.

Returns:
    A list of dictionaries where each dictionary corresponds to each filter applied.
    Each dictionary contains the filtered traces.
"""
def apply_bandpass_filters(traces, filters):
    passbands = []
 
    for f in filters:
        filtered_stations = {}
 
        for trace in traces:
            t = trace.copy()
            t.filter("bandpass", freqmin=float(f[0]), freqmax=float(f[1]), corners=4, zerophase=True)
            filtered_stations[t.stats["station"]] = t

        passbands.append(filtered_stations)

    return(passbands)


"""
Takes in a list of dictionaries which contain station data that has been filtered with
a bandpass filter and averages the values.

Parameters:
    per_filter_filtered_stations: List of dictionaries which have been filtered with apply_bandpass_filters.
    station_names: List of the names of the stations we are working with.

Returns:
    A list of dictionaries which contain filtered and averaged values.
"""
def rsam_processing(per_filter_filtered_stations, station_names):
    result = []

    for filtered_stations in per_filter_filtered_stations:
        rsam_stations = {}
        for name in station_names:
            rsam_stations[name] = 0.0

            if(name in filtered_stations):
                trace = filtered_stations[name]
                pts_per_minute = int(trace.stats.sampling_rate * 60)

                s = 0
                for n in trace.data:
                    s += abs(n)

                rsam_stations[name] = s / pts_per_minute

        result.append(rsam_stations)

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
            create_tremvlog_file(file_path, timestamp, station_names)

        station_names_in_file = common.read_tremvlog_stations(file_path)
        station_names_in_file.sort()  # sorts station names alphabetically
        timestamps = common.read_tremvlog_timestamps(file_path)

        stat_diff_data = station_difference(station_names_in_file, station_names, file_path, filter_index, filters)

        # If station lists differ, must read the whole file in and re-write it
        if (stat_diff_data != None):
            new_station_names = []
            for key in stat_diff_data:
                new_station_names.append(key)

            new_station_names.sort()  # sorts station names alphabetically
            station_names_in_file = new_station_names  # updates station list in file with added stations
            write_tremvlog_stat_differ(new_station_names, filter_index, path, file_path, filters, timestamp, timestamps, stat_diff_data, channel)

        # "backfills" lines of missing data (as 0.0) if gap between previous and current minute
        write_tremvlog_zeroes(file_path, timestamp)

        # writes current minute of RSAM data
        write_tremvlog_rsam(file_path, timestamp, station_names_in_file, rsam_results, filter_index)


""" If csv file does not exist for current day and filter, creates file. Writes station list as header.
    Also writes missing data as zeroes from start of day to current minute.
"""
def create_tremvlog_file(filename, t, stations):
    output = open(filename, "w")
    output.write("TIMESTAMP" + common.delimiter())

    # Writes station names at top of CSV file
    for i in range(0, len(stations)):
        output.write(stations[i])
        if (i == len(stations) - 1):
            output.write("\n")
        else:
            output.write(common.delimiter())

    minute_of_day = t.minute + t.hour * 60

    # Fill in empty values in the file if it isn't created at midnight.
    for i in range(0, minute_of_day):
        output.write(str(t - 60 * (minute_of_day - i)) + common.delimiter())

        for j in range(0, len(stations)):
            output.write(str(0.0))
            if (j == len(stations) - 1):
                output.write("\n")
            else:
                output.write(common.delimiter())

    output.close()


""" Returns list of lists with added stations and removed stations, comparing station names in config vs. output file.
"""
def station_difference(file_stats, stats, fp, filt_index, filt):
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
        data_in_file = common.read_tremvlog_file(fp)  # AKA "result"
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
                logging.info("Added stations: " + str(added_stats))
            if (len(removed_stats) > 0):
                logging.info("Removed stations: " + str(removed_stats))

        return (data_in_file)


""" Reads and rewrites station data from file to include new stations. Inputs zeros for removed stations.
    Writes note in log debug file to state which stations added or removed.
"""
def write_tremvlog_stat_differ(stations, filt_index, p, fp, filt, t, times, data, stat_channel):
    # Writes to an different file so that information isn't lost if the code crashes here
    temp_path = p + "temp" + common.generate_tremvlog_filename(t, filt[filt_index], stat_channel)
    output = open(temp_path, "w")

    output.write("TIMESTAMP" + common.delimiter())
    stations.sort()  # sorts stations alphabetically for writing
    for i in range(0, len(stations)):
        output.write(stations[i])

        if (i == len(stations) - 1):
            output.write("\n")
        else:
            output.write(common.delimiter())

    for i in range(0, len(times)):
        output.write(times[i] + common.delimiter())  # adds timestamp at beginning of lines in new file

        for j in range(0, len(stations)):
            name = stations[j]
            output.write(str(data[name][i]))

            if (j == len(stations) - 1):
                output.write("\n")
            else:
                output.write(common.delimiter())

    output.close()

    # swap files
    os.rename(fp, fp + "old")
    os.rename(temp_path, fp)
    os.remove(fp + "old")


""" Reads most recent timestamp of file and compares this to the current minute.
    If there is more than one minute difference, input zeroes for missing data.
"""
def write_tremvlog_zeroes(filename, time):
    # Read list of specific timestamps for file rewrite with station addition/removal
    file_path = filename  # to import variable into read timestamp function below

    timestamps = common.read_tremvlog_timestamps(file_path)  #### import this timestamps variable
    station_names_in_file = common.read_tremvlog_stations(file_path)

    # do the actual appending of new data...
    output = open(filename, "a")
    start_timestamp = time  # string of UTC starttime

    if (os.path.exists(filename)):
        #NOTE(thordur): added this to default the beginning of the day if there are no timestamps in a file(this happened...)
        SEC_IN_DAY = 60*60*24
        last_timestamp = UTCDateTime((int(UTCDateTime().timestamp) // SEC_IN_DAY) * SEC_IN_DAY)

        if(len(timestamps) > 0):
            last_timestamp = UTCDateTime(timestamps[-1])

        last_timestamp_minutes = int(last_timestamp.timestamp) // 60
        current_timestamp_minutes = int(time.timestamp) // 60

        minute_delta = current_timestamp_minutes - last_timestamp_minutes

        for i in range(1, minute_delta):
            output.write(str(UTCDateTime((last_timestamp_minutes + i) * 60)) + common.delimiter())

            for j in range(0, len(station_names_in_file)):
                output.write(str(0.0))

                if (j == len(station_names_in_file) - 1):
                    output.write("\n")
                else:
                    output.write(common.delimiter())

        output.close()


""" Called by write_tremvlog_file. Writes current minute of RSAM data to csv file.
"""
def write_tremvlog_rsam(filename, time, stations, rsam, filt_index):
    # open output to append new data
    output = open(filename, "a")

    # Writes current RSAM data
    output.write(str(time) + common.delimiter())
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
            output.write(common.delimiter())

    output.close()

#NOTE: This stuff is needed so we get output from uncaught exceptions in the debug.log file
def log_uncaught_exception_main(exc_type, exc_value, exc_traceback):
    sys.__excepthook__(exc_type, exc_value, exc_traceback)
    logging.critical("uncaught exception:", exc_info=(exc_type, exc_value, exc_traceback))

def log_uncaught_exception_threading(args):
    logging.critical("uncaught exception in thread {}:".format(args.thread.name), exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

sys.excepthook = log_uncaught_exception_main
threading.excepthook = log_uncaught_exception_threading

"""
Class that encapsulates the state and the main loop of the program.
The program relies on a FDSN connection for metadata and response information,
and a seedlink connection for raw data aquisition. Response data is refreshed once a day.
"""
class program:
    def __init__(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler(), logging.FileHandler("debug.log")]
        )

        self.exit = False#used so we can tell the program to exit from a thread
        self.response_lock = threading.Lock()#Lock for the reading of the response inventory as the aquisition happens on another thread.
        self.response_inventory = None
        self.metadata_inventory = None
        self.fdsn = None
        self.config = common.config("config.json")

        if("fdsn_address" not in self.config.config):
            raise Exception("You need to define the FDSN server address in config.json with \"fdsn_address\".")

        if("seedlink_address" not in self.config.config):
            raise Exception("You need to define the seedlink address in config.json with \"seedlink_address\".")

        if("seedlink_port" not in self.config.config):
            raise Exception("You need to define the seedlink port in config.json with \"seedlink_port\".")

        if("network" not in self.config.config):
            raise Exception("You need to define the SEED network config.json with \"network\".")

        if("response_filename" not in self.config.config):
            self.config["response_filename"] = ".resp.xml"

        if("metadata_filename" not in self.config.config):
            self.config["metadata_filename"] = ".meta.xml"

        if("station_wildcard" not in self.config.config):
            self.config["station_wildcard"] = "???"

        if("location_wildcard" not in self.config.config):
            self.config["location_wildcard"] = "??"

        if("channels" not in self.config.config):
            self.config["channels"] = "HHZ"

        if("filters" not in self.config.config):
            self.config["filters"] = [[0.5, 1.0], [1.0, 2.0], [2.0, 4.0]]

        self.fdsn_connect()

        if(os.path.exists(self.config["response_filename"])):
            self.read_response_from_file()
        else:
            self.fetch_response_inventory()


    """
    Tries to connect to the FDSN server. Does not abort on failure, since we might have the relevant information cached.
    """
    def fdsn_connect(self):
        try:
            logging.info("Connecting to fdsn server...")
            self.fdsn = fdsnClient(self.config["fdsn_address"])
        except Exception as e:
            logging.error("Could not connect to fdsn server.")
            logging.info(e)


    """
    Tries to read metadata inventory from file. Aborts program on failure.
    """
    def read_metadata_from_file(self):
        if(os.path.exists(self.config["metadata_filename"])):
            logging.info("Falling back to metadata file.")
            self.metadata_inventory = obspy.read_inventory(self.config["metadata_filename"])
        else:
            self.exit = True
            logging.error("No metadata file was found. Aborting program.")
            sys.exit(1)


    """
    Tries to read response inventory from file. Aborts program on failure.
    """
    def read_response_from_file(self):
        if(os.path.exists(self.config["response_filename"])):
            logging.info("Falling back to response file.")
            self.response_lock.acquire()
            self.response_inventory = obspy.read_inventory(self.config["response_filename"])
            self.response_lock.release()
        else:
            self.exit = True
            logging.error("No response file was found. Aborting program.")
            sys.exit(1)


    """
    Tries to get response inventory from the FDSN connection. Reads from a file on failure.
    """
    def fetch_response_inventory(self):
        logging.info("Fetching response inventory...")

        try:
            inv = self.fdsn.get_stations(network=self.config["network"], station="*", level="response")
            self.response_lock.acquire()
            self.response_inventory = inv
            self.response_lock.release()
            self.response_inventory.write(self.config["response_filename"], format="STATIONXML")
            logging.info("Wrote response inventory to file.")
        except Exception as e:
            logging.error("Could not get response inventory from the fdsn server.")
            logging.info(e)
            if(self.response_inventory is None):
                self.read_response_from_file()
            else:
                logging.info("Using cached response inventory.")


    def fetch_response_inventory_threaded(self):
        thread = threading.Thread(target=self.fetch_response_inventory)
        thread.name = "response_fetch_thread"
        thread.start()


    """
    The main loop of the program.
    Gets raw data for stations that are not on the blacklist(if it is present),
    pre processes and filters it, and then averages the data and writes it to a file.
    """
    def main(self):
        if(self.exit):
            logging.info("Exiting from response fetch thread(file not found and unable to connect to the server).")
            sys.exit(1)

        self.config.reload()
        self.fdsn_connect()

        fetch_starttime = UTCDateTime()
        data_starttime = fetch_starttime - 60

        stations_in_network = []

        try:
            logging.info("Fetching metadata inventory...")
            #NOTE: the station regex here isn't the same as for the seedlink connection...
            metadata = self.fdsn.get_stations(network=self.config["network"], station="*", starttime=data_starttime, endtime=fetch_starttime)
            self.metadata_inventory = metadata
            self.metadata_inventory.write(self.config["metadata_filename"], format="STATIONXML")
            logging.info("Wrote metadata inventory to file.")
        except Exception as e:
            logging.error("Could not get stations metadata from the fdsn server.")
            logging.info(e)
            if(self.metadata_inventory is None):
                self.read_metadata_from_file()
            else:
                logging.info("Using cached metadata inventory.")

        for s in self.metadata_inventory.networks[0]:
            add_station = True
            if("station_blacklist" in self.config.config):
                if(s in self.config["station_blacklist"]):
                    add_station = False

            if(add_station):
                stations_in_network.append(s.code)

        log_path = common.logger_output_path(fetch_starttime)

        if(os.path.exists(log_path) == False):
            os.makedirs(log_path)

        seedlink = None

        try:
            seedlink = seedlinkClient(self.config["seedlink_address"], self.config["seedlink_port"], 5, False)
        except Exception as e:
            logging.error("Could not connect to seedlink server.")
            logging.info(e)

        if(seedlink is not None):
            logging.info("Fetching waveforms...")
            received_station_waveforms = seedlink.get_waveforms(self.config["network"], self.config["station_wildcard"], self.config["location_wildcard"], self.config["channels"], data_starttime, fetch_starttime)
            logging.info("Retrieval of metadata and waveforms took " + str(UTCDateTime() - fetch_starttime))

            filters = self.config["filters"]
            rsam_st = UTCDateTime()

            pre_processed_stations = process_station_data(received_station_waveforms)

            self.response_lock.acquire()
            for trace in pre_processed_stations:
                name = trace.stats.station
                seed_identifier = self.config["network"] + "." + name + ".." + self.config["channels"]
                response = None

                try:
                    response = self.response_inventory.get_response(seed_identifier, fetch_starttime)
                    counts_to_um = response.instrument_sensitivity.value / 1000000

                    for i in range(0, len(trace.data)):
                        trace.data[i] /= counts_to_um
                except Exception as e:
                    logging.error(seed_identifier + ": " + str(e) + " Trace will be removed.")
                    pre_processed_stations.remove(trace)
            self.response_lock.release()

            per_filter_filtered_stations = apply_bandpass_filters(pre_processed_stations, filters)
            rsam_results = rsam_processing(per_filter_filtered_stations, stations_in_network)

            logging.info("Rsam calculation duration: " + str(UTCDateTime() - rsam_st))

            station_channel = determine_channel(self.config["channels"])
            write_tremvlog_file(rsam_results, filters, stations_in_network, data_starttime, station_channel)

            datestr = str(data_starttime.year) + "." + str(data_starttime.month) + "." + str(data_starttime.day)
            logging.info("Wrote to files " + datestr + " at: " + str(UTCDateTime()))

            if("alert_on" in self.config.config and self.config["alert_on"] == True):
                try:
                    def alert_hook():
                    # Runs tremv_alert module
                    alert.main(data_starttime, filters, station_channel, None)
                except Exception as e:
                    logging.error("Alert module could not be run.")
                    logging.error(e)


if __name__ == "__main__":
    p = program()

    #TODO: do the tasks queue up if they take longer than a minute for example?
    scheduler = schedule.Scheduler()
    scheduler.every().minute.at(":00").do(p.main)
    scheduler.every().day.at("00:00").do(p.fetch_response_inventory_threaded)

    while(True):
        scheduler.run_pending()
        time.sleep(1)
