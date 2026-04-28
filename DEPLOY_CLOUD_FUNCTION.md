# Deploy Sync Calendar na Firebase Cloud Functions

Tento script synchronizuje Google Calendar s aktuálním CAL z aplikace. Běží 3× denně (6:30, 12:30, 18:30) automaticky bez potřeby tvého počítače.

## Krok 1: Nastav Cloud Scheduler trigger

1. Jdi na [Google Cloud Console](https://console.cloud.google.com/)
2. Vyber projekt **climbing-app-d0074**
3. Jdi na **Cloud Scheduler** (hledej v horní liště)
4. Klikni **CREATE JOB**
5. Vyplň:
   - **Name**: `climbing-calendar-sync`
   - **Frequency**: `30 6,12,18 * * *` (6:30, 12:30, 18:30 CET)
   - **Timezone**: Europe/Prague
   - **Execution timeout**: 540 seconds
6. **CONTINUE**
7. Vyber typ: **HTTP**
8. URL: `https://europe-west1-climbing-app-d0074.cloudfunctions.net/sync_calendar`
9. Metoda: POST
10. Klikni **CREATE**

## Krok 2: Deploy Cloud Function

1. V Cloud Console jdi na **Cloud Functions**
2. Klikni **CREATE FUNCTION**
3. Vyplň:
   - **Environment**: Python 3.11
   - **Function name**: `sync_calendar`
   - **Region**: europe-west1
   - **Trigger type**: Cloud Pub/Sub (nebo Cloud Scheduler — pro scheduler se nastaví automaticky)
   - **Authentication**: Require authentication (zaškrtnuté)
4. V editoru:
   - **Runtime settings**: vyvol secrets (viz Krok 3)
   - `main.py`: zkopíruj obsah `sync_calendar.py`
   - `requirements.txt`: zkopíruj obsah `requirements.txt`
5. Klikni **DEPLOY** (čeká 2-3 minuty)

## Krok 3: Nastavení Service Account (Google Calendar API access)

Cloud Function potřebuje přístup k Google Calendar. Firebase má builtin service account, ale musíš mu dát permissions:

1. V Cloud Console jdi na **Service Accounts**
2. Najdi `firebase-adminsdk-...@climbing-app-d0074.iam.gserviceaccount.com`
3. Klikni na ni → **KEYS** → **ADD KEY** → **Create new key** → **JSON** → **CREATE**
4. V Cloud Function settings přidej **Environment variable**:
   - `GOOGLE_APPLICATION_CREDENTIALS`: obsah JSON klíče (base64 encoded)
   - NEBO nech builtin service account (Firebase SDK to používá automaticky)

Cloud Function se spouští pod Service Account, který má Firebase Admin SDK přístup. Zaměř se na **Calendar API permission**:

1. Jdi na [Google API Console](https://console.developers.google.com/)
2. Vyber projekt **climbing-app-d0074**
3. Jdi na **APIs & Services** → **Enabled APIs**
4. Hledej **Google Calendar API** → pokud není → **ENABLE**
5. Jdi na **Service Accounts** → Firebase service account → **EDIT**
6. V **Delegated domain-wide authority** (pokud je) → zaměř se na scopes
7. Jinak: v IAM přidej roli **Editor** nebo **Calendar API Manager** pro service account

**Jednodušší postup:**
1. Jdi na [Google OAuth Consent Screen](https://console.cloud.google.com/apis/consent)
2. Přidej scopes: `https://www.googleapis.com/auth/calendar`
3. Přidej test uživatele: `teamlanovka@gmail.com`

## Krok 4: Test

```bash
# Test lokálně
python3 -m pip install -r requirements.txt
python3 -c "from sync_calendar import sync_calendar; print(sync_calendar(None))"

# Nebo v Cloud Console: Cloud Scheduler → Klikni job → **FORCE RUN**
```

## Co se stane

Při spuštění:
1. Stáhne aktuální CAL z GitHubu
2. Načte Firestore data (stavěči, sundavači)
3. Vypočítá správné sektory a data
4. Synchronizuje Google Calendar (vytváří/aktualizuje/maže eventy)
5. Vrací report: `created=X, updated=Y, deleted=Z`

## Pokud něco nejde

- **Calendar API je disabled**: V Cloud Console → APIs & Services → Enable **Google Calendar API**
- **Permission denied**: Service Account musí mít přístup do `teamlanovka@gmail.com` kalendáře. Přidej ji do sdílení.
- **Firestore chyby**: Service Account potřebuje Firestore read permission (Firebase role to dělá automaticky)
- **GitHub network error**: Script čeká 10 sekund na odpověď, pokud je GitHub down → fallback na Firestore `_monSector`/`_wedSector`

---

**Výsledek:** Kalendář se automaticky synchronizuje 3× denně bez tvého přičinění. Stačí pushnout změny do GitHubu.
