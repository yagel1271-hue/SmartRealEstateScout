# Smart Real Estate Scout

מערכת בענן לאיתור, ניתוח ודירוג דירות להשקעה – פתח תקווה, 1.0–1.8 מיליון ₪.
אין צורך להתקין דבר במחשב: הכול רץ ב-GitHub Actions, הדשבורד ב-Streamlit Community Cloud, וההתראות ב-Telegram.

> הציון והערכות השווי הם כלי סינון בלבד ואינם שומה או המלצת השקעה.

## איך זה עובד

| רכיב | איפה | מה עושה |
|---|---|---|
| קליטת מודעות | בוט Telegram + `inbox/listings.csv` | אתה שולח קישור/טקסט של מודעה; המערכת מחלצת מחיר, חדרים, מ"ר, קומה, כתובת ומאפיינים |
| עסקאות השוואה | GovMap (רשות המסים) – אוטומטי | עסקאות שנרשמו בפועל סביב כל נכס |
| ניתוח | קוד Python דטרמיניסטי | מחיר למ"ר מול עסקאות, הערכת שווי, עלויות רכישה, תשואה ב-3 תרחישים, ציון 0–100 עם פירוט |
| דוח יומי | GitHub Actions, ~08:00 שעון ישראל | הזדמנויות מובילות, חדשות, ירידות מחיר |
| קליטה ועדכון | GitHub Actions, כל שעתיים | קורא הודעות מהבוט, מושך עסקאות, מנתח, שולח התראה מיידית מעל ציון 80 |
| דשבורד | Streamlit Community Cloud (אפליקציה פרטית) | סקירה, טבלת נכסים עם סינון, כרטיס נכס, עסקאות, הגדרות |

## למה אין סריקה אוטומטית של יד2/מדלן

תקנון יד2 אוסר במפורש איסוף נתונים באמצעים אוטומטיים (רובוטים, scrapers). לפי עקרונות הפרויקט המערכת לא עוקפת זאת.
החלופה החוקית: אתה (או התראות החיפוש של יד2 עצמה) מאתר מודעה → שולח אותה לבוט בלחיצה → המערכת מנתחת אותה מול נתונים רשמיים.
ראה [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## הגדרות

`config/settings.json` – עיר, תקציב, שעת דוח, סף התראה ומשקולות הדירוג. עורכים ישירות ב-GitHub (עיפרון → Commit).
סודות (Telegram) – רק ב-GitHub → Settings → Secrets and variables → Actions:
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

## פקודות (לפיתוח)

```
python -m app.main daily [--scheduled]   # הכול: קליטה, עסקאות, ניתוח, התראות, דוח
python -m app.main intake | comps | analyze | alerts | report [--send]
python -m app.main probe                 # בדיקת זמינות מקורות רשמיים
python -m pytest -q
streamlit run app/dashboard/Home.py
```

## מבנה

```
app/collectors/     govmap (עסקאות רשמיות), telegram_intake, manual_csv
app/database/       סכמת SQLAlchemy (SQLite כעת, מוכן ל-PostgreSQL)
app/services/       text_parser, ingest (כפילויות + היסטוריית מחיר), report, probe
app/analysis/       comps, finance, scoring, analyzer, assumptions (כל הנחה עם מקור ותאריך)
app/notifications/  telegram
app/dashboard/      Home.py (Streamlit, עברית RTL)
.github/workflows/  daily, intake, probe, tests
config/settings.json  inbox/listings.csv  data/scout.db
```
