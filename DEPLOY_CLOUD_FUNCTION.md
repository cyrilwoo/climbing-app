# Deploy synccalendar (Cloud Run + Cloud Scheduler)

`sync_calendar.py` synchronizuje plánovač s Google Calendar `teamlanovka@gmail.com`.
Běží jako **Cloud Run service `synccalendar`** v projektu `climbing-app-d0074`
(region `europe-west1`) a Cloud Scheduler ho volá 3× denně.

> ⚠️ **Push do GitHubu sám o sobě nestačí.** Cloud Run drží snapshot kódu —
> po každé změně `sync_calendar.py`, `requirements.txt` nebo `Dockerfile` musíš
> ručně redeployovat (viz níže).
>
> Naopak změny v `index.html` (zejména v `CAL`) se projeví **bez redeploye** —
> funkce při každém běhu fetchuje `index.html` z `raw.githubusercontent.com`.

## Předpoklady

- `gcloud` CLI na `~/google-cloud-sdk/bin/gcloud` (už nainstalovaný)
- Auth přes účet s rolí `owner` v `climbing-app-d0074`
  (aktuálně `alfred.limitboulder@gmail.com`)
- Python 3.11+ pro `gcloud` (default 3.9 vyhazuje warning)
- Aktivní projekt: `gcloud config set project climbing-app-d0074`

## Redeploy — jeden příkaz

Po editaci `sync_calendar.py` (nebo `Dockerfile` / `requirements.txt`):

```bash
export CLOUDSDK_PYTHON=/Users/cyrilkratochvil/.pyenv/versions/3.11.9/bin/python3.11
cd /Users/cyrilkratochvil/CLAUDE/climbing-app
~/google-cloud-sdk/bin/gcloud run deploy synccalendar \
  --source=. --region=europe-west1 --quiet
```

Build trvá ~5 min (Cloud Build → push do Artifact Registry → nová Cloud Run
revize). Až se vrátí `Service [synccalendar] revision [synccalendar-XXXXX-xxx]
has been deployed and is serving 100 percent of traffic.`, je hotovo.

## Spustit sync ručně (bez čekání na scheduler)

```bash
~/google-cloud-sdk/bin/gcloud scheduler jobs run \
  climbing-calendar-sync --location=europe-west1
```

Job naplánuje POST na Cloud Run URL. Sync běží ~15 min (čte CAL z GitHubu,
prochází Firestore týdny, mažé/vytváří/upravuje eventy).

Synchronní variantu s okamžitým výstupem dostaneš přes curl + auth token:

```bash
TOKEN=$(~/google-cloud-sdk/bin/gcloud auth print-identity-token)
URL=$(~/google-cloud-sdk/bin/gcloud run services describe synccalendar \
  --region=europe-west1 --format='value(status.url)')
curl -X POST -H "Authorization: Bearer $TOKEN" "$URL" --max-time 540
# → ✓ Sync completed: created=X, updated=Y, deleted=Z
```

## Logy

```bash
~/google-cloud-sdk/bin/gcloud run services logs read synccalendar \
  --region=europe-west1 --limit=30
```

Hledat `✓ Sync completed:` pro výsledek jednotlivých běhů.

## Scheduler — frekvence

```bash
~/google-cloud-sdk/bin/gcloud scheduler jobs describe \
  climbing-calendar-sync --location=europe-west1
```

Default: `30 6,12,18 * * *` (CEST), tj. 6:30, 12:30, 18:30. Upravit lze přes
`gcloud scheduler jobs update http climbing-calendar-sync --schedule="..."`.

## Co se přesně synchronizuje

Per týden v rozsahu `−7 dní … +130 dní` od dneška, na základě CAL z `index.html`
a Firestore stavu:

- **Lanovka** — `Lanovka — {sektor} | {stavěči} | lano-stavěč: {lano}` (lano
  jen v týdnech, kde `has_lano_build` vrací True — viz `sync_calendar.py`)
- **Limit** — `Limit — {sektor} | {stavěči}`
- **Tělocvična** — `Tělocvična | {stavěči}` (jen pokud CAL má `thu: TG` —
  červen–srpen je vypnutý)
- **Sundavání Lanovka/Limit** — den předem 20:00–22:00, `| mytí: {jméno}`
  pokud je vyplněno

Sektor-override (posunuté/zrušené týdny) i datum-override (přesun na jiný den)
jsou respektovány.

## Architekturní pozn.

- Aplikace byla původně deployed jako Cloud Function (1st gen), ale teď
  běží jako **Cloud Run service**. Cloud Functions API v projektu **není**
  enabled — `gcloud functions list` selže.
- Image se buildí z `Dockerfile` (Python 3.11 slim + `functions-framework`
  jako HTTP wrapper).
- Service Account: `firebase-adminsdk-fbsvc@climbing-app-d0074.iam.gserviceaccount.com`
  (má Calendar API permissions + Firestore admin).
- Scheduler volá Cloud Run s OIDC tokenem; veřejně je endpoint neauth (vrací
  403 na GET).
