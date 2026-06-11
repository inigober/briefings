#!/usr/bin/env python3
"""Tests for Google Places restaurant verification helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from restaurant_maps import (  # noqa: E402
    apply_places_result,
    build_search_query,
    business_status_flags,
    format_hours_compact,
    is_in_berlin,
    is_verified,
    maps_url_is_usable,
    verify_restaurant_item,
)
from slim_inbox_for_synthesis import RESTAURANT_SLIM_ITEM_KEYS  # noqa: E402


class RestaurantMapsTests(unittest.TestCase):
    def test_build_search_query_uses_name_and_address(self) -> None:
        item = {
            "name": "Da Jia Le",
            "address": "Goebenstraße 23, 10783 Berlin",
            "neighborhood": "Schöneberg",
        }
        self.assertIn("Da Jia Le", build_search_query(item))
        self.assertIn("Goebenstraße", build_search_query(item))

    def test_business_status_flags(self) -> None:
        self.assertEqual(business_status_flags("CLOSED_PERMANENTLY"), (True, False))
        self.assertEqual(business_status_flags("CLOSED_TEMPORARILY"), (False, True))
        self.assertEqual(business_status_flags("OPERATIONAL"), (False, False))

    def test_is_in_berlin_from_formatted_address(self) -> None:
        place = {"formattedAddress": "Goebenstraße 23, 10783 Berlin, Germany"}
        self.assertTrue(is_in_berlin(place))

    def test_format_hours_compact_joins_weekday_descriptions(self) -> None:
        place = {
            "regularOpeningHours": {
                "weekdayDescriptions": [
                    "Monday: Closed",
                    "Tuesday: 12:00 – 10:00 PM",
                ]
            }
        }
        self.assertIn("Monday", format_hours_compact(place) or "")

    def test_is_verified_strict_requires_place_id(self) -> None:
        item = {
            "google_maps_url": "https://www.google.com/maps/place/?q=place_id:abc",
            "exists_in_berlin": True,
            "permanently_closed": False,
            "temporarily_closed": False,
        }
        self.assertTrue(is_verified(item, require_places_api=False))
        self.assertFalse(is_verified(item, require_places_api=True))
        item["google_maps_place_id"] = "abc"
        self.assertTrue(is_verified(item, require_places_api=True))

    def test_maps_url_is_usable_rejects_placeholder(self) -> None:
        self.assertFalse(maps_url_is_usable("."))
        self.assertFalse(maps_url_is_usable("View on Google Maps"))
        self.assertTrue(maps_url_is_usable("https://maps.google.com/?q=Foo"))

    def test_apply_places_result_marks_closed(self) -> None:
        item = {"name": "Da Jia Le"}
        place = {
            "id": "places/ChIJtest",
            "displayName": {"text": "Da Jia Le"},
            "formattedAddress": "Goebenstraße 23, 10783 Berlin, Germany",
            "businessStatus": "CLOSED_PERMANENTLY",
            "googleMapsUri": "https://maps.google.com/?cid=123",
        }
        apply_places_result(item, place, query="Da Jia Le Berlin")
        self.assertTrue(item["permanently_closed"])
        self.assertFalse(item["maps_api_verified"])
        self.assertFalse(is_verified(item, require_places_api=True))

    def test_verify_restaurant_item_operational(self) -> None:
        item = {"name": "Pamfilya", "address": "Luxemburger Straße 1, 13353 Berlin"}
        place = {
            "id": "places/ChIJpamfilya",
            "displayName": {"text": "Pamfilya Restaurant"},
            "formattedAddress": "Luxemburger Str. 1, 13353 Berlin, Germany",
            "businessStatus": "OPERATIONAL",
            "rating": 4.0,
            "userRatingCount": 2484,
            "regularOpeningHours": {
                "weekdayDescriptions": ["Monday: 8:00 AM – 12:00 AM"]
            },
            "googleMapsUri": "https://maps.google.com/?cid=456",
        }
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"places": [place]}
        session = MagicMock()
        session.post.return_value = mock_response

        self.assertTrue(
            verify_restaurant_item(item, api_key="test-key", session=session, strict=True)
        )
        self.assertEqual(item["google_maps_rating"], 4.0)
        self.assertEqual(item["google_maps_review_count"], 2484)
        self.assertTrue(item["maps_api_verified"])

    def test_slim_keys_include_maps_metadata(self) -> None:
        required = {
            "google_maps_rating",
            "google_maps_review_count",
            "google_maps_hours_compact",
            "google_maps_place_id",
            "maps_api_verified",
        }
        self.assertTrue(required.issubset(set(RESTAURANT_SLIM_ITEM_KEYS)))


if __name__ == "__main__":
    unittest.main()
