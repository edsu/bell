#!/usr/bin/env python

import os
import re
import sys
import json
import time
import logging
import requests
import urlparse
import lxml.html
import lxml.etree
import requests_cache

logging.basicConfig(filename="scrape.log", level=logging.INFO)

# use a cache to prevent multiple fetches for the same URL
requests_cache.configure("ammem")

seen = {}
def load_html(url):
    if url in seen:
        logging.warn("already seen %s %s times", url, seen[url])

    seen[url] = seen.get(url, 0) + 1
    # look out for loops
    if seen[url] > 5:
        logging.fatal("aborting, fetched same url 5 times")
        sys.exit(1)

    # be somewhat gentle w/ the server :)
    time.sleep(1)

    return lxml.html.fromstring(requests.get(url).content)

def series_urls():
    url = "http://memory.loc.gov/ammem/bellhtml/magbellSeries.html"
    doc = load_html(url)
    for a in doc.xpath(".//a"):
        if "bellhtml/" in a.attrib["href"]:
            yield a.text_content(), urlparse.urljoin(url, a.attrib["href"])

def cgi_urls(url):
    doc = load_html(url)
    next_url = None
    for a in doc.xpath(".//a"):
        link_text = a.text_content()
        link_url = urlparse.urljoin(url, a.attrib["href"])
        if "cgi-bin/query" in link_url:
            if link_text == "PREV PAGE":
                continue
            elif link_text == "NEXT PAGE":
                next_url = link_url
            else:
                yield link_text, link_url
    if next_url:
        for t, u in cgi_urls(next_url):
            yield t, u

def img_urls(url):
    doc = load_html(url)
    next_url = None
    archival_img = None
    for a in doc.xpath(".//a"):
        link_text = a.text_content()
        link_url = urlparse.urljoin(url, a.attrib.get("href", None))
        if "Archival" in link_text and "JPEG" in link_text:
            archival_img = link_url
        elif link_text == "NEXT IMAGE":
            next_url = link_url

    if archival_img:
        yield archival_img

    if next_url:
        for u in img_urls(next_url):
            yield u

def get_transcription(item):
    if len(item["images"]) == 0:
        return None
    item_dir = os.path.dirname(item["images"][0])
    item_id = os.path.basename(item_dir)
    url = item_dir + "/" + item_id + ".xml"
    if requests.head(url).status_code == 200:
        logging.info("got transcription %s", url)
        return url
    return None

def get_last_item():
    if os.path.isfile("metadata.json"):
        for line in open("metadata.json"):
            last = line
        return json.loads(last)

def scrape(resume=False):
    # if there is a metadata file get the last item pulled down to see
    # if we can resume
    last_item = get_last_item()
    if not last_item:
        resume = False

    metadata = open("metadata.json", "a")
    for series_text, series_url in series_urls():
        if resume and series_text != last_item["series"]:
            logging.info("skipping series %s", series_text)
            continue
        for folder_text, folder_url in cgi_urls(series_url):
            if resume and subseries_text != last_item["subseries"]:
                logging.info("skipping subseries %s", subseries_text)
                continue

            # sometimes there's an item at the folder level
            item = get_item(folder_url)
            if item:
                metadata.write(json.dumps(item))
                metadata.write("\n")
                logging.info("got item at folder level from %s", folder_url)
                continue

            for item_text, item_url in cgi_urls(folder_url):
                if resume and item_text != last_item["title"]:
                    logging.info("skipping item %s", item_text)
                    continue
                elif resume:
                    resume = False
                    continue

                item = get_item(item_url)
                if not item:
                    logging.fatal("unable to fetch item from %s" , item_url)
                logging.info("got item from %s", item_url)
                metadata.write(json.dumps(item))
                metadata.write("\n")

def get_item(url):
    doc = load_html(url)
    html = lxml.etree.tostring(doc)
    m = re.search(r'</font><br/>\n(.+?)(?: - <a href="(.+?)">Transcription</a>)?<br/>\(Series: (.+), Folder: (.+)\)', html)
    if not m:
        return None
    title, transcription, series, folder = m.groups()
    m = re.search(r"<!-- (http://memory.loc.gov/cgi-bin/ampage\?collId=magbell.+) -->", html)
    url = m.group(1)

    # make transcription link absolute
    if transcription:
        transcription = urlparse.urljoin(url, transcription)

    item = {
        "url": url,
        "title": title,
        "series": series,
        "folder": folder,
        "transcription": transcription,
        "images": list(img_urls(url)),
    }

    # use the image links to sniff out where the transcription xml is
    item["transcription_xml"] = get_transcription(item)

    return item

if __name__ == "__main__":
    scrape(resume=True)
    #print get_item("http://memory.loc.gov/cgi-bin/ampage?collId=magbell&fileName=391/39100301/bellpage.db&RecNum=0")
    #print get_item("http://memory.loc.gov/cgi-bin/ampage?collId=magbell&fileName=391/39100101/bellpage.db&RecNum=0")
