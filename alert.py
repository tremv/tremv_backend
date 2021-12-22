# Author:
# Bethany Erin Vanderhoof

import os
import common
import numpy
from obspy import UTCDateTime


class ClassAlertInfo:

    def __init__(self):
        self.filter_list = []
        self.lta = {}
        self.sta = {}
        self.ramp = {}
        self.ratio_values = {}
        self.station_trigger = {}
        self.filters_triggered = {}
        self.current_eventID = {}
        self.previous_eventID = {}
        self.current_velocity = {}
        self.ramp_buffer = {}
        self.audio_alarm = {}
        self.alert_on = {}
        self.alarm_per_hr = 0
        self.target_hr = ""

    def alert_on_redefine(self, filters, alert_on):

        for name in filters:
            filter_name = str(name)
            if(filter_name not in alert_on):
                alert_on[filter_name] = False

# Class acts as a global variable
AlertInfo = ClassAlertInfo()


""" Defines the start and end times of the STA and LTA windows. Returns lists with start & end times for sta and lta.
"""
def define_windows(starttime, sta_length, lta_length):
    # window start and end times
    sta_window_start = starttime - sta_length
    sta_window_end = starttime
    lta_window_end = sta_window_start - 60
    lta_window_start = lta_window_end - lta_length

    windows = [[sta_window_start, sta_window_end], [lta_window_start, lta_window_end]] # sta and lta windows
    return(windows)


""" Specifies for which day/s data must be pulled (and thus for which days files should exist).
    Only accommodates maximum LTA plus STA windows spanning max two days. Returns list of days (data range).
"""
def define_data_range(windows, time):

    sta_window_start = windows[0][0]
    lta_window_start = windows[1][0]

    data_range = [] # list of time range with relevant data. Only more than len=1 if windows overlap day boundary
    if(str(lta_window_start)[8:10] != str(time)[8:10]):
        data_range.append(lta_window_start)
    elif(str(sta_window_start)[8:10] != str(time)[8:10]):
        data_range.append(lta_window_start)

    data_range.append(time) # appending time here so that an older date would be first in the list
    return(data_range)


""" Reads csv files and returns two dictionaries -- one for the sta window and one for the lta window.
    Dictionaries span the time of windows (in min) defined in the alert_config.json configuration file.
    Returns dictionaries in relevant time range for each filter.
"""
def read_data(filters, data_range, delimeter, station_channel):

    data_dicts = {}

    # reads csv files...
    for i in range(0, len(filters)):
        filter_name = str(filters[i])

        data = {}
        for j in range(0, len(data_range)): # one or two days worth of data
            path = common.logger_output_path(data_range[j])
            file = common.generate_tremvlog_filename(data_range[j], filters[i], station_channel)
            file_path = path+file

            min_past_midnight = int(str(data_range[j])[11:13]) * 60 + int(str(data_range[j])[14:16]) + 1

            data1 = {}
            station_names1 = []

            if(os.path.exists(file_path)):
                if(len(data_range) == 1): # if only one day for data
                    all_data = common.read_tremvlog_file(file_path, delimeter)
                    data = {}

                    for name in all_data:
                        data[name] = all_data[name][0:min_past_midnight]

                else: # if two days for data
                    if(j == 0):
                        timestamps1 = common.read_tremvlog_timestamps(file_path, delimeter) # reads prev day file timestamps
                        station_names1 = common.read_tremvlog_stations(file_path, delimeter) # reads prev day file stations
                        missing_min = 1440 - len(timestamps1) # notes how many mins of data are missing from first file
                        data1 = common.read_tremvlog_file(file_path, delimeter)

                        # Assuming that the file has all timestamps from start of day until a single stopping minute...
                        for k in range(0,missing_min):
                            for name in station_names1:
                                data1[name].append(0.0)

                    if(j > 0): # if averaging window/s span two days
                        timestamps2 = common.read_tremvlog_timestamps(file_path, delimeter) # reads prev day file timestamps
                        station_names2 = common.read_tremvlog_stations(file_path, delimeter)

                        # only reads first x minutes of second (current day) file (up to current starttime)
                        all_data2 = common.read_tremvlog_file(file_path, delimeter)
                        data2 = {}

                        for name in all_data2:
                            data2[name] = all_data2[name][0:min_past_midnight]

                        # checks if stations are same for both days, if not, add empty data for first day missing stat
                        for name in station_names1:
                            if(name not in station_names2):
                                add_zero_data = []
                                for r in range(0, len(timestamps2)):
                                    add_zero_data.append(0.0)
                                data2[name] = add_zero_data

                        # checks if stations are same for both days, if not, add empty data for second day missing stat
                        for name in station_names2:
                            if(name not in station_names1):
                                add_zero_data = []
                                for r in range(0, 1440):
                                    add_zero_data.append(0.0)
                                data1[name] = add_zero_data

                        # combine dictionaries for first and second days
                        data = {}
                        for k in data1.keys():
                            data.update({k: []})
                            for m in data1[k]:
                                data[k].append(m)
                            for n in data2[k]:
                                data[k].append(n)

        data_dicts[filter_name] = data

    return(data_dicts)


