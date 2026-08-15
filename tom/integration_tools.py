from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx

from .credentials import CredentialManager
from .google_oauth import GoogleOAuth
from .models import Risk
from .tools import ToolRegistry

TIMEOUT = httpx.Timeout(20.0, connect=5.0)
USER_AGENT = "TOM-Agent/2.0"


async def _request(method: str, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, json: dict[str, Any] | None = None, data: dict[str, Any] | None = None, auth: tuple[str, str] | None = None) -> Any:
    merged = {"User-Agent": USER_AGENT, **(headers or {})}
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
        response = await client.request(method, url, params=params, headers=merged, json=json, data=data, auth=auth)
        response.raise_for_status()
        if not response.content:
            return {"status_code": response.status_code}
        return response.json()


def _credential(credentials: CredentialManager | None, provider: str, field: str, env_name: str) -> str:
    stored = credentials.get(provider) if credentials else None
    value = str((stored or {}).get(field, "")).strip() or os.getenv(env_name, "").strip()
    if not value:
        raise RuntimeError(f"provider credential not configured: {env_name}")
    return value


@dataclass
class GoogleCalendarListTool:
    name: str = "google.calendar_list"
    risk: Risk = Risk.READ
    description: str = "List upcoming Google Calendar events for the connected account."
    oauth: GoogleOAuth | None = None

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.oauth is None:
            raise RuntimeError("Google OAuth is not initialized")
        token = await self.oauth.access_token()
        calendar_id = str(arguments.get("calendar_id", "primary"))
        params: dict[str, Any] = {"maxResults": max(1, min(50, int(arguments.get("max_results", 10)))), "singleEvents": "true", "orderBy": "startTime"}
        if arguments.get("time_min"):
            params["timeMin"] = str(arguments["time_min"])
        return await _request("GET", f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events", params=params, headers={"Authorization": f"Bearer {token}"})


@dataclass
class GoogleCalendarCreateTool:
    name: str = "google.calendar_create"
    risk: Risk = Risk.HIGH
    description: str = "Create a Google Calendar event after explicit TOM approval."
    oauth: GoogleOAuth | None = None

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.oauth is None:
            raise RuntimeError("Google OAuth is not initialized")
        token = await self.oauth.access_token()
        summary, start, end = str(arguments["summary"]).strip(), str(arguments["start"]).strip(), str(arguments["end"]).strip()
        if not summary or not start or not end:
            raise ValueError("summary, start and end are required")
        body: dict[str, Any] = {"summary": summary, "start": {"dateTime": start}, "end": {"dateTime": end}}
        for field in ("description", "location"):
            if arguments.get(field):
                body[field] = str(arguments[field])
        if arguments.get("attendees"):
            body["attendees"] = [{"email": str(email)} for email in arguments["attendees"]]
        calendar_id = str(arguments.get("calendar_id", "primary"))
        return await _request("POST", f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events", headers={"Authorization": f"Bearer {token}"}, json=body)


@dataclass
class GmailSearchTool:
    name: str = "google.gmail_search"
    risk: Risk = Risk.READ
    description: str = "Search messages in the connected Gmail account."
    oauth: GoogleOAuth | None = None

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.oauth is None:
            raise RuntimeError("Google OAuth is not initialized")
        token = await self.oauth.access_token()
        query = str(arguments.get("query", "")).strip()
        limit = max(1, min(25, int(arguments.get("limit", 10))))
        listed = await _request("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages", params={"q": query, "maxResults": limit}, headers={"Authorization": f"Bearer {token}"})
        messages = []
        for item in listed.get("messages", []):
            detail = await _request("GET", f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{item['id']}", params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]}, headers={"Authorization": f"Bearer {token}"})
            messages.append(detail)
        return {"resultSizeEstimate": listed.get("resultSizeEstimate", 0), "messages": messages}


@dataclass
class GmailSendTool:
    name: str = "google.gmail_send"
    risk: Risk = Risk.HIGH
    description: str = "Send a Gmail message after explicit TOM approval."
    oauth: GoogleOAuth | None = None

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.oauth is None:
            raise RuntimeError("Google OAuth is not initialized")
        token = await self.oauth.access_token()
        to, subject, body = str(arguments["to"]).strip(), str(arguments.get("subject", "")).strip(), str(arguments["body"])
        if not to or not body:
            raise ValueError("to and body are required")
        raw = f"To: {to}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n{body}"
        encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
        return await _request("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send", headers={"Authorization": f"Bearer {token}"}, json={"raw": encoded})


@dataclass
class GooglePlacesSearchTool:
    credentials: CredentialManager | None = None
    name: str = "maps.places_search"
    risk: Risk = Risk.READ
    description: str = "Search real places using Google Places."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        key = _credential(self.credentials, "google_maps", "api_key", "TOM_GOOGLE_MAPS_API_KEY")
        query = str(arguments["query"]).strip()
        if not query:
            raise ValueError("query is required")
        body: dict[str, Any] = {"textQuery": query, "pageSize": max(1, min(20, int(arguments.get("limit", 10))))}
        if arguments.get("latitude") is not None and arguments.get("longitude") is not None:
            body["locationBias"] = {"circle": {"center": {"latitude": float(arguments["latitude"]), "longitude": float(arguments["longitude"])}, "radius": float(arguments.get("radius_m", 5000))}}
        return await _request("POST", "https://places.googleapis.com/v1/places:searchText", headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.rating,places.websiteUri"}, json=body)


@dataclass
class GoogleRoutesTool:
    credentials: CredentialManager | None = None
    name: str = "maps.route"
    risk: Risk = Risk.READ
    description: str = "Calculate a driving, walking or bicycling route using Google Routes."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        key = _credential(self.credentials, "google_maps", "api_key", "TOM_GOOGLE_MAPS_API_KEY")
        origin = {"location": {"latLng": {"latitude": float(arguments["origin_lat"]), "longitude": float(arguments["origin_lon"])}}}
        destination = {"location": {"latLng": {"latitude": float(arguments["destination_lat"]), "longitude": float(arguments["destination_lon"])}}}
        mode = str(arguments.get("travel_mode", "DRIVE")).upper()
        if mode not in {"DRIVE", "WALK", "BICYCLE", "TWO_WHEELER"}:
            raise ValueError("unsupported travel mode")
        return await _request("POST", "https://routes.googleapis.com/directions/v2:computeRoutes", headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.legs.steps.navigationInstruction"}, json={"origin": origin, "destination": destination, "travelMode": mode})


@dataclass
class TwilioSmsTool:
    credentials: CredentialManager | None = None
    name: str = "communication.sms_send"
    risk: Risk = Risk.HIGH
    description: str = "Send an SMS through Twilio after explicit TOM approval."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        sid = _credential(self.credentials, "twilio", "account_sid", "TOM_TWILIO_ACCOUNT_SID")
        token = _credential(self.credentials, "twilio", "auth_token", "TOM_TWILIO_AUTH_TOKEN")
        from_number = _credential(self.credentials, "twilio", "from_number", "TOM_TWILIO_FROM_NUMBER")
        to, body = str(arguments["to"]).strip(), str(arguments["body"]).strip()
        if not to or not body:
            raise ValueError("to and body are required")
        return await _request("POST", f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", data={"From": from_number, "To": to, "Body": body}, auth=(sid, token))


def register_integration_tools(registry: ToolRegistry, credentials: CredentialManager) -> GoogleOAuth:
    oauth = GoogleOAuth(credentials)
    for tool in (GoogleCalendarListTool(oauth=oauth), GoogleCalendarCreateTool(oauth=oauth), GmailSearchTool(oauth=oauth), GmailSendTool(oauth=oauth), GooglePlacesSearchTool(credentials), GoogleRoutesTool(credentials), TwilioSmsTool(credentials)):
        registry.register(tool)
    return oauth
