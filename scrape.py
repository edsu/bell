#!/usr/bin/env python

import os
import json
import time
import logging
import requests
import urlparse
import lxml.html

logging.basicConfig(filename="scrape.log", level=logging.INFO)

seen = {}
def load_html(url):
    if url in seen:
        logging.warn("already seen %s %s times", url, seen[url])
    seen[url] = seen.get(url, 0) + 1
    time.sleep(1)
    return lxml.html.fromstring(requests.get(url).content)

def series_urls():
    url = "http://memory.loc.gov/ammem/bellhtml/magbellSeries.html"
    doc = load_html(url)
    count = 1
    for a in doc.xpath(".//a"):
        if "bellhtml/" in a.attrib["href"]:
            count += 1
            yield a.text_content(), urlparse.urljoin(url, a.attrib["href"])
            if count > 2:
                pass #break

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
    metadata = open("metadata.json", "a")

    # if there is a metadata file get the last item pulled down to see
    # if we can resume
    last_item = get_last_item()

    for series_text, series_url in series_urls():
        if resume and series_text != last_item["series"]:
            logging.info("skipping series %s", series_text)
            continue
        for subseries_text, subseries_url in cgi_urls(series_url):
            if resume and subseries_text != last_item["subseries"]:
                logging.info("skipping subseries %s", subseries_text)
                continue
            for item_text, item_url in cgi_urls(subseries_url):
                if resume and item_text != last_item["title"]:
                    logging.info("skipping item %s", item_text)
                    continue
                elif resume:
                    resume = False
                    continue
                item = {
                    "series": series_text,
                    "subseries": subseries_text,
                    "title": item_text, 
                    "url": item_url, 
                    "images": []
                }
                for img_url in img_urls(item_url):
                    logging.info("got image %s", img_url)
                    item["images"].append(img_url)
                if len(item["images"]) == 0:
                    logging.warn("no images found for %s", item_url)
                item["transcription"] = get_transcription(item)
                metadata.write(json.dumps(item))
                metadata.write("\n")

if __name__ == "__main__":
    scrape(resume=True)
