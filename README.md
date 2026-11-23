# Smart Real Estate Scout

מערכת מקומית לאיתור, ניתוח ודירוג דירות להשקעה – גרסה ראשונה: פתח תקווה, 1.0–1.8 מיליון ₪.

> הציון והערכות השווי הם כלי סינון בלבד ואינם שומה או המלצת השקעה.

## התקנה ראשונה (Windows)

1. התקן **Python 3.12** (לסמן "Add python.exe to PATH") ו-**Git for Windows**.
2. שכפל את הפרויקט:
   ```
   git clone <כתובת-הריפו> SmartRealEstateScout
   ```
3. לחץ פעמיים על `setup.bat`. הוא יוצר סביבה וירטואלית, מתקין חבילות, יוצר `.env` ומריץ בדיקות.

## פקודות

| פעולה | פקודה |
|---|---|
| בדיקת סביבה | `.venv\Scripts\python -m app.main doctor` |
| הצגת הגדרות | `.venv\Scripts\python -m app.main config` |
| הרצת בדיקות | `.venv\Scripts\python -m pytest` |
| סריקה | `run_scanner.bat` (מימוש בשלב 5) |
| Dashboard | `run_dashboard.bat` (מימוש בשלב 4) |

## מבנה

```
app/
  config.py          הגדרות (נקראות מ-.env)
  logging_setup.py   לוגים ל-logs/scout.log
  main.py            נקודת כניסה (CLI)
  collectors/        איסוף נתונים ממקורות מותרים
  database/          מסד נתונים
  analysis/          ניתוח פיננסי ונדל"ני, דירוג
  dashboard/         ממשק Streamlit
  notifications/     Telegram
  scheduler/         תזמון
  services/          שירותים משותפים (doctor וכו')
data/  logs/  tests/  scripts/  docs/
```

## אבטחה

- סודות (Telegram Token) רק בקובץ `.env`, שאינו נשמר ב-Git.
- תיקיות `data/` ו-`logs/` אינן נשמרות ב-Git.

## סטטוס

ראה [docs/ROADMAP.md](docs/ROADMAP.md).
