#testa hvort do block-i þegar við erum að ná í inventory file með fdsn
import time
import threading
import logging
import schedule
import obspy
from obspy.clients.fdsn import Client as fdsnClient
from obspy import UTCDateTime

def run_threaded(f):
    thread = threading.Thread(target=f)
    thread.start()

def func_a():
    for i in range(0, 6):
        print(i)
        time.sleep(5)

def func_b():
    fdsn = None

    try:
        logging.info("Connecting to fdsn server...")
        fdsn = fdsnClient("http://eos-seiscomp-d01.vedur.is/fdsnws/")
    except Exception as e:
        logging.error("Could not connect to fdsn server. Using old inventory file.")
        logging.info(e)
        return

    st = time.time()
    logging.info("Getting inventory file...")
    inv = fdsn.get_stations(network="VI", station="*", level="response")
    logging.info("Done. This took "  + str(time.time() - st) + " sec")

scheduler = schedule.Scheduler()
scheduler.every().minute.at(":00").do(run_threaded, func_b)
scheduler.every().minute.at(":05").do(func_a)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

while(True):
    scheduler.run_pending()
    time.sleep(1)

#niðurstaða:    þetta defintely block-ar, ég gæti notað asyncio og gert loop_create til að schedule-a þetta,
#               sem býr síðan til temp file og swappar þegar það er ekkert að gerast

"""
Atburðar rásin í loggernum ætti að vera eftirfarandi:
    Í upphafi á forritinu reynum við að tengjast við fdsn. Ef það klikkar og inventory skráin er ekki til,
    þurfum við að _crash-a_

    Ef það heppnast og inventory skráin er ekki til þurfum við að sækja hana.

    Þar sem við notum self.fdsn athugum við hvort hann sé None og reynum að tengjast ef svo er.
    Ef það virkar ekki notum við cached dót í staðinn.

    Ef seedlink tengingin virkar ekki ætti forritið hinsvegar að hrynja
"""
