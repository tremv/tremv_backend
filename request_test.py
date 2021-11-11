import requests
import json
import datetime

date_start = datetime.datetime(2001, 1, 20)
date_end = datetime.datetime(2001, 1, 21)
query = {}
query["rangestart"] = {"year": date_start.year, "month": date_start.month, "day": date_start.day, "hour": date_start.hour, "minute": date_start.minute}
query["rangeend"] = {"year": date_end.year, "month": date_end.month, "day": date_end.day, "hour": date_end.hour, "minute": date_end.minute}
response = requests.post("http://localhost:4242/api/range", json=query)
print(response.text)