""" Removes stations specified in remove_stations variable in config file so they aren't included in data processing.
    Returns a dictionary of data with specified stations removed.
"""
def remove_stat(filters, data_dict, remove_stat):

    for i in range(0, len(filters)):
        filter_name = str(filters[i])

        for name in remove_stat:
            try:
                data_dict[filter_name].pop(name)
            except:
                pass

    return(data_dict)


""" Splits the data dictionaries from read_data() to the appropriate time windows for the STA and LTA.
    Returns a list of two lists--for STA data and LTA data --each containing the list of dictionaries for each filter.
"""
def split_data(data, sta_length, lta_length, avg_length, ramp_int, filters):

    sta_min = int((sta_length+60)/60) # convert back to min from sec
    lta_min = int((lta_length+60)/60)

    sta_data = {}
    lta_data = {}
    ramp_data = {}
    velocity_data = {}

    for i in range(0, len(filters)):
        filter_name = str(filters[i])
        sta_data_dict = {}
        lta_data_dict = {}
        ramp_data_dict = {}
        velocity_data_dict = {}

        for name in data[filter_name]:
            sta_data_list = []
            lta_data_list = []
            ramp_data_list = []

            for j in range(1, sta_min+1):
                sta_data_list.append(data[filter_name][name][-j])
            for k in range(1, lta_min+1):
                lta_data_list.append(data[filter_name][name][-k-sta_min]) # end of sta window - k
            for l in range(1, avg_length*ramp_int+1):
                ramp_data_list.append(data[filter_name][name][-l])
            velocity_data_dict[name] = data[filter_name][name][-1]

            # assigns data to station and reverses list of data so it's in correct order (earliest to latest)
            sta_data_dict[name] = sta_data_list[::-1]
            lta_data_dict[name] = lta_data_list[::-1]
            ramp_data_dict[name] = ramp_data_list[::-1]

        sta_data[filter_name] = sta_data_dict
        lta_data[filter_name] = lta_data_dict
        ramp_data[filter_name] = ramp_data_dict
        velocity_data[filter_name] = velocity_data_dict

    AlertInfo.sta = sta_data
    AlertInfo.lta = lta_data
    AlertInfo.ramp = ramp_data
    AlertInfo.current_velocity = velocity_data


