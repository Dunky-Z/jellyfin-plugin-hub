# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import sync  # noqa: E402


METATUBE_GUID = "01cc53ec-c415-4108-bbd4-a684a9801a32"
SHOOTER_GUID = "038d37a2-7a1e-4c01-9b6d-aa215d29ab4c"
THUNDER_GUID = "e4ce9da9-ef00-417c-96f2-861c512d45eb"


def plugin(guid, name, version="1.0.0.0"):
    return {
        "guid": guid,
        "name": name,
        "description": name,
        "overview": name,
        "owner": "test",
        "category": "Metadata",
        "versions": [
            {
                "version": version,
                "changelog": "test",
                "targetAbi": "10.11.0.0",
                "sourceUrl": "https://example.com/%s.zip" % name,
                "checksum": "abc",
                "timestamp": "2026-01-01T00:00:00Z",
            }
        ],
    }


class FakeFetch(object):
    def __init__(self, mapping=None, errors=None):
        self.mapping = mapping or {}
        self.errors = errors or {}
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if url in self.errors:
            raise self.errors[url]
        if url not in self.mapping:
            raise IOError("not found: %s" % url)
        data = self.mapping[url]
        if not isinstance(data, str):
            data = json.dumps(data)
        return data


class MergeTests(unittest.TestCase):
    def test_merge_keeps_plugins_from_all_sources(self):
        a = [plugin(METATUBE_GUID, "MetaTube")]
        b = [plugin(SHOOTER_GUID, "Shooter"), plugin(THUNDER_GUID, "Thunder")]
        merged = sync.merge_plugins([a, b])
        names = [item["name"] for item in merged]
        self.assertEqual(names, ["MetaTube", "Shooter", "Thunder"])

    def test_merge_dedupes_by_guid_and_keeps_first(self):
        first = plugin(METATUBE_GUID, "MetaTube-jsdelivr", "2.0.0.0")
        second = plugin(METATUBE_GUID, "MetaTube-raw", "1.0.0.0")
        merged = sync.merge_plugins([[first], [second]])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["name"], "MetaTube-jsdelivr")
        self.assertEqual(merged[0]["versions"][0]["version"], "2.0.0.0")

    def test_merge_guid_compare_is_case_insensitive(self):
        first = plugin(METATUBE_GUID.upper(), "A")
        second = plugin(METATUBE_GUID.lower(), "B")
        merged = sync.merge_plugins([[first], [second]])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["name"], "A")

    def test_merge_skips_entries_without_guid(self):
        valid = plugin(METATUBE_GUID, "MetaTube")
        merged = sync.merge_plugins([[{"name": "broken"}, valid]])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["name"], "MetaTube")


class ParseTests(unittest.TestCase):
    def test_parse_manifest_array(self):
        text = json.dumps([plugin(METATUBE_GUID, "MetaTube")])
        parsed = sync.parse_manifest(text)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "MetaTube")

    def test_parse_manifest_single_object(self):
        text = json.dumps(plugin(METATUBE_GUID, "MetaTube"))
        parsed = sync.parse_manifest(text)
        self.assertEqual(len(parsed), 1)

    def test_parse_manifest_rejects_invalid_json(self):
        with self.assertRaises(ValueError):
            sync.parse_manifest("not-json")

    def test_parse_manifest_rejects_unexpected_type(self):
        with self.assertRaises(ValueError):
            sync.parse_manifest("123")


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.plugins = [
            plugin(METATUBE_GUID, "MetaTube"),
            plugin(SHOOTER_GUID, "Shooter"),
            plugin(THUNDER_GUID, "Thunder"),
        ]

    def test_include_keeps_only_listed_guids(self):
        filtered = sync.filter_plugins(
            self.plugins, include_guids=[THUNDER_GUID]
        )
        self.assertEqual([item["name"] for item in filtered], ["Thunder"])

    def test_exclude_drops_listed_guids(self):
        filtered = sync.filter_plugins(
            self.plugins, exclude_guids=[SHOOTER_GUID]
        )
        self.assertEqual(
            [item["name"] for item in filtered], ["MetaTube", "Thunder"]
        )


class FetchSourceTests(unittest.TestCase):
    def test_fetch_source_uses_first_working_url(self):
        source = {
            "name": "MetaTube",
            "urls": [
                "https://cdn.example/fail.json",
                "https://raw.example/ok.json",
            ],
        }
        fetch = FakeFetch(
            mapping={"https://raw.example/ok.json": [plugin(METATUBE_GUID, "MetaTube")]},
            errors={"https://cdn.example/fail.json": IOError("cdn down")},
        )
        plugins, url = sync.fetch_source(source, fetch=fetch)
        self.assertEqual(url, "https://raw.example/ok.json")
        self.assertEqual(plugins[0]["name"], "MetaTube")
        self.assertEqual(fetch.calls, [
            "https://cdn.example/fail.json",
            "https://raw.example/ok.json",
        ])

    def test_fetch_source_raises_when_all_urls_fail(self):
        source = {
            "name": "MetaTube",
            "urls": ["https://a.example/x.json", "https://b.example/x.json"],
        }
        fetch = FakeFetch(errors={
            "https://a.example/x.json": IOError("a"),
            "https://b.example/x.json": IOError("b"),
        })
        with self.assertRaises(sync.FetchError):
            sync.fetch_source(source, fetch=fetch)


