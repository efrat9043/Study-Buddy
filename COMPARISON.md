# Study Buddy – השוואה בין מימוש API למימוש SDK

## מה בנינו

Study Buddy הוא סוכן AI קטן שמקבל חומר לימודי ופועל בשני שלבים:

1. **החלטה** – המודל מנתח את החומר ובוחר פעולה אחת מתוך שלוש:
   `generate_questions` (החומר מתאים), `request_more_material` (חסר חומר), `cannot_proceed` (לא חומר לימודי).
2. **ביצוע** – הקוד פועל לפי ההחלטה. רק אם הוחלט ליצור שאלות – נשלחת קריאה שנייה שמייצרת 5 שאלות (שאלה, תשובה, הסבר, רמת קושי).

הסוכן מומש פעמיים, עם אותו ספק (OpenAI), אותו מודל, אותם פרומפטים ואותה לוגיקה:

| גרסה | תיקייה | דרך ההתקשרות |
|---|---|---|
| API | `api_version/` | בקשות HTTP ידניות עם הספרייה `requests` |
| SDK | `sdk_version/` | הספרייה הרשמית של OpenAI – `openai` |

---

## מה זהה בשתי הגרסאות

הפרומפטים, ה-JSON Schemas, בדיקת התקינות של השאלות (`validate_questions`), מנגנון ההחלטה (`decide_action`, `generate_questions`, `run_agent`) וקריאת ההגדרות מ-`.env`.

**ההבדל היחיד הוא הפונקציה שמדברת עם השרת – `call_model`.**

---

## ההבדל בקוד – צד מול צד

### 1. שליחת הבקשה

**API** – בונים הכול בעצמנו: כתובת, כותרות, גוף הבקשה (`build_request_body`, `send_request`):

```python
API_URL = "https://api.openai.com/v1/responses"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}
body = {"model": model, "instructions": instructions, "input": study_text, ...}
response = requests.post(API_URL, headers=headers, json=body, timeout=120)
```

**SDK** – קוראים לפונקציה. ה-SDK יודע את הכתובת, בונה את הכותרות ושולח:

```python
client = OpenAI(api_key=api_key, timeout=120)
response = client.responses.create(model=model, instructions=instructions, input=study_text, ...)
```

### 2. טיפול בשגיאות

**API** – בודקים בעצמנו את קוד הסטטוס, ומחלצים את הודעת השגיאה מתוך ה-JSON (`get_error_message`):

```python
if response.status_code != 200:
    message = response.json()["error"]["message"]
    raise StudyBuddyError(f"HTTP {response.status_code}: {message}")
```

**SDK** – כל שגיאה מגיעה כ-Exception מסוג מתאים, שכבר מכיל את הפרטים:

```python
except openai.APIStatusError as error:
    raise StudyBuddyError(f"HTTP {error.status_code}: {error.message}")
```

### 3. חילוץ הטקסט מהתשובה

**API** – התשובה היא מילון מקונן; צריך לדעת את המבנה ולחפש בו ידנית (`extract_output_text`):

```python
for item in response_data.get("output", []):
    if item.get("type") != "message":
        continue
    for part in item.get("content", []):
        if part.get("type") == "output_text":
            return part["text"]
```

**SDK** – שדה מוכן:

```python
response.output_text
```

---

## טבלת השוואה

| נושא | API | SDK |
|---|---|---|
| כתובת השרת | כתובה בקוד (`API_URL`) | ה-SDK יודע אותה |
| אימות (מפתח) | בונים כותרת `Authorization: Bearer ...` | `OpenAI(api_key=...)` |
| גוף הבקשה | בונים dict בעצמנו | פרמטרים של פונקציה |
| שגיאות HTTP | בדיקת `status_code` + חילוץ הודעה | Exceptions מוכנים (`AuthenticationError`, `RateLimitError`...) |
| קריאת התשובה | מעבר ידני על מילון | `response.output_text`, שדות עם שמות (`response.status`) |
| ניסיון חוזר בשגיאה זמנית | אין (היה צריך לכתוב) | אוטומטי – עד 2 ניסיונות |
| עזרה בעורך (השלמה אוטומטית) | אין – מילון עם מחרוזות | יש – העורך מכיר את השדות |
| תלות חיצונית | `requests` בלבד | ספריית `openai` (ועוד ספריות שהיא מביאה) |
| שקיפות | רואים בדיוק מה נשלח ומה חוזר | הפרטים מוסתרים בתוך ה-SDK |
| גודל הקובץ | 235 שורות | 199 שורות |
| פונקציות תקשורת | 5 (`build_request_body`, `send_request`, `get_error_message`, `extract_output_text`, `call_model`) | 1 (`call_model`) |

---

## מה ה-SDK **לא** עשה בשבילנו

- **בדיקת סירוב** של המודל ובדיקה **שהתשובה לא נקטעה** – נשארו בקוד בשתי הגרסאות.
- **אימות התוכן** – שיש בדיוק 5 שאלות ושכל השדות מלאים – נשאר בשתי הגרסאות.
- **מנגנון ההחלטה** – ה-SDK הוא רק דרך תקשורת; הוא לא הופך את הקוד לסוכן.

---

## מסקנות

**יתרונות ה-SDK:** פחות קוד לכתוב ולתחזק, פחות מקום לטעויות (שם שדה שגוי, כותרת חסרה), שגיאות ברורות, ניסיונות חוזרים אוטומטיים, והשלמה אוטומטית בעורך.

**יתרונות ה-API הישיר:** שקיפות מלאה – רואים ומבינים בדיוק את בקשת ה-HTTP; אין תלות בספרייה של הספק; עובד מכל שפה וסביבה, גם כשאין SDK.

**בפועל:** ה-SDK הוא "עטיפה" מעל אותן קריאות HTTP בדיוק. בפרויקט אמיתי בדרך כלל נבחר ב-SDK; הבנת ה-API הישיר עוזרת להבין מה ה-SDK עושה מאחורי הקלעים ולאתר תקלות.

---

## הרצה

```powershell
.\.venv\Scripts\python.exe api_version\main.py sample_lesson.txt
.\.venv\Scripts\python.exe sdk_version\main.py sample_lesson.txt
```