""" For each station (and each filter), averages RSAM values for each station within long and short windows.
    Returns list of dictionaries (one per filter) of STA and LTA averages for each station.
"""
def avg_windows(data_percent, filters):

    data = [AlertInfo.sta, AlertInfo.lta]

    for i in range(0, len(data)): # len 2, position 0 for sta & position 1 for lta
        for j in range(0, len(filters)):
            filter_name = str(filters[j])

            for name in data[i][filter_name]:
                list_to_avg = data[i][filter_name][name]
                list_sum = 0
                length = 0 # length of data to be averaged

                for k in range(0, len(list_to_avg)):

                    if(str(list_to_avg[k]) != "0.0"):
                        #list_sum += numpy.log(list_to_avg[k])
                        list_sum += list_to_avg[k]
                        length += 1

                data_percent_used = (length/len(list_to_avg))*100

                # redefines AlertInfo.sta and AlertInfo.lta list as average (with natural log applied before)
                if(length != 0 and data_percent_used >= data_percent):
                    avg = list_sum/length
                    data[i][filter_name][name] = avg
                else:
                    data[i][filter_name][name] = None


""" Calculates sta/lta ratio for each station from avg_windows() data.
    Returns list of dictionaries (one per filter) of the sta/lta ratio at each station.
"""
def calc_ratio(filters):

    sta = AlertInfo.sta
    lta = AlertInfo.lta

    ratio = {}
    for i in range(0, len(filters)):
        filter_name = str(filters[i])

        ratio_dict = {}

        for name in sta[filter_name]:
            if(sta[filter_name][name] != None and lta[filter_name][name] != None):
                ratio_dict[name] = (sta[filter_name][name])/(lta[filter_name][name])
        ratio[filter_name] = ratio_dict

    AlertInfo.ratio_values = ratio


""" Checks most recent sta ratio values (in ring buffer) to see if most recent is higher than first (or in steps?).
    Checking first value (ratio recorded x minutes earlier) versus current value -- only important for new trigger.
"""
def make_ramp(avg_length, ramp_int, filters):

    data = AlertInfo.ramp
    ramp_dict = {}

    for name in filters:
        filter_name = str(name)
        ring_buffer_dict = {}
        for station in data[filter_name]:
            buffer_averages = []

            i = 1
            while i < (ramp_int * avg_length):
                sum_num = 0
                for j in range(0, avg_length):
                    sum_num += data[filter_name][station][-i]
                    i += 1

                avg_num = sum_num / avg_length
                buffer_averages.insert(0, avg_num)

            ring_buffer_dict[station] = buffer_averages
        ramp_dict[filter_name] = ring_buffer_dict

    AlertInfo.ramp_buffer = ramp_dict


""" Assigns boolean True or False to each station for each filter, True if ratio above trigger ratio, False if below.
    Counts number of stations that are triggered (aka stations assigned True).
    Returns list with list of dictionaries (one per filter) of True/False and list of number of votes (one per filter).
"""
def stat_voting(trigger_ratio, min_velocity):

    stat_triggered = {}
    trig_votes = {}

    ratios = AlertInfo.ratio_values
    ramp_dict = AlertInfo.ramp_buffer
    velocities = AlertInfo.current_velocity

    for filter_name in ratios:
        trigger_dict = {} # dictionary with boolian
        trig_vote = 0
        for name in ratios[filter_name]:

            # checks that most recent velocity is at or above velocity threshold
            if(velocities[filter_name][name] >= min_velocity):

                # checks that sta/lta ratio above trigger ratio
                if(ratios[filter_name][name] >= trigger_ratio):

                    i = 1
                    while i < len(ramp_dict[filter_name][name]):

                        # checks that each most recent ramps interval average is higher than previous
                        if(ramp_dict[filter_name][name][-i] > ramp_dict[filter_name][name][-i - 1]):
                            i += 1

                            if(i == len(ramp_dict[filter_name][name])):
                                trigger_dict[name] = True
                                trig_vote += 1

                        else:
                            trigger_dict[name] = False
                            break

                else:
                    trigger_dict[name] = False

            else:
                trigger_dict[name] = False

        stat_triggered[filter_name] = trigger_dict
        trig_votes[filter_name] = trig_vote

    AlertInfo.station_trigger = stat_triggered # list of dictionaries (one per filter) with bool if station triggered

    votes = trig_votes
    return(votes)