class BuildHubTests(unittest.TestCase):
    def test_build_hub_merges_sources(self):
        config = {
            "sources": [
                {
                    "name": "MetaTube",
                    "urls": ["https://meta.example/manifest.json"],
                },
                {
                    "name": "MeiamSubtitles",
                    "urls": ["https://sub.example/manifest.json"],
                },
            ]
        }
        fetch = FakeFetch(mapping={
            "https://meta.example/manifest.json": [plugin(METATUBE_GUID, "MetaTube")],
            "https://sub.example/manifest.json": [
                plugin(SHOOTER_GUID, "Shooter"),
                plugin(THUNDER_GUID, "Thunder"),
            ],
        })
        merged, status = sync.build_hub(config, fetch=fetch)
        self.assertEqual(
            [item["name"] for item in merged],
            ["MetaTube", "Shooter", "Thunder"],
        )
        self.assertTrue(all(item["ok"] for item in status))

    def test_build_hub_strict_fails_when_one_source_is_down(self):
        config = {
            "sources": [
                {"name": "MetaTube", "urls": ["https://meta.example/manifest.json"]},
                {"name": "MeiamSubtitles", "urls": ["https://sub.example/manifest.json"]},
            ]
        }
        fetch = FakeFetch(
            mapping={"https://meta.example/manifest.json": [plugin(METATUBE_GUID, "MetaTube")]},
            errors={"https://sub.example/manifest.json": IOError("down")},
        )
        with self.assertRaises(sync.FetchError):
            sync.build_hub(config, fetch=fetch, allow_partial=False)

    def test_build_hub_allow_partial_keeps_successful_sources(self):
        config = {
            "sources": [
                {"name": "MetaTube", "urls": ["https://meta.example/manifest.json"]},
                {"name": "MeiamSubtitles", "urls": ["https://sub.example/manifest.json"]},
            ]
        }
        fetch = FakeFetch(
            mapping={"https://meta.example/manifest.json": [plugin(METATUBE_GUID, "MetaTube")]},
            errors={"https://sub.example/manifest.json": IOError("down")},
        )
        merged, status = sync.build_hub(config, fetch=fetch, allow_partial=True)
        self.assertEqual([item["name"] for item in merged], ["MetaTube"])
        self.assertEqual([item["ok"] for item in status], [True, False])


class WriteTests(unittest.TestCase):
    def test_write_manifest_is_json_array(self):
        plugins = [plugin(METATUBE_GUID, "MetaTube")]
        handle, path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        try:
            sync.write_json(path, plugins)
            with open(path, "r") as handle:
                loaded = json.load(handle)
            self.assertIsInstance(loaded, list)
            self.assertEqual(loaded[0]["guid"], METATUBE_GUID)
        finally:
            os.remove(path)


class ConfigTests(unittest.TestCase):
    def test_load_config_reads_sources_json(self):
        config_path = os.path.join(ROOT, "sources.json")
        config = sync.load_config(config_path)
        by_name = {item["name"]: item for item in config["sources"]}
        self.assertEqual(
            [item["name"] for item in config["sources"]],
            [
                "MetaTube",
                "MeiamSubtitles",
                "MetaShark",
                "ThePornDB",
                "Skin Manager",
                "Intro Skipper",
                "Danmu",
                "SubMichi",
            ],
        )
        self.assertIn(
            "https://cdn.jsdelivr.net/gh/metatube-community/jellyfin-plugin-metatube@dist/manifest.json",
            by_name["MetaTube"]["urls"],
        )
        self.assertIn(
            "https://github.com/91270/MeiamSubtitles.Release/raw/main/Plugin/manifest-stable.json",
            by_name["MeiamSubtitles"]["urls"],
        )
        self.assertIn(
            "https://github.com/cxfksword/jellyfin-plugin-metashark/releases/download/manifest/manifest.json",
            by_name["MetaShark"]["urls"],
        )
        self.assertIn(
            "https://raw.githubusercontent.com/ThePornDatabase/Jellyfin.Plugin.ThePornDB/main/manifest.json",
            by_name["ThePornDB"]["urls"],
        )
        self.assertEqual(
            by_name["Skin Manager"]["include"],
            ["e9ca8b8e-ca6d-40e7-85dc-58e536df8eb3"],
        )
        self.assertEqual(
            by_name["Intro Skipper"]["include"],
            ["c83d86bb-a1e0-4c35-a113-e2101cf4ee6b"],
        )
        self.assertIn(
            "https://github.com/cxfksword/jellyfin-plugin-danmu/releases/download/manifest/manifest.json",
            by_name["Danmu"]["urls"],
        )
        self.assertIn(
            "https://raw.githubusercontent.com/vicvinue/jellyfin-plugin-subtitlecat/main/manifest.json",
            by_name["SubMichi"]["urls"],
        )


if __name__ == "__main__":
    unittest.main()
