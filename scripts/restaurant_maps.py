#!/usr/bin/env python3
"""Google Places helpers for Berlin restaurant pre-fetch verification."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

import requests

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.businessStatus,places.rating,places.userRatingCount,"
    "places.regularOpeningHours,places.googleMapsUri,places.addressComponents"
)

BERLIN_MARKERS = ("berlin", "berlino")
INVALID_MAPS_URL_PREFIXES = (
    "view on google",
    ".",
    "n/a",
)


def log(msg: str) -> None:
    print(msg, flush=True)


def build_search_query(item: dict) -> str:
    name = (item.get("google_maps_name") or item.get("name") or "").strip()
    address = (item.get("google_maps_address") or item.get("address") or "").strip()
    neighborhood = (item.get("neighborhood") or "").strip()
    parts = [name]
    if address:
        parts.append(address)
    elif neighborhood:
        parts.append(neighborhood)
    parts.append("Berlin Germany")
    return " ".join(p for p in parts if p)


def _address_components(place: dict) -> list[dict]:
    return place.get("addressComponents") or []


def is_in_berlin(place: dict) -> bool:
    formatted = (place.get("formattedAddress") or "").lower()
    if any(marker in formatted for marker in BERLIN_MARKERS):
        return True
    for component in _address_components(place):
        types = component.get("types") or []
        text = (component.get("longText") or component.get("shortText") or "").lower()
        if "locality" in types and "berlin" in text:
            return True
        if "administrative_area_level_1" in types and text in {"berlin", "be"}:
            return True
    return False


def business_status_flags(status: str | None) -> tuple[bool, bool]:
    normalized = (status or "").upper()
    permanently_closed = normalized == "CLOSED_PERMANENTLY"
    temporarily_closed = normalized == "CLOSED_TEMPORARILY"
    return permanently_closed, temporarily_closed


def format_hours_compact(place: dict) -> str | None:
    hours = place.get("regularOpeningHours") or {}
    descriptions = hours.get("weekdayDescriptions") or []
    if not descriptions:
        return None
    compact = "; ".join(str(line).strip() for line in descriptions if str(line).strip())
    if len(compact) > 140:
        return compact[:137].rstrip() + "..."
    return compact


def place_id_from_resource(resource_id: str) -> str:
    if resource_id.startswith("places/"):
        return resource_id[len("places/") :]
    return resource_id


def fallback_maps_url(name: str, address: str) -> str:
    query = quote_plus(" ".join(part for part in (name, address, "Berlin") if part))
    return f"https://www.google.com/maps/search/?api=1&query={query}"


def maps_url_is_usable(url: str) -> bool:
    cleaned = (url or "").strip().lower()
    if not cleaned.startswith("http"):
        return False
    return not any(cleaned.startswith(prefix) for prefix in INVALID_MAPS_URL_PREFIXES)


def is_verified(item: dict, *, require_places_api: bool = False) -> bool:
    url = (item.get("google_maps_url") or "").strip()
    if not maps_url_is_usable(url):
        return False
    if not bool(item.get("exists_in_berlin")):
        return False
    if bool(item.get("permanently_closed")) or bool(item.get("temporarily_closed")):
        return False
    if require_places_api and not (item.get("google_maps_place_id") or "").strip():
        return False
    return True


def apply_places_result(item: dict, place: dict, *, query: str) -> None:
    place_id = place_id_from_resource(place.get("id") or "")
    display_name = ((place.get("displayName") or {}).get("text") or "").strip()
    formatted_address = (place.get("formattedAddress") or "").strip()
    permanently_closed, temporarily_closed = business_status_flags(place.get("businessStatus"))
    exists_in_berlin = is_in_berlin(place)

    item["google_maps_place_id"] = place_id or None
    if display_name:
        item["google_maps_name"] = display_name
    if formatted_address:
        item["google_maps_address"] = formatted_address
    maps_uri = (place.get("googleMapsUri") or "").strip()
    if maps_uri:
        item["google_maps_url"] = maps_uri
    elif place_id:
        item["google_maps_url"] = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

    rating = place.get("rating")
    if rating is not None:
        item["google_maps_rating"] = float(rating)
    review_count = place.get("userRatingCount")
    if review_count is not None:
        item["google_maps_review_count"] = int(review_count)
    hours = format_hours_compact(place)
    if hours:
        item["google_maps_hours_compact"] = hours

    item["exists_in_berlin"] = exists_in_berlin
    item["permanently_closed"] = permanently_closed
    item["temporarily_closed"] = temporarily_closed
    item["maps_api_verified"] = (
        bool(place_id)
        and exists_in_berlin
        and not permanently_closed
        and not temporarily_closed
    )

    notes: list[str] = []
    if not exists_in_berlin:
        notes.append("Places API result is outside Berlin")
    if permanently_closed:
        notes.append("Places API: permanently closed")
    if temporarily_closed:
        notes.append("Places API: temporarily closed")
    if item["maps_api_verified"]:
        notes.append(f"Places API verified ({place.get('businessStatus') or 'OPERATIONAL'})")
    else:
        notes.append(f"Places API lookup for '{query}' did not pass verification")
    item["verification_notes"] = "; ".join(notes)


def mark_places_lookup_failed(item: dict, *, query: str, reason: str) -> None:
    item["google_maps_place_id"] = None
    item["maps_api_verified"] = False
    item["exists_in_berlin"] = False
    item["permanently_closed"] = bool(item.get("permanently_closed"))
    item["temporarily_closed"] = bool(item.get("temporarily_closed"))
    if not maps_url_is_usable(item.get("google_maps_url") or ""):
        item["google_maps_url"] = fallback_maps_url(
            item.get("name") or "",
            item.get("google_maps_address") or item.get("address") or "",
        )
    item["verification_notes"] = f"Places API: {reason} (query: {query})"


def search_place(api_key: str, query: str, *, session: requests.Session | None = None) -> dict | None:
    client = session or requests
    response = client.post(
        PLACES_SEARCH_URL,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": PLACES_FIELD_MASK,
        },
        json={"textQuery": query, "regionCode": "DE", "languageCode": "en"},
        timeout=30,
    )
    response.raise_for_status()
    places = response.json().get("places") or []
    return places[0] if places else None


def verify_restaurant_item(
    item: dict,
    *,
    api_key: str,
    session: requests.Session | None = None,
    strict: bool = True,
) -> bool:
    query = build_search_query(item)
    try:
        place = search_place(api_key, query, session=session)
    except requests.RequestException as exc:
        mark_places_lookup_failed(item, query=query, reason=str(exc))
        item["verified"] = is_verified(item, require_places_api=strict)
        return False

    if not place:
        mark_places_lookup_failed(item, query=query, reason="no matching place")
        item["verified"] = is_verified(item, require_places_api=strict)
        return False

    apply_places_result(item, place, query=query)
    item["verified"] = is_verified(item, require_places_api=strict)
    return bool(item["verified"])


def verify_raw_payload(
    payload: dict,
    *,
    api_key: str,
    strict: bool = True,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    items = payload.get("items") or []
    verified_count = 0
    for item in items:
        if verify_restaurant_item(item, api_key=api_key, session=session, strict=strict):
            verified_count += 1
    payload["verified_count"] = verified_count
    payload["maps_verified_at"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat()
    return payload