""" For each filter, checks if enough stations are triggered to set alert_on to TRUE (if alert_on currently FALSE).
    If alert_on is FALSE and enough votes to change it to TRUE, create entry in catalog.
    If alert_on is already TRUE, checks if any new stations have triggered (or untriggered) - will update activity file.
"""
def trigger(vote, votes_needed):

    trig_votes = vote
    filters = AlertInfo.filter_list

    triggered_filters_dict = {}
    alert_on_dict = {}

    for name in filters:
        filter_name = str(name)

        if(trig_votes[filter_name] >= votes_needed): # vote is list with vote count corresponding to [filt1, filt2, ...]
            triggered_filters_dict[filter_name] = True # this line sets the first alarm to true!
            alert_on_dict[filter_name] = True

        elif(trig_votes[filter_name] < votes_needed):
            triggered_filters_dict[filter_name] = False
            alert_on_dict[filter_name] = False

    AlertInfo.filters_triggered = triggered_filters_dict


""" Creates new event in catalog and new file, if necessary. Returns event_info (for filter, give time & eventID).
"""
def catalog_new_event(current_time, current_filter, current_info, previous_info, current_stations, line_one, space):

    # defines file path of new catalog (or of existing catalog) based on current time
    cat_path = ("tremor_catalog/" + str(current_time.year) + "/")
    if (os.path.exists(cat_path) == False):
        os.makedirs(cat_path)

    month = str(current_time.month)
    year = str(current_time.year)

    filename = year + "." + month + "_tremor_catalog.txt"
    file_path = cat_path + filename

    if (os.path.exists(file_path) == False):
        catalog = open(file_path, "w+")
        catalog.write(line_one)
        catalog.close()

    catalog = open(file_path, "r")
    lines = catalog.readlines()  # previous event ID
    prevID = (lines[-1]).split()[0]

    # define new event ID for new event (add 1 to old event ID)
    # HANDLE if over year or month boundary
    if(prevID == "EventID"):
        eventID = 1
    else:
        eventID = int(prevID) + 1

    current_info[current_filter] = [eventID, current_time]
    previous_info[current_filter] = [eventID, current_time]

    # remove " " and "'" from station and filter strings to avoid future reading issues (i.e. .split())
    characters_to_remove = " '[]"
    current_stations.sort()
    stations = str(current_stations)
    for character in characters_to_remove:
        stations = stations.replace(character, "")

    write_filter = str(current_filter).replace(" ", "")

    # allotted space for written variables (somewhat arbitrary, but nice for reading)
    id_space = (7 - len(str(eventID))) * " " + space
    time_space = (27 - len(str(current_time))) * " " + space
    filter_space = (12 - len(str(write_filter))) * " " + space

    catalog = open(file_path, "a")
    catalog.write(str(eventID) + id_space + str(current_time) + time_space + str(write_filter) + filter_space +
                  str(stations) + "\n")
    catalog.close()

    AlertInfo.previous_eventID = previous_info
    AlertInfo.alert_on[current_filter] = True  # for a filter, set alert_on to True (preserves state for next run)
    return(current_info)


""" Adds newly triggered stations for event to currently triggered event line in catalog.
"""
def catalog_edit_event(current_filter, current_stations, alert_on, line_one):

    time = AlertInfo.current_eventID[current_filter][1]  # if filt already triggered, tries reading event id & starttime
    eventID = AlertInfo.current_eventID[current_filter][0]

    # must do this in case the file with currently triggered event is different month or year!
    cat_path = ("tremor_catalog/" + str(time.year) + "/")
    if(os.path.exists(cat_path) == False):
        os.makedirs(cat_path)

    month = str(time.month)
    year = str(time.year)

    filename = year + "." + month + "_tremor_catalog.txt"
    file_path = cat_path + filename

    catalog = open(file_path, "r")
    lines = catalog.readlines()[1:]  # previous event ID
    rewrite_lines = [line_one]

    for line in lines:

        if(int(line.split()[0]) == int(eventID)):  # checks for line with previous eventID
            previous_stations = line.split()[3]
            previous_stations = previous_stations.split(",")

            for station in current_stations:
                if station not in previous_stations:
                    previous_stations.append(station)
            previous_stations.sort()

            # remove " " and "'" from station and filter strings to avoid future reading issues (i.e. .split())
            characters_to_remove = " '[]"
            stations = str(previous_stations)
            for character in characters_to_remove:
                stations = stations.replace(character, "")

            line = str(line[0:58]) + str(stations) + "\n"

        rewrite_lines.append(line)
    catalog.close()

    temp_path = file_path + "temp"
    catalog = open(temp_path, "w")
    catalog.writelines(rewrite_lines)
    catalog.close()

    # swap files
    os.rename(file_path, file_path + "old")
    os.rename(temp_path, file_path)
    os.remove(file_path + "old")

    alert_on[current_filter] = True


