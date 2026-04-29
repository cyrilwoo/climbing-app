"""
Firebase Cloud Function: Sync climbing app schedule to Google Calendar (teamlanovka@gmail.com)
Runs on schedule: 3x daily (6:30, 12:30, 18:30)

Reads CAL from GitHub source, reads Firestore data, syncs to Google Calendar.
"""

import functions_framework
import requests
import re
from datetime import datetime, timedelta
from google.cloud import firestore
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


# ─── helpers ────────────────────────────────────────────────────────────────

def parse_cal_from_github():
    """Fetch index.html and parse CAL object"""
    try:
        resp = requests.get(
            'https://raw.githubusercontent.com/cyrilwoo/climbing-app/main/index.html',
            timeout=10
        )
        resp.raise_for_status()
        html = resp.text

        match = re.search(r"const CAL = \{(.*?)\n    \};", html, re.DOTALL)
        if not match:
            print("ERROR: CAL not found in index.html")
            return {}

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
                fm = re.search(rf"{field}:\s*([A-Z0-9]+)?", fields_str)
                if fm and fm.group(1):
                    entry[field] = fm.group(1)
            cal[week_id] = entry

        return cal

    except Exception as e:
        print(f"ERROR parsing CAL from GitHub: {e}")
        return {}


def get_calendar_service():
    return googleapiclient.discovery.build('calendar', 'v3')


def list_events_on_date(service, date_str):
    """List events on a specific date"""
    start = f"{date_str}T00:00:00Z"
    end   = f"{date_str}T23:59:59Z"
    try:
        result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start, timeMax=end,
            singleEvents=True, orderBy='startTime'
        ).execute()
        return result.get('items', [])
    except Exception as e:
        print(f"ERROR listing events on {date_str}: {e}")
        return []


def find_event(events, prefix):
    for ev in events:
        if ev.get('summary', '').startswith(prefix):
            return ev
    return None


def _delete(service, event_id):
    try:
        service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
        return True
    except Exception as e:
        print(f"ERROR deleting {event_id}: {e}")
        return False


def _create(service, summary, date_str, start_time, end_time):
    try:
        event = {
            'summary': summary,
            'start': {'dateTime': f"{date_str}T{start_time}", 'timeZone': 'Europe/Prague'},
            'end':   {'dateTime': f"{date_str}T{end_time}",   'timeZone': 'Europe/Prague'},
            'colorId': '3',
            'reminders': {'useDefault': False},
        }
        service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        return True
    except Exception as e:
        print(f"ERROR creating '{summary}' on {date_str}: {e}")
        return False


def _update(service, event_id, summary):
    try:
        event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()
        event['summary'] = summary
        service.events().update(calendarId=CALENDAR_ID, eventId=event_id, body=event).execute()
        return True
    except Exception as e:
        print(f"ERROR updating {event_id}: {e}")
        return False


def sync_event(service, prefix, date, title, start_time, end_time, stats):
    """
    Ensure an event with `prefix` on `date` matches `title`.
    If title is None → delete the event if it exists.
    Returns nothing; mutates stats dict.
    """
    events = list_events_on_date(service, date)
    ev = find_event(events, prefix)
    if title is None:
        if ev:
            _delete(service, ev['id'])
            stats['deleted'] += 1
    else:
        if ev:
            if ev.get('summary') != title:
                _update(service, ev['id'], title)
                stats['updated'] += 1
        else:
            _create(service, title, date, start_time, end_time)
            stats['created'] += 1


def clear_on_dates(service, prefix, *dates, stats):
    """Delete events with `prefix` on any of the given dates (deduped)."""
    for d in dict.fromkeys(d for d in dates if d):  # dedup, preserve order
        events = list_events_on_date(service, d)
        ev = find_event(events, prefix)
        if ev:
            _delete(service, ev['id'])
            stats['deleted'] += 1


