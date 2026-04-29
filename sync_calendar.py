"""
Firebase Cloud Function: Sync climbing app schedule to Google Calendar (teamlanovka@gmail.com)
Runs on schedule: 3x daily (6:30, 12:30, 18:30)

Reads CAL from GitHub source, reads Firestore data, syncs to Google Calendar.
"""

import functions_framework
import requests
import json
import re
from datetime import datetime, timedelta
from google.cloud import firestore
from google.oauth2 import service_account
import googleapiclient.discovery

# Firebase Firestore
db = firestore.Client()

# Google Calendar API
SCOPES = ['https://www.googleapis.com/auth/calendar']
CALENDAR_ID = 'teamlanovka@gmail.com'

# Sector definitions (from index.html CAL)
SECTORS_MON = {
    'L1': 'Převis + Bizár',
    'L2': 'Dole kout + Strop',
    'L3': 'Nový profil + nahoře kolmice',
    'L4': 'Hříbek',
    'L5': 'Dole kolmice + převis',
}

SECTORS_WED = {
    'D': 'Dětská',
    'P': 'Přední převis',
    'Z': 'Zadní převis',
    'K': 'Kolmice',
}


def parse_cal_from_github():
    """Fetch index.html and parse CAL object"""
    try:
        resp = requests.get(
            'https://raw.githubusercontent.com/cyrilwoo/climbing-app/main/index.html',
            timeout=10
        )
        resp.raise_for_status()
        html = resp.text

        # Find CAL object: const CAL = { ... };
        match = re.search(r"const CAL = \{(.*?)\n    \};", html, re.DOTALL)
        if not match:
            print("ERROR: CAL not found in index.html")
            return {}

        cal_str = "{" + match.group(1) + "}"

        # Parse entries: '2026-07-06': { mon: L1, thu: TG },
        cal = {}
        for line in match.group(1).split('\n'):
            line = line.strip()
            if not line or line.startswith('//'):
                continue

            m = re.match(r"'(\d{4}-\d{2}-\d{2})':\s*\{(.*?)\}", line)
            if not m:
                continue

            week_id = m.group(1)
            fields_str = m.group(2)

            entry = {}
            for field in ['mon', 'wed', 'thu']:
                # mon: L1 or mon: L1, or mon: null or missing
                fm = re.search(rf"{field}:\s*([A-Z0-9]+)?", fields_str)
                if fm and fm.group(1):
                    entry[field] = fm.group(1)

            cal[week_id] = entry

        return cal

    except Exception as e:
        print(f"ERROR parsing CAL from GitHub: {e}")
        return {}


def get_sector_name(code, is_wed=False):
    """Convert sector code (L1, D, P, etc.) to name"""
    if is_wed:
        return SECTORS_WED.get(code)
    else:
        return SECTORS_MON.get(code)


def get_calendar_service():
    """Get authorized Google Calendar service"""
    # Uses default Application Default Credentials (Cloud Function automatically provides this)
    return googleapiclient.discovery.build('calendar', 'v3')


def list_events_on_date(service, date_str):
    """List events on a specific date in teamlanovka@gmail.com calendar"""
    start = datetime.fromisoformat(f"{date_str}T00:00:00").isoformat() + "Z"
    end = datetime.fromisoformat(f"{date_str}T23:59:59").isoformat() + "Z"

    try:
        result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start,
            timeMax=end,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        return result.get('items', [])
    except Exception as e:
        print(f"ERROR listing events on {date_str}: {e}")
        return []


def find_event(events, prefix):
    """Find event starting with prefix (e.g., 'Lanovka', 'Limit')"""
    for ev in events:
        if ev.get('summary', '').startswith(prefix):
            return ev
    return None


def delete_event(service, event_id):
    """Delete event from calendar"""
    try:
        service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
        return True
    except Exception as e:
        print(f"ERROR deleting event {event_id}: {e}")
        return False


def create_event(service, summary, date_str, start_time, end_time):
    """Create event in calendar"""
    try:
        event = {
            'summary': summary,
            'start': {
                'dateTime': f"{date_str}T{start_time}",
                'timeZone': 'Europe/Prague'
            },
            'end': {
                'dateTime': f"{date_str}T{end_time}",
                'timeZone': 'Europe/Prague'
            },
            'colorId': '3',  # Grape
            'reminders': {'useDefault': False}
        }
        result = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        return result
    except Exception as e:
        print(f"ERROR creating event: {e}")
        return None


def update_event(service, event_id, summary):
    """Update event summary"""
    try:
        event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()
        event['summary'] = summary
        service.events().update(calendarId=CALENDAR_ID, eventId=event_id, body=event).execute()
        return True
    except Exception as e:
        print(f"ERROR updating event {event_id}: {e}")
        return False


def format_setters(setters, lano=None):
    """Format setters list: 'Name1, Name2, ...' + lano if present"""
    active = [s for s in (setters or []) if s and s != '__NULL__']
    if lano and lano != '__NULL__':
        active.append(lano)
    if not active:
        return None
    return ', '.join(active)


