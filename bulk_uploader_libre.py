# A script to upload Libre data to Nightscout.
#
# Use the Libre desktop app to transfer data from your Libre to a tsv file, then run this script.
#
# Inspired by https://github.com/cjo20/ns-api-uploader
# Requires Python 3

import argparse
import csv
from datetime import datetime, timezone
import glob
import hashlib
import json
import os
from shutil import copyfile

import requests # pip3 install requests


def url_and_headers(base_url, api_secret):
    url = "%s/api/v1/entries" % base_url
    hashed_secret = hashlib.sha1(api_secret.encode('utf-8')).hexdigest()
    headers = {'API-SECRET' : hashed_secret,
               'Content-Type': "application/json",
               'Accept': 'application/json'}
    return url, headers


def find_last_nightscout_entry(url, headers):
    r = requests.get(url, headers=headers)
    entries = r.json()
    if len(entries) == 0:
        last_timestamp = 0
        print("No entries found in Nightscout")
    else:
        last_timestamp = entries[0]['date'] / 1000
        dt = datetime.fromtimestamp(last_timestamp)
        print("Last timestamp in Nightscout: %s" % dt)
    return last_timestamp


def to_mldg(mmoll):
    return int(mmoll * 18.018018)


def get_latest_file(libre_tsv_glob):
    files = glob.glob(libre_tsv_glob)
    files.sort()
    latest_file = files[-1]
    print("Latest Libre tsv file: %s" % latest_file)
    return latest_file


def copy_file_if_newer(libre_tsv, libre_tsv_glob):
    latest_file = get_latest_file(libre_tsv_glob)
    file_mtime = os.path.getmtime(libre_tsv)
    latest_mtime = os.path.getmtime(latest_file)
    if file_mtime > latest_mtime:
        print("New data found")
        new_file = libre_tsv_glob.replace("*", datetime.strftime(datetime.fromtimestamp(file_mtime), "%Y-%m-%dT%H%M"))
        copyfile(libre_tsv, new_file)
    else:
        print("No new data found")

def upload_to_nightscout(libre_tsv_glob, base_url, api_secret, dry_run=False):

    current_timestamp = int(datetime.now().timestamp())
    print("Current time: %s" % datetime.fromtimestamp(current_timestamp))
    tz = datetime.now(timezone.utc).astimezone().tzinfo # the local timezone

    url, headers = url_and_headers(base_url, api_secret)
    last_timestamp = find_last_nightscout_entry(url, headers)
    latest_file = get_latest_file(libre_tsv_glob)

    with open(latest_file, 'r') as tsvfile:
        # See format of Libre tsv file discussed here: https://github.com/nahog/freestyle-libre-parser-viewer
        reader = csv.reader(tsvfile, delimiter='\t')
        next(reader, None)  # skip the first line (patient name)
        next(reader, None)  # skip the headers
        entries = []
        for row in reader:
            time = row[1]
            dt = datetime.strptime(time, "%Y/%m/%d %H:%M")
            dt = dt.replace(tzinfo=tz)
            timestamp = dt.timestamp()
            if timestamp <= last_timestamp:
                continue
            if timestamp >= current_timestamp:
                continue # ignore times in the future
            date = int(timestamp * 1000)
            date_string = dt.isoformat()
            record_type = int(row[2])
            if record_type == 0: # historic glucose
                entry = dict(type='sgv', sgv=to_mldg(float(row[3])), date=date, dateString=date_string)
                entries.append(entry)
            elif record_type == 1: # scan glucose
                entry = dict(type='sgv', sgv=to_mldg(float(row[4])), date=date, dateString=date_string)
                entries.append(entry)
            elif record_type == 2: # strip glucose
                entry = dict(type='mbg', mbg=to_mldg(float(row[12])), date=date, dateString=date_string)
                entries.append(entry)

        for entry in entries:
            print(entry)

        if len(entries) == 0:
            print("No new entries")
            return

        if dry_run:
            print("Dry run, not uploading to Nightscout")
        else:
            print("Uploading to Nightscout")
            r = requests.post(url, headers=headers, data=json.dumps(entries))
            if r.status_code == 200:
                print("Uploaded successfully")
                print(r.text)
            else:
                print("%d" % r.status_code)
                print(r.text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--api_secret', help="API-SECRET for uploading", required=True)
    parser.add_argument('--base_url', help="Base URL of Nightscout site", required=True)
    parser.add_argument('--libre_tsv', help="Export data file from FreeStyle Libre Desktop App", required=True)
    parser.add_argument('--libre_tsv_glob', help="Local file glob of the form /path/to/dir/libre-*.txt", required=True)
    parser.add_argument('--dry_run', default=False, help="Don't upload to Nightscout")
    args = parser.parse_args()

    copy_file_if_newer(args.libre_tsv, args.libre_tsv_glob)

    upload_to_nightscout(args.libre_tsv_glob, args.base_url, args.api_secret, args.dry_run)