def day_before(date_str):
    return (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')


def firestore_value(val):
    """Extract value from Firestore field (supports both REST dict wrappers and native Python SDK types)"""
    if val is None:
        return None
    if isinstance(val, list):
        return [firestore_value(v) for v in val]
    if isinstance(val, str):
        return None if val == '__NULL__' else val
    if isinstance(val, bool):
        return val
    if isinstance(val, dict):
        if 'nullValue' in val:
            return None
        if 'stringValue' in val:
            v = val['stringValue']
            return None if v == '__NULL__' else v
        if 'arrayValue' in val:
            return [firestore_value(v) for v in val['arrayValue'].get('values', [])]
        if 'booleanValue' in val:
            return val['booleanValue']
        if 'mapValue' in val:
            fields = val['mapValue'].get('fields', {})
            return {k: firestore_value(v) for k, v in fields.items()}
    return val


def format_setters(setters, lano=None):
    active = [s for s in (setters or []) if s and s != '__NULL__']
    if lano and lano != '__NULL__':
        active.append(lano)
    return ', '.join(active) if active else None


# ─── main sync ──────────────────────────────────────────────────────────────

@functions_framework.http
def sync_calendar(request):
    try:
        cal = parse_cal_from_github()
        if not cal:
            return "ERROR: Could not parse CAL", 500

        service = get_calendar_service()
        now = datetime.now()
        stats = {'created': 0, 'updated': 0, 'deleted': 0}

        weeks_to_sync = [
            wid for wid in sorted(cal.keys())
            if -7 <= (datetime.strptime(wid, '%Y-%m-%d') - now).days <= 130
        ]

        for week_id in weeks_to_sync:
            cal_entry = cal[week_id]

            # ── Firestore data ──────────────────────────────────────────────
            try:
                doc = db.collection('weeks').document(week_id).get()
                fw = doc.to_dict() or {}
            except:
                fw = {}

            mon_setters  = firestore_value(fw.get('monday'))          or []
            mon_lano     = firestore_value(fw.get('mondayLano'))
            wed_setters  = firestore_value(fw.get('wednesday'))        or []
            thu_setters  = firestore_value(fw.get('thursday'))         or []
            mon_sun      = firestore_value(fw.get('mondaySundavaci'))  or []
            wed_sun      = firestore_value(fw.get('wednesdaySundavaci')) or []
            mon_myti     = firestore_value(fw.get('mondayMyti'))
            wed_myti     = firestore_value(fw.get('wednesdayMyti'))
            mon_cancelled = firestore_value(fw.get('_monCancelled'))
            wed_cancelled = firestore_value(fw.get('_wedCancelled'))
            mon_shifted   = firestore_value(fw.get('_monShifted'))
            wed_shifted   = firestore_value(fw.get('_wedShifted'))

            # ── Effective dates ─────────────────────────────────────────────
            week_dt = datetime.strptime(week_id, '%Y-%m-%d')

            # _monDate / _wedDate / _thuDate are computed by the app as override ?? default
            raw_mon = firestore_value(fw.get('_monDate')) or firestore_value(fw.get('monDateOverride'))
            raw_wed = firestore_value(fw.get('_wedDate')) or firestore_value(fw.get('wedDateOverride'))
            raw_thu = firestore_value(fw.get('_thuDate')) or firestore_value(fw.get('thuDateOverride'))

            mon_date = raw_mon if raw_mon else week_id
            wed_default = (week_dt + timedelta(days=3 if cal_entry.get('wed') == 'D' else 2)).strftime('%Y-%m-%d')
            wed_date = raw_wed if raw_wed else wed_default
            thu_default = (week_dt + timedelta(days=3)).strftime('%Y-%m-%d')
            thu_date = raw_thu if raw_thu else thu_default

            # ── Sector overrides ────────────────────────────────────────────
            def resolve_sector(cal_code, override_field, sector_dict):
                """Return (sector_name, is_off) respecting Firestore override."""
                override = firestore_value(fw.get(override_field))
                if isinstance(override, dict) and (override.get('isOff') or override.get('sector')):
                    if override.get('isOff'):
                        return None, True
                    sec = override.get('sector')
                    return (sec, False) if sec else (None, False)
                # Fall back to CAL
                if cal_code and cal_code != 'V':
                    name = sector_dict.get(cal_code)
                    return (name, False)
                return None, (cal_code == 'V')

            mon_sector, mon_is_off = resolve_sector(
                cal_entry.get('mon'), 'monSectorOverride', SECTORS_MON)
            wed_sector, wed_is_off = resolve_sector(
                cal_entry.get('wed'), 'wedSectorOverride', SECTORS_WED)
            thu_code = cal_entry.get('thu')  # only TG, no override

            # ── LANOVKA ─────────────────────────────────────────────────────
            lanovka_active = mon_sector and not mon_is_off and not (mon_cancelled or mon_shifted)

            if lanovka_active:
                setters_str = format_setters(mon_setters, mon_lano)
                title = f"Lanovka — {mon_sector}"
                if setters_str:
                    title += f" | {setters_str}"

                # Delete stale event from default (week_id) if date was moved
                if mon_date != week_id:
                    clear_on_dates(service, 'Lanovka', week_id, stats=stats)

                sync_event(service, 'Lanovka', mon_date, title, '07:15:00', '15:00:00', stats)

                # Sundavání
                sun = day_before(mon_date)
                if mon_date != week_id:
                    old_sun = day_before(week_id)
                    if old_sun != sun:
                        clear_on_dates(service, 'Sundavání Lanovka', old_sun, stats=stats)

                if mon_sun:
                    s = format_setters(mon_sun)
                    sun_title = f"Sundavání Lanovka | {s}"
                    if mon_myti:
                        sun_title += f" | mytí: {mon_myti}"
                    sync_event(service, 'Sundavání Lanovka', sun, sun_title, '20:00:00', '22:00:00', stats)
                else:
                    sync_event(service, 'Sundavání Lanovka', sun, None, '', '', stats)

            else:
                # No Lanovka — delete event and sundavání at ALL possible positions
                clear_on_dates(service, 'Lanovka',
                               mon_date, week_id,
                               stats=stats)
                clear_on_dates(service, 'Sundavání Lanovka',
                               day_before(mon_date), day_before(week_id),
                               stats=stats)

            # ── LIMIT ───────────────────────────────────────────────────────
            limit_active = wed_sector and not wed_is_off and not (wed_cancelled or wed_shifted)

            if limit_active:
                setters_str = format_setters(wed_setters)
                title = f"Limit — {wed_sector}"
                if setters_str:
                    title += f" | {setters_str}"

                # Delete stale event from default date if date was moved
                if wed_date != wed_default:
                    clear_on_dates(service, 'Limit', wed_default, stats=stats)

                sync_event(service, 'Limit', wed_date, title, '07:15:00', '15:00:00', stats)

                # Sundavání
                sun = day_before(wed_date)
                if wed_date != wed_default:
                    old_sun = day_before(wed_default)
                    if old_sun != sun:
                        clear_on_dates(service, 'Sundavání Limit', old_sun, stats=stats)

                if wed_sun:
                    s = format_setters(wed_sun)
                    sun_title = f"Sundavání Limit | {s}"
                    if wed_myti:
                        sun_title += f" | mytí: {wed_myti}"
                    sync_event(service, 'Sundavání Limit', sun, sun_title, '20:00:00', '22:00:00', stats)
                else:
                    sync_event(service, 'Sundavání Limit', sun, None, '', '', stats)

            else:
                # No Limit — delete at ALL possible positions
                # (overridden date, default +2, +3, and the old +2/+3 around week start)
                all_limit_dates = {
                    wed_date,
                    wed_default,
                    (week_dt + timedelta(days=2)).strftime('%Y-%m-%d'),
                    (week_dt + timedelta(days=3)).strftime('%Y-%m-%d'),
                }
                for d in all_limit_dates:
                    clear_on_dates(service, 'Limit', d, stats=stats)
                    clear_on_dates(service, 'Sundavání Limit', day_before(d), stats=stats)

            # ── TĚLOCVIČNA ──────────────────────────────────────────────────
            if thu_code:
                setters_str = format_setters(thu_setters)
                title = "Tělocvična"
                if setters_str:
                    title += f" | {setters_str}"

                # Delete stale event from default Thursday if date was moved
                if thu_date != thu_default:
                    clear_on_dates(service, 'Tělocvična', thu_default, stats=stats)

                sync_event(service, 'Tělocvična', thu_date, title, '08:00:00', '12:00:00', stats)
            else:
                # No Tělocvična this week — delete at both possible positions
                clear_on_dates(service, 'Tělocvična', thu_date, thu_default, stats=stats)

        result = f"✓ Sync completed: created={stats['created']}, updated={stats['updated']}, deleted={stats['deleted']}"
        print(result)
        return result, 200

    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return f"ERROR: {e}", 500