""" Creates catalogue of tremor events.
"""
def write_catalog(time, filters, minimum_event_gap):

    triggered_filters = AlertInfo.filters_triggered
    AlertInfo.alert_on_redefine(filters, AlertInfo.alert_on)
    alert_status = AlertInfo.alert_on

    # currently hardcoded, allows proper space for more than enough events per month
    #s = "    "
    #s = "    "
    #first_line = "EventID" + s + "TriggerTime                " + s + "Filter      " + s + "Stations\n"
    #NOTE(thordur): I changed this to facilitate programmatic reading of the catalog files(i.e. reading them to a dict)
    delim = "\t"
    first_line = "EventID" + delim + "TriggerTime" + delim + "Filter" + delim + "Stations\n"

    event_info = AlertInfo.current_eventID

    audio = {}
    for name in filters:
        filter_name = str(name)
        triggered_stations = AlertInfo.station_trigger
        stations = []  # list of triggered stations
        event_info = AlertInfo.current_eventID
        prev_info = AlertInfo.previous_eventID # previously triggered events (rechecked for every filter)

        for station in triggered_stations[filter_name]:
            if(triggered_stations[filter_name][station] == True):
                stations.append(station)

        if(triggered_filters[filter_name] == True):

            if(alert_status[filter_name] == False): # start event record, current min trigger! but prev min no trigger

                try:
                    # Accounts for the minimum minutes between tremor event starttimes, may append to previous event
                    new_tremor_time = prev_info[filter_name][1] + minimum_event_gap * 60
                    if(time <= new_tremor_time):
                        alert_status[filter_name] = True
                        event_info[filter_name] = prev_info[filter_name]
                        AlertInfo.current_eventID = event_info
                        catalog_edit_event(filter_name, stations, alert_status, first_line)
                        audio[filter_name] = False
                    else:
                        # returns event_info for AlertInfo.current_event_id
                        event_info = catalog_new_event(time, filter_name, event_info, prev_info, stations, first_line, delim)
                        audio[filter_name] = True  # sets audio alarm dictionary to true for given minute
                except:
                    # returns event_info for AlertInfo.current_event_id
                    event_info = catalog_new_event(time, filter_name, event_info, prev_info, stations, first_line, delim)
                    audio[filter_name] = True  # sets audio alarm dictionary to true for given minute

            elif(alert_status[filter_name] == True):
                # read most recent event ID for this filter and check if new stations must be added to this event
                catalog_edit_event(filter_name, stations, alert_status, first_line)
                audio[filter_name] = False

        elif(triggered_filters[filter_name] == False):
            # make alert on False for this station
            if(alert_status[filter_name] == False):
                alert_status[filter_name] = False
            elif(alert_status[filter_name] == True):
                event_info.pop(filter_name)
                alert_status[filter_name] = False
            audio[filter_name] = False

    AlertInfo.audio_alarm = audio
    AlertInfo.current_eventID = event_info