def firestore_value(val):
    """Extract value from Firestore field wrapper (REST API dict or native Python SDK type)"""
    if val is None:
        return None
    # Native Python SDK: list
    if isinstance(val, list):
        return [firestore_value(v) for v in val]
    # Native Python SDK: string
    if isinstance(val, str):
        return None if val == '__NULL__' else val
    # Native Python SDK: bool
    if isinstance(val, bool):
        return val
    # REST API format: dict with type wrappers
    if isinstance(val, dict):
        if val.get('nullValue') is not None:
            return None
        if 'stringValue' in val:
            v = val['stringValue']
            return None if v == '__NULL__' else v
        if 'arrayValue' in val:
            arr = val['arrayValue'].get('values', [])
            return [firestore_value(v) for v in arr]
        if 'booleanValue' in val:
            return val['booleanValue']
        if 'mapValue' in val:
            # Sector override object: {sector: ..., isOff: ...}
            fields = val['mapValue'].get('fields', {})
            return {k: firestore_value(v) for k, v in fields.items()}
    return val


@functions_framework.http
def sync_calendar(request):
    """Main sync function"""
    try:
        cal = parse_cal_from_github()
        if not cal:
            return "ERROR: Could not parse CAL", 500

        service = get_calendar_service()

        now = datetime.now()
        weeks_to_sync = []

        # Find weeks to sync: within 7 days past to 90 days future
        for week_id in sorted(cal.keys()):
            try:
                week_date = datetime.strptime(week_id, '%Y-%m-%d')
                days_diff = (week_date - now).days
                if -7 <= days_diff <= 90:
                    weeks_to_sync.append(week_id)
            except:
                continue

        created = 0
        updated = 0
        deleted = 0

        # Sync each week
        for week_id in weeks_to_sync:
            cal_entry = cal[week_id]

            # Fetch Firestore data
            try:
                doc = db.collection('weeks').document(week_id).get()
                fw_data = doc.to_dict() or {}
            except:
                fw_data = {}

            # Extract Firestore values
            mon_setters = firestore_value(fw_data.get('monday')) or []
            mon_lano = firestore_value(fw_data.get('mondayLano'))
            wed_setters = firestore_value(fw_data.get('wednesday')) or []
            thu_setters = firestore_value(fw_data.get('thursday')) or []
            mon_sundavaci = firestore_value(fw_data.get('mondaySundavaci')) or []
            wed_sundavaci = firestore_value(fw_data.get('wednesdaySundavaci')) or []
            mon_myti = firestore_value(fw_data.get('mondayMyti'))
            wed_myti = firestore_value(fw_data.get('wednesdayMyti'))

            mon_cancelled = firestore_value(fw_data.get('_monCancelled'))
            wed_cancelled = firestore_value(fw_data.get('_wedCancelled'))
            mon_shifted = firestore_value(fw_data.get('_monShifted'))
            wed_shifted = firestore_value(fw_data.get('_wedShifted'))

            # Determine dates and sectors
            week_date = datetime.strptime(week_id, '%Y-%m-%d')
            mon_date = week_id
            wed_date = (week_date + timedelta(days=3 if cal_entry.get('wed') == 'D' else 2)).strftime('%Y-%m-%d')
            thu_date = (week_date + timedelta(days=3)).strftime('%Y-%m-%d')

            # Lanovka (Monday)
            mon_sector_code = cal_entry.get('mon')
            # Check monSectorOverride from Firestore
            mon_override = firestore_value(fw_data.get('monSectorOverride'))
            if isinstance(mon_override, dict) and (mon_override.get('isOff') or mon_override.get('sector')):
                if mon_override.get('isOff'):
                    mon_sector_code = None  # overridden to off
                else:
                    # Overridden to specific sector name (already a label, not a code)
                    mon_override_sector = mon_override.get('sector')
                    if mon_override_sector:
                        # Use override sector name directly
                        mon_sector_code = '_OVERRIDE_'
                        mon_sector_name_override = mon_override_sector

            if mon_sector_code and mon_sector_code != '_OVERRIDE_':
                mon_sector = get_sector_name(mon_sector_code, False)
            elif mon_sector_code == '_OVERRIDE_':
                mon_sector = mon_sector_name_override
            else:
                mon_sector = None

            if mon_sector and not (mon_cancelled or mon_shifted):
                setters_str = format_setters(mon_setters, mon_lano)
                title = f"Lanovka — {mon_sector}"
                if setters_str:
                    title += f" | {setters_str}"

                events = list_events_on_date(service, mon_date)
                event = find_event(events, 'Lanovka')

                if event:
                    if event.get('summary') != title:
                        update_event(service, event['id'], title)
                        updated += 1
                else:
                    create_event(service, title, mon_date, '07:15:00', '15:00:00')
                    created += 1

                # Sundavání Lanovka (day before)
                if mon_sundavaci:
                    sun_date = (week_date - timedelta(days=1)).strftime('%Y-%m-%d')
                    sun_setters = format_setters(mon_sundavaci)
                    sun_title = f"Sundavání Lanovka | {sun_setters}"
                    if mon_myti:
                        sun_title += f" | mytí: {mon_myti}"

                    events = list_events_on_date(service, sun_date)
                    event = find_event(events, 'Sundavání Lanovka')

                    if event:
                        if event.get('summary') != sun_title:
                            update_event(service, event['id'], sun_title)
                            updated += 1
                    else:
                        create_event(service, sun_title, sun_date, '20:00:00', '22:00:00')
                        created += 1
                else:
                    # No sundavači — delete any existing Sundavání Lanovka event on that day
                    sun_date = (week_date - timedelta(days=1)).strftime('%Y-%m-%d')
                    events = list_events_on_date(service, sun_date)
                    event = find_event(events, 'Sundavání Lanovka')
                    if event:
                        delete_event(service, event['id'])
                        deleted += 1
            else:
                # No Lanovka this week — delete any wrong Lanovka event on mon_date
                events = list_events_on_date(service, mon_date)
                event = find_event(events, 'Lanovka')
                if event:
                    delete_event(service, event['id'])
                    deleted += 1
                # Also delete Sundavání Lanovka (day before)
                sun_date = (week_date - timedelta(days=1)).strftime('%Y-%m-%d')
                events = list_events_on_date(service, sun_date)
                event = find_event(events, 'Sundavání Lanovka')
                if event:
                    delete_event(service, event['id'])
                    deleted += 1

            # Limit (Wednesday/Thursday)
            wed_sector_code = cal_entry.get('wed') if cal_entry.get('wed') != 'V' else None
            # Check wedSectorOverride from Firestore
            wed_override = firestore_value(fw_data.get('wedSectorOverride'))
            if isinstance(wed_override, dict) and (wed_override.get('isOff') or wed_override.get('sector')):
                if wed_override.get('isOff'):
                    wed_sector_code = None
                else:
                    wed_override_sector = wed_override.get('sector')
                    if wed_override_sector:
                        wed_sector_code = '_OVERRIDE_'
                        wed_sector_name_override = wed_override_sector

            if wed_sector_code and wed_sector_code != '_OVERRIDE_':
                wed_sector = get_sector_name(wed_sector_code, True)
            elif wed_sector_code == '_OVERRIDE_':
                wed_sector = wed_sector_name_override
            else:
                wed_sector = None

            if wed_sector and not (wed_cancelled or wed_shifted):
                setters_str = format_setters(wed_setters)
                title = f"Limit — {wed_sector}"
                if setters_str:
                    title += f" | {setters_str}"

                events = list_events_on_date(service, wed_date)
                event = find_event(events, 'Limit')

                if event:
                    if event.get('summary') != title:
                        update_event(service, event['id'], title)
                        updated += 1
                else:
                    create_event(service, title, wed_date, '07:15:00', '15:00:00')
                    created += 1

                # Sundavání Limit (day before)
                if wed_sundavaci:
                    sun_date = (datetime.strptime(wed_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
                    sun_setters = format_setters(wed_sundavaci)
                    sun_title = f"Sundavání Limit | {sun_setters}"
                    if wed_myti:
                        sun_title += f" | mytí: {wed_myti}"

                    events = list_events_on_date(service, sun_date)
                    event = find_event(events, 'Sundavání Limit')

                    if event:
                        if event.get('summary') != sun_title:
                            update_event(service, event['id'], sun_title)
                            updated += 1
                    else:
                        create_event(service, sun_title, sun_date, '20:00:00', '22:00:00')
                        created += 1
                else:
                    # No sundavači — delete any existing Sundavání Limit event
                    sun_date = (datetime.strptime(wed_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
                    events = list_events_on_date(service, sun_date)
                    event = find_event(events, 'Sundavání Limit')
                    if event:
                        delete_event(service, event['id'])
                        deleted += 1
            else:
                # No Limit this week — delete any wrong Limit event on wed_date
                events = list_events_on_date(service, wed_date)
                event = find_event(events, 'Limit')
                if event:
                    delete_event(service, event['id'])
                    deleted += 1
                # Also delete Sundavání Limit (day before)
                sun_date = (datetime.strptime(wed_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
                events = list_events_on_date(service, sun_date)
                event = find_event(events, 'Sundavání Limit')
                if event:
                    delete_event(service, event['id'])
                    deleted += 1

            # Tělocvična (Thursday)
            if cal_entry.get('thu'):
                setters_str = format_setters(thu_setters)
                title = "Tělocvična"
                if setters_str:
                    title += f" | {setters_str}"

                events = list_events_on_date(service, thu_date)
                event = find_event(events, 'Tělocvična')

                if event:
                    if event.get('summary') != title:
                        update_event(service, event['id'], title)
                        updated += 1
                else:
                    create_event(service, title, thu_date, '08:00:00', '12:00:00')
                    created += 1

        result = f"✓ Sync completed: created={created}, updated={updated}, deleted={deleted}"
        print(result)
        return result, 200

    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return f"ERROR: {e}", 500
