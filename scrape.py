#!/usr/bin/env python

import os
import json
import time
import logging
import requests
import urlparse
import lxml.html

seen = {}
def load_html(url):
    if url in seen:
        print "already seen %s %s times" % (url, seen[url])
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
    count = 0
    for a in doc.xpath(".//a"):
        link_text = a.text_content()
        link_url = urlparse.urljoin(url, a.attrib["href"])
        if "cgi-bin/query" in link_url:
            if link_text == "PREV PAGE":
                continue
            elif link_text == "NEXT PAGE":
                next_url = link_url
            else:
                count += 1
                yield link_text, link_url
            if count > 2:
                pass #break
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

def transcription(img_url):
    item_dir = os.path.dirname(item["images"][0])
    item_id = os.path.basename(item_dir)
    url = item_dir + "/" + item_id + ".xml"
    if requests.head(url).status_code == 200:
        print url
        return url
    return None

def scrape(skip_until=None):
    metadata = open("metadata.json", "a")
    for series_text, series_url in series_urls():
        for subseries_text, subseries_url in cgi_urls(series_url):
            for item_text, item_url in cgi_urls(subseries_url):
                item = {
                    "series": series_text,
                    "subseries": subseries_text,
                    "title": item_text, 
                    "url": item_url, 
                    "images": []
                }
                for img_url in img_urls(item_url):
                    print img_url
                    item["images"].append(img_url)
                if len(item["images"]) == 0:
                    print "no images", item_url
                item["transcription"] = transcription(item["images"][0])
                metadata.write(json.dumps(item))
                metadata.write("\n")