""" Prevents muted stations from voting to set off audio alarm trigger. The triggered event will still be written in the
    catalog. Useful for ongoing effusive eruptions to mute stations in certain regions while still writing event logs.
"""
def silence_muted_stations(muted_stats, votes_needed, votes, filters):

    # remove muted station votes from audio alarm. Will not ring if too few station votes minus muted stat votes.
    if(len(muted_stats) != 0):

        stations_triggered = AlertInfo.station_trigger
        for name in filters:
            filter_name = str(name)
            mute_votes = 0
            for station in stations_triggered[filter_name]:
                if(station in muted_stats):
                    if(AlertInfo.station_trigger[filter_name][station] == True):
                        mute_votes += 1

            updated_votes = votes[filter_name] - mute_votes
            if(updated_votes < votes_needed):
                AlertInfo.audio_alarm[filter_name] = False


""" Prevents muted filters from setting off an audio alarm trigger. Triggered events will still be written in the 
    catalog.
"""
def silence_muted_filters(muted_filt, filters):

    for name in filters:
        filter_name = str(name)

        if(filter_name in str(muted_filt)):
            AlertInfo.audio_alarm[filter_name] = False


""" Determines if an audio alarm must be triggered for this minute. Returns a boolian True or False for audio alarm.
    Only triggers once per event, when a filter is first triggered. Will not ring alarm if "silence_alarm" = "True".
"""
def ring_audio_alarm(filters, silence, max_audio, time):

    if(silence == "True"):
        ring_alarm = False # will not ring if module has been silenced
    else:
        ring_alarm = False
        audio_alarm = AlertInfo.audio_alarm

        for name in filters:
            filter_name = str(name)
            if(audio_alarm[filter_name] == True):
                ring_alarm = True
                AlertInfo.alarm_per_hr += 1

                # Limits number of audio alarms that ring per hour
                if(time >= AlertInfo.target_hr or AlertInfo.target_hr == ""):

                    AlertInfo.target_hr = UTCDateTime(str(time)[0:13]) + 3600
                    AlertInfo.alarm_per_hr = 0

                if(AlertInfo.alarm_per_hr > max_audio):
                    ring_alarm = False

                break

    return(ring_alarm)


def main(starttime, logger_filters, channel, alert_hook=None):
    alert_config = common.config("alert_config.json")

    AlertInfo.filter_list = logger_filters # import filters in data structure from tremv_logger

    delim = "," # Maybe configure this better elsewhere. In config file? Or hardcode and import into alert from logger.

    # window length in min (because cannot be smaller than 1 minute) -- config file in min, this var in sec
    sta_len = alert_config["sta_length"]*60-60
    # * 60 to convert to sec, minus 60 because already includes data from current minute
    lta_len = alert_config["lta_length"]*60-60

    # read data, split data to sta and lta windows
    time_windows = define_windows(starttime, sta_len, lta_len)
    time_range = define_data_range(time_windows, starttime)
    data_dictionary = read_data(logger_filters, time_range, delim, channel)
    updated_data_dict = remove_stat(logger_filters, data_dictionary, alert_config["remove_stations"])
    split_data(updated_data_dict, sta_len, lta_len, alert_config["ramp_min_avg"], alert_config["ramp_intervals"],
               logger_filters)

    # checks that ramp exists before eruption
    make_ramp(alert_config["ramp_min_avg"], alert_config["ramp_intervals"], logger_filters)

    # checks that sta/lta trigger ratio is satisfied
    avg_windows(alert_config["percentage_data"], logger_filters)
    calc_ratio(logger_filters)

    voting = stat_voting(alert_config["trigger_ratio"], alert_config["min_velocity"])
    trigger(voting, alert_config["station_votes"])
    write_catalog(starttime, logger_filters, alert_config["minimum_min_between_events"])

    silence_muted_stations(alert_config["mute_stations"], alert_config["station_votes"], voting, logger_filters)
    silence_muted_filters(alert_config["mute_filters"], logger_filters)
    run_alert_hook=ring_audio_alarm(logger_filters,alert_config["silence_audio"],alert_config["max_audio_per_hr"],starttime)

    if(run_alert_hook == True):
        print("Triggering alert hook.")
        if(alert_hook):
            alert_hook()
