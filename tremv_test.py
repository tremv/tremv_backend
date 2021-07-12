import time
import obspy
from obspy.clients.seedlink.basic_client import Client
from obspy import UTCDateTime

SEC_TO_NANO = 1000*1000*1000
sec_bounds_in_ns = 30 * SEC_TO_NANO
seedlink = Client("sandur.vedur.is", 18000, 5, False)
station_names = {}

while(True):
    print("Getting station info...")
    network_info = seedlink.get_info()

    for t in network_info:
        name = t[1]
        if(name not in station_names):
            station_names[name] = True

    names = list(station_names.keys())
    print(len(names))
    print(names)
    print()
    #figure out how many nano sec are from epoch, then mod that with nano sec in a minute to get how
    #much time we have spent during the current minute. We subtract that from how many nano seconds
    #are in a minute, and then divide by a constant to get how many seconds we are supposed to sleep until
    #the next minute starts.
    print("sleeping...")
    sleeptime_in_sec = (sec_bounds_in_ns - (int(time.time() * SEC_TO_NANO) % sec_bounds_in_ns)) / SEC_TO_NANO
    time.sleep(sleeptime_in_sec)
