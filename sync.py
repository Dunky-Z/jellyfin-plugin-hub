#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch and merge personal Jellyfin plugin catalogs into one manifest."""

from __future__ import print_function, unicode_literals

import argparse
import json
import os
import sys
import datetime

try:
    from urllib.error import URLError, HTTPError
    from urllib.request import Request, urlopen
except ImportError:  # Python 2 fallback, not expected
    from urllib2 import Request, urlopen, URLError, HTTPError


ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(ROOT, "sources.json")
DEFAULT_OUTPUT = os.path.join(ROOT, "dist", "manifest.json")
DEFAULT_STATUS = os.path.join(ROOT, "dist", "status.json")
USER_AGENT = "jellyfin-plugin-hub/1.0"
FETCH_TIMEOUT = 30


class FetchError(Exception):
    """Raised when a catalog source cannot be fetched."""


def normalize_guid(guid):
    if guid is None:
        return ""
    return str(guid).strip().lower()


def parse_manifest(text):
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError("invalid JSON: %s" % exc)

    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    raise ValueError("manifest must be a JSON array or object, got %s" % type(data).__name__)


def fetch_text(url, timeout=FETCH_TIMEOUT):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        response = urlopen(request, timeout=timeout)
        try:
            raw = response.read()
        finally:
            response.close()
    except HTTPError as exc:
        raise IOError("HTTP %s for %s" % (exc.code, url))
    except URLError as exc:
        raise IOError("URL error for %s: %s" % (url, exc.reason))
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return raw


def fetch_source(source, fetch=fetch_text):
    urls = source.get("urls") or []
    if not urls:
        raise FetchError("source %s has no urls" % source.get("name", "<unnamed>"))

    errors = []
    for url in urls:
        try:
            plugins = parse_manifest(fetch(url))
            return plugins, url
        except Exception as exc:
            errors.append("%s (%s)" % (url, exc))

    name = source.get("name", "<unnamed>")
    raise FetchError(
        "failed to fetch source %s: %s" % (name, "; ".join(errors))
    )


def _guid_set(values):
    if not values:
        return None
    return set(normalize_guid(item) for item in values if item)


def filter_plugins(plugins, include_guids=None, exclude_guids=None):
    include = _guid_set(include_guids)
    exclude = _guid_set(exclude_guids) or set()
    result = []
    for item in plugins:
        guid = normalize_guid(item.get("guid"))
        if not guid:
            continue
        if include is not None and guid not in include:
            continue
        if guid in exclude:
            continue
        result.append(item)
    return result


def merge_plugins(batches):
    merged = []
    seen = set()
    for plugins in batches:
        for item in plugins:
            guid = normalize_guid(item.get("guid"))
            if not guid or guid in seen:
                continue
            seen.add(guid)
            merged.append(item)
    return merged


def load_config(path):
    with open(path, "r") as handle:
        config = json.load(handle)
    if not isinstance(config, dict) or "sources" not in config:
        raise ValueError("config must contain a sources list: %s" % path)
    if not isinstance(config["sources"], list):
        raise ValueError("sources must be a list: %s" % path)
    return config


def build_hub(config, fetch=fetch_text, allow_partial=False):
    batches = []
    status = []
    failures = []

    for source in config.get("sources") or []:
        name = source.get("name", "<unnamed>")
        try:
            plugins, url = fetch_source(source, fetch=fetch)
            plugins = filter_plugins(
                plugins,
                include_guids=source.get("include"),
                exclude_guids=source.get("exclude"),
            )
            batches.append(plugins)
            status.append({
                "name": name,
                "ok": True,
                "url": url,
                "count": len(plugins),
            })
        except FetchError as exc:
            failures.append(str(exc))
            status.append({
                "name": name,
                "ok": False,
                "error": str(exc),
                "count": 0,
            })

    if failures and not allow_partial:
        raise FetchError("one or more sources failed: %s" % " | ".join(failures))
    if not batches:
        raise FetchError("no plugin catalogs were fetched")

    return merge_plugins(batches), status


def write_json(path, data):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w") as handle:
        handle.write(text)


def _now_utc():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Merge configured Jellyfin plugin catalogs into one manifest."
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to sources.json")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Path to write manifest.json")
    parser.add_argument("--status", default=DEFAULT_STATUS, help="Path to write status.json")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Write output even if some sources fail",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    plugins, status = build_hub(config, allow_partial=args.allow_partial)
    write_json(args.output, plugins)
    write_json(args.status, {
        "generatedAt": _now_utc(),
        "pluginCount": len(plugins),
        "sources": status,
    })

    print("Wrote %s plugins to %s" % (len(plugins), args.output))
    for item in status:
        if item.get("ok"):
            print("  OK  %s (%s plugins) via %s" % (item["name"], item["count"], item["url"]))
        else:
            print("  ERR %s: %s" % (item["name"], item.get("error")))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("error: %s" % exc, file=sys.stderr)
        sys.exit(1)
