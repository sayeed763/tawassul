"""
Quranic Read & Analytics — single-file Streamlit app
Tawassul — Quran Read & Analytics (single-file Streamlit app)
Run:  pip install "streamlit>=1.39" pandas  &&  streamlit run app.py

Keep these next to app.py:
* quran_roman_urdu.csv  – fixed Roman Urdu source (loaded automatically, never uploaded by users)
* fonts/ (optional)     – drop an Indo-Pak Quran .ttf/.otf here to use it as the Arabic font
Arabic text is downloaded once automatically on first start and cached in quran_arabic.json.
"""
import base64
import hashlib
import html
import io
import json
import re
import sqlite3
import urllib.request
from pathlib import Path

import pandas as pd
import streamlit as st

APP_NAME_EN = "Tawassul"
APP_NAME_AR = "تَوَسُّل"
LOGO_PATH = Path(__file__).resolve().parent / "logo.png"
ICON_PATH = Path(__file__).resolve().parent / "logo_icon.png"
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "quran_analytics.db")
CSV_PATH = BASE_DIR / "quran_roman_urdu.csv"      # fixed, bundled translation source
ARABIC_CACHE = BASE_DIR / "quran_arabic.json"     # written automatically after the first download
FONT_DIR = BASE_DIR / "fonts"
BISMILLAH_AR = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"
BISMILLAH_EN = "Bismillah ir-Rahman ir-Rahim"
BISMILLAH_UR = "Allah ke naam se jo bohat meherban, nihayat rahm karne wala hai."

# ───────────────────────── 1. STATIC DATA ─────────────────────────
# (arabic name, transliterated name, ayah count, K=Makki / D=Madani)
SURAHS = [
    ("الفاتحة", "Al-Fatihah", 7, "K"), ("البقرة", "Al-Baqarah", 286, "D"),
    ("آل عمران", "Ali 'Imran", 200, "D"), ("النساء", "An-Nisa", 176, "D"),
    ("المائدة", "Al-Ma'idah", 120, "D"), ("الأنعام", "Al-An'am", 165, "K"),
    ("الأعراف", "Al-A'raf", 206, "K"), ("الأنفال", "Al-Anfal", 75, "D"),
    ("التوبة", "At-Tawbah", 129, "D"), ("يونس", "Yunus", 109, "K"),
    ("هود", "Hud", 123, "K"), ("يوسف", "Yusuf", 111, "K"),
    ("الرعد", "Ar-Ra'd", 43, "D"), ("إبراهيم", "Ibrahim", 52, "K"),
    ("الحجر", "Al-Hijr", 99, "K"), ("النحل", "An-Nahl", 128, "K"),
    ("الإسراء", "Al-Isra", 111, "K"), ("الكهف", "Al-Kahf", 110, "K"),
    ("مريم", "Maryam", 98, "K"), ("طه", "Ta-Ha", 135, "K"),
    ("الأنبياء", "Al-Anbiya", 112, "K"), ("الحج", "Al-Hajj", 78, "D"),
    ("المؤمنون", "Al-Mu'minun", 118, "K"), ("النور", "An-Nur", 64, "D"),
    ("الفرقان", "Al-Furqan", 77, "K"), ("الشعراء", "Ash-Shu'ara", 227, "K"),
    ("النمل", "An-Naml", 93, "K"), ("القصص", "Al-Qasas", 88, "K"),
    ("العنكبوت", "Al-Ankabut", 69, "K"), ("الروم", "Ar-Rum", 60, "K"),
    ("لقمان", "Luqman", 34, "K"), ("السجدة", "As-Sajdah", 30, "K"),
    ("الأحزاب", "Al-Ahzab", 73, "D"), ("سبأ", "Saba", 54, "K"),
    ("فاطر", "Fatir", 45, "K"), ("يس", "Ya-Sin", 83, "K"),
    ("الصافات", "As-Saffat", 182, "K"), ("ص", "Sad", 88, "K"),
    ("الزمر", "Az-Zumar", 75, "K"), ("غافر", "Ghafir", 85, "K"),
    ("فصلت", "Fussilat", 54, "K"), ("الشورى", "Ash-Shura", 53, "K"),
    ("الزخرف", "Az-Zukhruf", 89, "K"), ("الدخان", "Ad-Dukhan", 59, "K"),
    ("الجاثية", "Al-Jathiyah", 37, "K"), ("الأحقاف", "Al-Ahqaf", 35, "K"),
    ("محمد", "Muhammad", 38, "D"), ("الفتح", "Al-Fath", 29, "D"),
    ("الحجرات", "Al-Hujurat", 18, "D"), ("ق", "Qaf", 45, "K"),
    ("الذاريات", "Adh-Dhariyat", 60, "K"), ("الطور", "At-Tur", 49, "K"),
    ("النجم", "An-Najm", 62, "K"), ("القمر", "Al-Qamar", 55, "K"),
    ("الرحمن", "Ar-Rahman", 78, "D"), ("الواقعة", "Al-Waqi'ah", 96, "K"),
    ("الحديد", "Al-Hadid", 29, "D"), ("المجادلة", "Al-Mujadila", 22, "D"),
    ("الحشر", "Al-Hashr", 24, "D"), ("الممتحنة", "Al-Mumtahanah", 13, "D"),
    ("الصف", "As-Saff", 14, "D"), ("الجمعة", "Al-Jumu'ah", 11, "D"),
    ("المنافقون", "Al-Munafiqun", 11, "D"), ("التغابن", "At-Taghabun", 18, "D"),
    ("الطلاق", "At-Talaq", 12, "D"), ("التحريم", "At-Tahrim", 12, "D"),
    ("الملك", "Al-Mulk", 30, "K"), ("القلم", "Al-Qalam", 52, "K"),
    ("الحاقة", "Al-Haqqah", 52, "K"), ("المعارج", "Al-Ma'arij", 44, "K"),
    ("نوح", "Nuh", 28, "K"), ("الجن", "Al-Jinn", 28, "K"),
    ("المزمل", "Al-Muzzammil", 20, "K"), ("المدثر", "Al-Muddaththir", 56, "K"),
    ("القيامة", "Al-Qiyamah", 40, "K"), ("الإنسان", "Al-Insan", 31, "D"),
    ("المرسلات", "Al-Mursalat", 50, "K"), ("النبأ", "An-Naba", 40, "K"),
    ("النازعات", "An-Nazi'at", 46, "K"), ("عبس", "Abasa", 42, "K"),
    ("التكوير", "At-Takwir", 29, "K"), ("الانفطار", "Al-Infitar", 19, "K"),
    ("المطففين", "Al-Mutaffifin", 36, "K"), ("الانشقاق", "Al-Inshiqaq", 25, "K"),
    ("البروج", "Al-Buruj", 22, "K"), ("الطارق", "At-Tariq", 17, "K"),
    ("الأعلى", "Al-A'la", 19, "K"), ("الغاشية", "Al-Ghashiyah", 26, "K"),
    ("الفجر", "Al-Fajr", 30, "K"), ("البلد", "Al-Balad", 20, "K"),
    ("الشمس", "Ash-Shams", 15, "K"), ("الليل", "Al-Layl", 21, "K"),
    ("الضحى", "Ad-Duha", 11, "K"), ("الشرح", "Ash-Sharh", 8, "K"),
    ("التين", "At-Tin", 8, "K"), ("العلق", "Al-Alaq", 19, "K"),
    ("القدر", "Al-Qadr", 5, "K"), ("البينة", "Al-Bayyinah", 8, "D"),
    ("الزلزلة", "Az-Zalzalah", 8, "D"), ("العاديات", "Al-Adiyat", 11, "K"),
    ("القارعة", "Al-Qari'ah", 11, "K"), ("التكاثر", "At-Takathur", 8, "K"),
    ("العصر", "Al-Asr", 3, "K"), ("الهمزة", "Al-Humazah", 9, "K"),
    ("الفيل", "Al-Fil", 5, "K"), ("قريش", "Quraysh", 4, "K"),
    ("الماعون", "Al-Ma'un", 7, "K"), ("الكوثر", "Al-Kawthar", 3, "K"),
    ("الكافرون", "Al-Kafirun", 6, "K"), ("النصر", "An-Nasr", 3, "D"),
    ("المسد", "Al-Masad", 5, "K"), ("الإخلاص", "Al-Ikhlas", 4, "K"),
    ("الفلق", "Al-Falaq", 5, "K"), ("الناس", "An-Nas", 6, "K"),
]

# Demo seed: {surah_id: [(arabic, roman_urdu), ...]}  — ayah numbers are list positions.
SEED = {
    1: [
        ("بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ", "Allah ke naam se jo bohat meherban, nihayat rahm karne wala hai."),
        ("الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ", "Tamam taarif Allah ke liye hai jo tamam jahanon ka palne wala hai."),
        ("الرَّحْمَٰنِ الرَّحِيمِ", "Bohat meherban, nihayat rahm karne wala."),
        ("مَالِكِ يَوْمِ الدِّينِ", "Roz-e-jaza ka malik."),
        ("إِيَّاكَ نَعْبُدُ وَإِيَّاكَ نَسْتَعِينُ", "Hum sirf teri hi ibadat karte hain aur sirf tujh hi se madad mangte hain."),
        ("اهْدِنَا الصِّرَاطَ الْمُسْتَقِيمَ", "Hamein seedhe raste par chala."),
        ("صِرَاطَ الَّذِينَ أَنْعَمْتَ عَلَيْهِمْ غَيْرِ الْمَغْضُوبِ عَلَيْهِمْ وَلَا الضَّالِّينَ",
         "Un logon ka raasta jin par tu ne inaam kiya, un ka nahin jin par ghazab hua aur na gumrahon ka."),
    ],
    103: [
        ("وَالْعَصْرِ", "Zamane ki qasam."),
        ("إِنَّ الْإِنسَانَ لَفِي خُسْرٍ", "Beshak insan khasare mein hai."),
        ("إِلَّا الَّذِينَ آمَنُوا وَعَمِلُوا الصَّالِحَاتِ وَتَوَاصَوْا بِالْحَقِّ وَتَوَاصَوْا بِالصَّبْرِ",
         "Siwaye un ke jo iman laye, nek amal kiye, aur ek doosre ko haq ki aur sabr ki talqeen karte rahe."),
    ],
    108: [
        ("إِنَّا أَعْطَيْنَاكَ الْكَوْثَرَ", "Beshak hum ne aap ko Kawthar ata ki."),
        ("فَصَلِّ لِرَبِّكَ وَانْحَرْ", "Pas apne rab ke liye namaz parhein aur qurbani karein."),
        ("إِنَّ شَانِئَكَ هُوَ الْأَبْتَرُ", "Beshak aap ka dushman hi be-nam-o-nishan hai."),
    ],
    109: [
        ("قُلْ يَا أَيُّهَا الْكَافِرُونَ", "Kah do: aye inkar karne walo!"),
        ("لَا أَعْبُدُ مَا تَعْبُدُونَ", "Main un ki ibadat nahin karta jin ki tum ibadat karte ho."),
        ("وَلَا أَنتُمْ عَابِدُونَ مَا أَعْبُدُ", "Aur na tum us ki ibadat karne wale ho jis ki main karta hoon."),
        ("وَلَا أَنَا عَابِدٌ مَا عَبَدتُّمْ", "Aur na main un ki ibadat karne wala hoon jin ki tum ne ibadat ki."),
        ("وَلَا أَنتُمْ عَابِدُونَ مَا أَعْبُدُ", "Aur na tum us ki ibadat karne wale ho jis ki main karta hoon."),
        ("لَكُمْ دِينُكُمْ وَلِيَ دِينِ", "Tumhare liye tumhara deen aur mere liye mera deen."),
    ],
    110: [
        ("إِذَا جَاءَ نَصْرُ اللَّهِ وَالْفَتْحُ", "Jab Allah ki madad aur fath aa jaye."),
        ("وَرَأَيْتَ النَّاسَ يَدْخُلُونَ فِي دِينِ اللَّهِ أَفْوَاجًا",
         "Aur aap logon ko Allah ke deen mein fauj dar fauj dakhil hote dekhein."),
        ("فَسَبِّحْ بِحَمْدِ رَبِّكَ وَاسْتَغْفِرْهُ إِنَّهُ كَانَ تَوَّابًا",
         "To apne rab ki hamd ke saath tasbeeh karein aur us se maghfirat mangein, beshak woh bada tauba qubool karne wala hai."),
    ],
    112: [
        ("قُلْ هُوَ اللَّهُ أَحَدٌ", "Kah do: woh Allah ek hai."),
        ("اللَّهُ الصَّمَدُ", "Allah be-niyaz hai."),
        ("لَمْ يَلِدْ وَلَمْ يُولَدْ", "Na us ki koi aulad hai aur na woh kisi ki aulad hai."),
        ("وَلَمْ يَكُنْ لَهُ كُفُوًا أَحَدٌ", "Aur koi bhi us ke barabar nahin."),
    ],
    113: [
        ("قُلْ أَعُوذُ بِرَبِّ الْفَلَقِ", "Kah do: main subah ke rab ki panah mangta hoon."),
        ("مِنْ شَرِّ مَا خَلَقَ", "Us ki makhlooq ke sharr se."),
        ("وَمِنْ شَرِّ غَاسِقٍ إِذَا وَقَبَ", "Aur andheri raat ke sharr se jab woh chha jaye."),
        ("وَمِنْ شَرِّ النَّفَّاثَاتِ فِي الْعُقَدِ", "Aur girahon mein phoonkne walion ke sharr se."),
        ("وَمِنْ شَرِّ حَاسِدٍ إِذَا حَسَدَ", "Aur hasad karne wale ke sharr se jab woh hasad kare."),
    ],
    114: [
        ("قُلْ أَعُوذُ بِرَبِّ النَّاسِ", "Kah do: main logon ke rab ki panah mangta hoon."),
        ("مَلِكِ النَّاسِ", "Logon ke badshah ki."),
        ("إِلَٰهِ النَّاسِ", "Logon ke mabood ki."),
        ("مِنْ شَرِّ الْوَسْوَاسِ الْخَنَّاسِ", "Us waswasa dalne wale ke sharr se jo (Allah ka naam sun kar) peechhe hat jata hai."),
        ("الَّذِي يُوَسْوِسُ فِي صُدُورِ النَّاسِ", "Jo logon ke seenon mein waswase dalta hai."),
        ("مِنَ الْجِنَّةِ وَالنَّاسِ", "Chahe jinnon mein se ho ya insanon mein se."),
    ],
}

# Curated tags used together with keyword filters:  (surah, ayah, category)
SEED_TAGS = [
    (103, 2, "warnings"), (108, 2, "commands"), (109, 1, "commands"),
    (110, 3, "commands"), (112, 1, "commands"), (113, 1, "commands"),
    (114, 1, "commands"), (1, 6, "commands"),
]

# Curated, human-written analysis (extend this dict — or move it to a DB table — for more Surahs).
SURAH_INFO = {
    1: dict(
        theme="Al-Fatihah is the opening of the Quran and a compact prayer. It praises Allah as Lord of all worlds, "
              "the Most Merciful and Master of the Day of Judgement, pledges worship and reliance for Him alone, and "
              "asks for guidance on the straight path. The core need it addresses is human dependence on guidance.",
        summary="A seven-ayah prayer recited in every rak'ah of salah. Structure: praise (1-4), covenant (5), request (6-7).",
        history="No past-nation narrative; it frames the whole Quran as the answer to the plea for guidance.",
        lessons="Begin with gratitude and praise; worship and seeking help belong to Allah alone; guidance is the greatest need.",
        future="Recite it consciously, treating each rak'ah as a renewed request for guidance and a renewed pledge.",
    ),
    103: dict(
        theme="Al-'Asr states that humankind, across time, is in loss except those who combine four things: faith, "
              "righteous action, mutual counsel to truth, and mutual counsel to patience.",
        summary="Three ayahs: an oath by time, a verdict of loss, and an exception with four conditions of success.",
        history="No narrative; it is a universal principle. Early Muslims are reported to have recited it when parting.",
        lessons="Time is capital; success is personal (faith, deeds) and communal (truth, patience).",
        future="Keep a circle that reminds you of truth and patience; audit how your time is spent.",
    ),
    108: dict(
        theme="Al-Kawthar consoles the Prophet ﷺ against those who mocked him, promising abundant good, and commands "
              "gratitude through prayer and sacrifice.",
        summary="Promise of abundance (1), command of worship (2), and the fate of the one who spites him (3).",
        history="Revealed in Makkah when opponents taunted the Prophet ﷺ. Many narrations link Kawthar to a river in Paradise.",
        lessons="Allah's gifts exceed people's insults; respond to blessing with worship.",
        future="When criticised, return to gratitude and prayer rather than retaliation.",
    ),
    109: dict(
        theme="Al-Kafirun draws a clear line in worship: no mixing of tawheed with shirk, while leaving each community "
              "its own path in this world.",
        summary="A repeated, firm declaration of non-compromise in worship, ending with 'for you your religion, for me mine'.",
        history="Reports say Makkan leaders proposed alternating worship; the surah rejected that.",
        lessons="Clarity in belief; courtesy in conduct; no compromise on the object of worship.",
        future="Hold firm on core beliefs without hostility in daily dealings.",
    ),
    110: dict(
        theme="An-Nasr announces Allah's help and victory, people entering Islam in crowds, and commands glorification, "
              "praise and seeking forgiveness in the moment of success.",
        summary="Victory arrives (1-2); the right response is tasbih, hamd and istighfar (3).",
        history="Revealed in Madinah near the completion of the Prophet's mission; some companions understood it as a sign of that.",
        lessons="Success is from Allah; respond with humility and repentance, not pride.",
        future="After every achievement, pause for thanks and istighfar.",
    ),
    112: dict(
        theme="Al-Ikhlas is a concise statement of pure tawheed: Allah is One, self-sufficient, neither begetting nor "
              "begotten, and without equal.",
        summary="Four ayahs defining Allah's oneness, independence and uniqueness.",
        history="Reports mention people asking the Prophet ﷺ to describe his Lord; this surah was the answer.",
        lessons="Dependence on Allah alone; no partner, no likeness.",
        future="Let tawheed shape what you fear, hope for and rely on.",
    ),
    113: dict(
        theme="Al-Falaq teaches seeking refuge in the Lord of daybreak from external harms: created evils, darkness, "
              "occult harm and envy.",
        summary="A prayer of refuge: the Lord of dawn (1), harm in general (2), night (3), sorcery (4), envy (5).",
        history="Makkan; paired with An-Nas as the two 'Mu'awwidhatayn', commonly recited morning, evening and before sleep.",
        lessons="Protection is sought from Allah, not from means alone.",
        future="Make the morning/evening and bedtime refuge routine.",
    ),
    114: dict(
        theme="An-Nas teaches seeking refuge in the Lord, King and God of mankind from the whisperer who retreats at "
              "Allah's remembrance — an inner, spiritual harm.",
        summary="Three titles of Allah (1-3), then refuge from the retreating whisperer (4-6).",
        history="Makkan; second of the Mu'awwidhatayn.",
        lessons="Inner whispers are real; remembrance is the remedy.",
        future="Respond to doubts and whispers with dhikr and seeking refuge.",
    ),
}

# Pivotal Arabic terms: {surah: [(arabic, meaning)]}
PIVOTAL = {
    1: [("الحمد", "Praise"), ("رب", "Lord / Sustainer"), ("الدين", "Judgement / religion"), ("الصراط", "The path")],
    103: [("العصر", "Time / era"), ("خسر", "Loss"), ("الصالحات", "Righteous deeds"), ("الصبر", "Patience")],
    108: [("الكوثر", "Abundant good"), ("صل", "Pray"), ("انحر", "Sacrifice")],
    109: [("أعبد", "I worship"), ("دين", "Religion / way")],
    110: [("نصر", "Help / victory"), ("الفتح", "Opening / conquest"), ("استغفره", "Seek His forgiveness")],
    112: [("الله", "Allah"), ("أحد", "One"), ("الصمد", "The Self-Sufficient")],
    113: [("أعوذ", "I seek refuge"), ("شر", "Evil / harm"), ("الفلق", "Daybreak")],
    114: [("أعوذ", "I seek refuge"), ("الناس", "Mankind"), ("الوسواس", "The whisperer")],
}

# Dua / Zikr references: {surah: [(ayahs, kind, note)]}
DUAS = {
    1: [([6, 7], "Dua", "Request for guidance")],
    110: [([3], "Zikr", "Tasbih, hamd and istighfar")],
    113: [([1, 2, 3, 4, 5], "Dua", "Seeking refuge from harm")],
    114: [([1, 2, 3, 4, 5, 6], "Dua", "Seeking refuge from the whisperer")],
}

STOPWORDS = """من في ما لا ان إن إنه أن على الى إلى عن او أو ثم قد لم لن هو هي هم كان كانوا الذي الذين التي
و ف ب ل يا ذلك هذا هذه كل ولا ولم وما فلا ولن ثم""".split()

CATEGORY_KEYWORDS = {
    "commands": ["قل", "اقيموا", "اتقوا", "اعبدوا", "اطيعوا", "انفقوا", "فاصبر", "واصبر", "اذكروا", "فصل", "وانحر", "فسبح", "واستغفره", "استغفروا", "توكل"],
    "warnings": ["عذاب", "ويل", "خسر", "لعنة", "نذير", "انذرتكم", "هلك", "سوء"],
    "afterlife": ["جنة", "جنات", "النار", "جهنم", "سقر", "الجحيم", "نعيم", "الفردوس", "سعير", "الحطمة", "الجنة"],
}
CATEGORY_LABELS = {
    "Direct Commands": "commands",
    "Warnings": "warnings",
    "Description of Paradise / Hellfire": "afterlife",
}

MAKKI_NOTE = ("Makki — typically focuses on faith (iman), tawheed, accountability and the Hereafter, with short, "
              "rhythmic ayahs.")
MADANI_NOTE = ("Madani — typically focuses on social laws, community life, governance, and relations between "
               "people and communities.")

# ───────────────────────── 2. TEXT UTILITIES ─────────────────────────
_DIAC = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")


def norm(text: str) -> str:
    """Strip diacritics/tatweel, unify alef/ya/ta-marbuta -> searchable skeleton."""
    t = _DIAC.sub("", text or "")
    t = re.sub("[أإآٱ]", "ا", t).replace("ى", "ي").replace("ة", "ه")
    t = re.sub(r"[^\u0621-\u064A\s]", "", t)
    return re.sub(r"\s+", " ", t).strip()


STOPWORDS = {norm(w) for w in STOPWORDS}


def strip_bismillah(text: str) -> str:
    words = text.split()
    if len(words) > 4 and [norm(w) for w in words[:4]] == ["بسم", "الله", "الرحمن", "الرحيم"]:
        return " ".join(words[4:])
    return text


# ───────────────────────── 3. DATABASE ─────────────────────────
@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    init_db(conn)
    return conn


def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS surahs(
            surah_id INTEGER PRIMARY KEY, name_ar TEXT, name_en TEXT,
            ayah_count INTEGER, revelation TEXT);
        CREATE TABLE IF NOT EXISTS quran_data(
            surah_id INTEGER NOT NULL, ayah_number INTEGER NOT NULL,
            arabic_naskh TEXT NOT NULL, arabic_clean TEXT NOT NULL,
            roman_urdu_translation TEXT DEFAULT '',
            PRIMARY KEY (surah_id, ayah_number));
        CREATE INDEX IF NOT EXISTS idx_quran_surah ON quran_data(surah_id, ayah_number);
        CREATE TABLE IF NOT EXISTS ayah_tags(
            surah_id INTEGER, ayah_number INTEGER, category TEXT,
            PRIMARY KEY (surah_id, ayah_number, category));
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
    """)
    conn.execute("DELETE FROM surahs")
    conn.executemany(
        "INSERT INTO surahs VALUES (?,?,?,?,?)",
        [(i + 1, ar, en, n, "Makki" if k == "K" else "Madani") for i, (ar, en, n, k) in enumerate(SURAHS)])
    conn.executemany("INSERT OR IGNORE INTO ayah_tags VALUES (?,?,?)", SEED_TAGS)
    conn.commit()
    ensure_data(conn)


def load_roman_urdu():
    """Read the bundled CSV (the only source of translations)."""
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Missing {CSV_PATH.name} — place it next to app.py.")
    raw = CSV_PATH.read_bytes()
    df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig").fillna("")
    data = {(int(r.surah_id), int(r.ayah_number)): str(r.roman_urdu_translation).strip() for r in df.itertuples()}
    return hashlib.sha1(raw).hexdigest(), data


def fetch_arabic_from_api():
    """Uthmani Arabic from the public AlQuran Cloud API -> {(surah, ayah): text}."""
    url = "https://api.alquran.cloud/v1/quran/quran-uthmani"
    with urllib.request.urlopen(url, timeout=30) as r:
        surahs = json.load(r)["data"]["surahs"]
    out = {}
    for sd in surahs:
        for a in sd["ayahs"]:
            text = a["text"]
            if sd["number"] not in (1, 9) and a["numberInSurah"] == 1:
                text = strip_bismillah(text)  # the API prepends Bismillah to ayah 1
            out[(sd["number"], a["numberInSurah"])] = text
    return out


def load_arabic():
    """Returns (dict, is_complete). Order: local cache -> one-time API download -> built-in demo text."""
    if ARABIC_CACHE.exists():
        try:
            d = {tuple(map(int, k.split(":"))): v for k, v in json.loads(ARABIC_CACHE.read_text("utf-8")).items()}
            if len(d) >= 6236:
                return d, True
        except Exception:
            pass
    try:
        d = fetch_arabic_from_api()
        if len(d) >= 6236:
            ARABIC_CACHE.write_text(json.dumps({f"{a}:{b}": t for (a, b), t in d.items()}, ensure_ascii=False), "utf-8")
            return d, True
    except Exception:
        pass
    return {(sid, i + 1): ar for sid, rows in SEED.items() for i, (ar, _) in enumerate(rows)}, False


def ensure_data(conn):
    """(Re)builds quran_data from the fixed CSV + Arabic whenever they change. Users cannot alter it."""
    h, roman = load_roman_urdu()
    meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    n = conn.execute("SELECT COUNT(*) FROM quran_data").fetchone()[0]
    if meta.get("csv") == h and meta.get("arabic") == "full" and n == len(roman):
        return
    arabic, full = load_arabic()
    with conn:
        conn.execute("DELETE FROM quran_data")
        conn.executemany(
            "INSERT INTO quran_data VALUES (?,?,?,?,?)",
            [(s, a, arabic.get((s, a), ""), norm(arabic.get((s, a), "")), ur) for (s, a), ur in sorted(roman.items())])
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('csv', ?)", (h,))
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('arabic', ?)", ("full" if full else "partial",))


COLS = "q.surah_id, s.name_en, q.ayah_number, q.arabic_naskh, q.roman_urdu_translation"
BASE = f"SELECT {COLS} FROM quran_data q JOIN surahs s ON s.surah_id = q.surah_id"


def q(sql, params=()):
    return pd.read_sql_query(sql, get_conn(), params=params)


def get_ayahs(sid, ayahs=None):
    df = q(f"{BASE} WHERE q.surah_id=? ORDER BY q.ayah_number", (sid,))
    return df if not ayahs else df[df.ayah_number.isin(ayahs)]


def word_search(term, sid=None, partial=True):
    t = norm(term)
    clause = "q.arabic_clean LIKE ?" if partial else "(' ' || q.arabic_clean || ' ') LIKE ?"
    pat = f"%{t}%" if partial else f"% {t} %"
    sql = f"{BASE} WHERE {clause}" + (" AND q.surah_id=?" if sid else "") + " ORDER BY q.surah_id, q.ayah_number"
    return q(sql, (pat, sid) if sid else (pat,))


def passage_search(category, sid=None, ayahs=None):
    kws = CATEGORY_KEYWORDS[category]
    kw_sql = " OR ".join("(' ' || q.arabic_clean || ' ') LIKE ?" for _ in kws)
    sql = (f"{BASE} WHERE (({kw_sql}) OR EXISTS (SELECT 1 FROM ayah_tags t WHERE t.surah_id=q.surah_id "
           f"AND t.ayah_number=q.ayah_number AND t.category=?))" + (" AND q.surah_id=?" if sid else "")
           + " ORDER BY q.surah_id, q.ayah_number")
    params = [f"% {norm(k)} %" for k in kws] + [category] + ([sid] if sid else [])
    df = q(sql, params)
    return df[df.ayah_number.isin(ayahs)] if ayahs else df


def recurring_words(df):
    counts, shown = {}, {}
    for ar in df.arabic_naskh:
        for tok in ar.split():
            n = norm(tok)
            if len(n) < 2 or n in STOPWORDS:
                continue
            counts[n] = counts.get(n, 0) + 1
            shown.setdefault(n, tok)
    out = pd.DataFrame([(shown[k], k, v) for k, v in counts.items()], columns=["word", "key", "count"])
    return out.sort_values(["count", "key"], ascending=[False, True]).reset_index(drop=True)


def dua_search(sid, ayahs=None):
    if sid in DUAS:
        rows = []
        for nums, kind, note in DUAS[sid]:
            d = get_ayahs(sid, nums)
            if ayahs:
                d = d[d.ayah_number.isin(ayahs)]
            d = d.assign(kind=kind, note=note)
            rows.append(d)
        return pd.concat(rows) if rows else pd.DataFrame()
    # fallback heuristic for Surahs without curated entries
    df = get_ayahs(sid, ayahs)
    return df[df.arabic_naskh.map(lambda x: any(k in norm(x).split() for k in ("ربنا", "اللهم")))] \
        .assign(kind="Dua (auto-detected)", note="Keyword match: contains 'Rabbana'")


# ───────────────────────── 4. STYLING / RENDERING ─────────────────────────
AR_STYLES = {  # label: (font stack, weight, line-height)
    "Indo-Pak style — Scheherazade (bold, curved)": ("'Scheherazade New','Noto Naskh Arabic',serif", 700, 2.1),
    "Nastaliq — Noto Nastaliq Urdu": ("'Noto Nastaliq Urdu','Scheherazade New',serif", 500, 2.8),
    "Classic Naskh — Amiri": ("'Amiri','Scheherazade New',serif", 400, 2.1),
}


def custom_font_css():
    """Optional: any .ttf/.otf placed in ./fonts becomes the 'Custom' Arabic style."""
    files = sorted(list(FONT_DIR.glob("*.ttf")) + list(FONT_DIR.glob("*.otf"))) if FONT_DIR.exists() else []
    if not files:
        return ""
    fmt = "opentype" if files[0].suffix == ".otf" else "truetype"
    b64 = base64.b64encode(files[0].read_bytes()).decode()
    return f"@font-face{{font-family:'TawassulCustom';src:url(data:font/{files[0].suffix[1:]};base64,{b64}) format('{fmt}');}}"


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&family=Scheherazade+New:wght@400;500;600;700&family=Noto+Nastaliq+Urdu:wght@400;500;700&family=Aref+Ruqaa:wght@400;700&display=swap');
%CUSTOM%
.ar{font-family:%FONT%;font-weight:%WEIGHT%;direction:rtl;text-align:right;font-size:%ARSIZE%px;line-height:%LH%;
    text-rendering:optimizeLegibility;-webkit-font-smoothing:antialiased;word-spacing:.12em;}
.ur{font-size:%URSIZE%px;line-height:1.7;direction:ltr;text-align:left;}
.qwrap{border:1px solid rgba(128,128,128,.3);border-radius:14px;overflow:hidden;}
.qrow{display:grid;grid-template-columns:1fr 1fr;gap:1.2rem;padding:.9rem 1.1rem;
      border-bottom:1px solid rgba(128,128,128,.2);align-items:center;}
.qrow:last-child{border-bottom:none;}
.bsm{background:rgba(25,118,210,.08);}
.ref{display:inline-block;font-size:.75rem;font-weight:600;color:#1976d2;margin-bottom:.2rem;}
.sname{font-family:'Aref Ruqaa','Amiri',serif;font-size:2.6rem;text-align:center;margin:0;}
.hero{text-align:center;padding:1.6rem 1rem 1.2rem;margin:.2rem 0 1.2rem;border-radius:20px;
      background:radial-gradient(circle at 50% 0%,rgba(201,162,39,.18),rgba(25,118,210,.10) 55%,transparent 80%);
      border:1px solid rgba(201,162,39,.35);}
.hero .logo{width:min(300px,70%);border-radius:18px;box-shadow:0 8px 28px rgba(0,0,0,.18);margin-bottom:.6rem;}
.hero .orn{letter-spacing:.6em;color:#c9a227;font-size:1.1rem;}
.hero .title-ar{font-family:'Aref Ruqaa','Amiri',serif;font-weight:700;font-size:clamp(3.4rem,11vw,6.5rem);
      line-height:1.35;margin:.1rem 0;direction:rtl;
      background:linear-gradient(90deg,#0d47a1,#1976d2 40%,#c9a227 80%);-webkit-background-clip:text;
      background-clip:text;color:transparent;-webkit-text-fill-color:transparent;}
.hero .title-en{font-size:clamp(1.2rem,3.5vw,1.8rem);letter-spacing:.45em;text-transform:uppercase;
      font-weight:700;color:#1976d2;margin-top:-.2rem;}
.hero .tag{opacity:.75;margin-top:.5rem;font-size:1rem;}
@media(max-width:700px){.qrow{grid-template-columns:1fr;}}
.st-key-navbar{position:sticky;top:2.9rem;z-index:999;padding:.4rem 0;
    background:var(--background-color,rgba(255,255,255,.92));border-bottom:1px solid rgba(128,128,128,.25);}
[data-testid="stBaseButton-primary"],button[kind="primary"]{background:#1976d2!important;border:none!important;color:#fff!important;font-weight:700;}
[data-testid="stBaseButton-primary"]:hover,button[kind="primary"]:hover{background:#0d47a1!important;}
.st-key-analyse_btn button{padding:.8rem 1rem;font-size:1.15rem;}
</style>
"""


def styles():
    ss = st.session_state
    options = dict(AR_STYLES)
    custom = custom_font_css()
    if custom:
        options = {"Custom font (fonts folder)": ("'TawassulCustom','Scheherazade New',serif", 400, 2.2), **options}
    st.sidebar.header("⚙️ Display settings")
    label = st.sidebar.selectbox("Arabic style", list(options), key="ar_style")
    ar_size = st.sidebar.slider("Arabic font size", 20, 80, 38, key="ar_size")
    ur_size = st.sidebar.slider("Roman Urdu font size", 12, 36, 18, key="ur_size")
    font, weight, lh = options[label]
    st.markdown(CSS.replace("%CUSTOM%", custom).replace("%FONT%", font).replace("%WEIGHT%", str(weight))
                .replace("%LH%", str(lh)).replace("%ARSIZE%", str(ar_size)).replace("%URSIZE%", str(ur_size)),
                unsafe_allow_html=True)


def rows_html(df, show_ref=False, bismillah=False):
    out = ['<div class="qwrap">']
    if bismillah:
        out.append(f'<div class="qrow bsm"><div class="ur"><span class="ref">{BISMILLAH_EN}</span><br>'
                   f'{html.escape(BISMILLAH_UR)}</div><div class="ar">{BISMILLAH_AR}</div></div>')
    for r in df.itertuples():
        ref = f"{html.escape(r.name_en)} {r.surah_id}:{r.ayah_number}" if show_ref else f"Ayah {r.ayah_number}"
        ur = html.escape(r.roman_urdu_translation) if r.roman_urdu_translation else "<i>Roman Urdu not loaded</i>"
        out.append(f'<div class="qrow"><div class="ur"><span class="ref">{ref}</span><br>{ur}</div>'
                   f'<div class="ar">{html.escape(r.arabic_naskh) or "—"}</div></div>')
    out.append("</div>")
    st.markdown("".join(out), unsafe_allow_html=True)


def show_results(df, empty_msg="No matching ayahs found in the loaded data."):
    if df.empty:
        st.info(empty_msg)
    else:
        st.caption(f"{len(df)} ayah(s)")
        rows_html(df, show_ref=True)


# ───────────────────────── 5. NAVIGATION STATE ─────────────────────────
DEFAULTS = dict(page="surahs", surah=None, mode=None, scope_type="Analyse Total Surah", scope=None,
                module="A · Revelation Context & Central Theme", b_section="Key Words: Recurring Words",
                c_option="Summary", drill_term=None, drill_label=None, drill_kind="recurring", drill_partial=False)
MODULES = ["A · Revelation Context & Central Theme", "B · Structural & Linguistic Breakdown",
           "C · Summary & Dua / Zikr"]
SCOPE_OPTS = ["Analyse Total Surah", "Analyse Particular Ayat / Ayats"]


def init_state():
    if "nav" not in st.session_state:
        st.session_state.nav = [dict(DEFAULTS)]
        st.session_state.idx = 0


def cur():
    return st.session_state.nav[st.session_state.idx]


def go(**changes):
    new = {**cur(), **changes}
    if new == cur():
        return
    st.session_state.nav = st.session_state.nav[: st.session_state.idx + 1] + [new]  # drop forward branch
    st.session_state.idx += 1


def back():
    st.session_state.idx = max(0, st.session_state.idx - 1)


def forward():
    st.session_state.idx = min(len(st.session_state.nav) - 1, st.session_state.idx + 1)


def state_select(label, options, field):
    """Selectbox whose value lives in the navigation history (so Back/Next restore it)."""
    value = cur().get(field)
    value = value if value in options else options[0]
    key = f"{field}_{st.session_state.idx}"
    st.selectbox(label, options, index=options.index(value), key=key,
                 on_change=lambda: go(**{field: st.session_state[key]}))
    return value


def surah_meta(sid):
    ar, en, n, k = SURAHS[sid - 1]
    return ar, en, n, ("Makki" if k == "K" else "Madani")


def navbar():
    s, idx = cur(), st.session_state.idx
    with st.container(key="navbar"):
        c1, c2, c3, c4 = st.columns([1.2, 1.2, 1, 6])
        c1.button("⬅️ Back", disabled=idx == 0, on_click=back, use_container_width=True)
        c2.button("➡️ Next", disabled=idx >= len(st.session_state.nav) - 1, on_click=forward,
                  use_container_width=True)
        c3.button("🏠", on_click=lambda: go(**DEFAULTS), help="All Surahs", use_container_width=True)
        crumbs = ["Surahs"]
        if s["surah"]:
            crumbs.append(f"{s['surah']}. {surah_meta(s['surah'])[1]}")
            crumbs.append({"read": "Read", "analyse": "Read + Analyse"}.get(s["mode"], "Mode"))
        if s["page"] in ("analytics", "drill"):
            crumbs.append("Analytics")
        if s["page"] == "drill":
            crumbs.append(s["drill_label"] or "")
        c4.markdown(" › ".join(crumbs))


# ───────────────────────── 6. PAGES ─────────────────────────
@st.cache_resource
def logo_b64():
    return base64.b64encode(LOGO_PATH.read_bytes()).decode() if LOGO_PATH.exists() else ""


def page_surahs():
    logo = (f'<img class="logo" src="data:image/png;base64,{logo_b64()}" alt="Tawassul logo">'
            if logo_b64() else "")
    st.markdown(f'<div class="hero">{logo}<div class="orn">۞ ✦ ۞</div>'
                f'<div class="title-ar">{APP_NAME_AR}</div>'
                f'<div class="title-en">{APP_NAME_EN}</div>'
                f'<div class="tag">Read · Reflect · Analyse the Quran</div></div>', unsafe_allow_html=True)
    flt = st.text_input("Search Surah (name or number)", placeholder="e.g. Ikhlas, 112, الفاتحة")
    items = [(i + 1, *m) for i, m in enumerate(SURAHS)]
    if flt.strip():
        f = flt.strip().lower()
        items = [x for x in items if f in x[2].lower() or f in x[1] or f == str(x[0])]
    cols = st.columns(4)
    for j, (sid, ar, en, n, k) in enumerate(items):
        with cols[j % 4]:
            st.button(f"{sid}. {en} — {ar}\n\n{n} ayahs · {'Makki' if k == 'K' else 'Madani'}",
                      key=f"surah_{sid}", use_container_width=True,
                      on_click=lambda sid=sid: go(**{**DEFAULTS, "page": "mode", "surah": sid}))


def surah_header(sid):
    ar, en, n, rev = surah_meta(sid)
    st.markdown(f'<p class="sname">{ar}</p>', unsafe_allow_html=True)
    st.subheader(f"{sid}. {en}")
    st.caption(f"{rev} · {n} ayahs")


def page_mode():
    sid = cur()["surah"]
    surah_header(sid)
    st.markdown("#### Choose how you want to proceed")
    st.button("📖  Option 1 — Read Surah with Roman Urdu Translation", use_container_width=True,
              on_click=lambda: go(page="read", mode="read"))
    st.button("🔍  Option 2 — Read + Analyse", use_container_width=True,
              on_click=lambda: go(page="read", mode="analyse"))


def loaded_warning(sid, df):
    if (df.arabic_naskh == "").any():
        st.warning("Arabic text is not available yet. Tawassul downloads it automatically once when it has "
                   "an internet connection — please reopen the app when online.")


def page_read():
    s = cur()
    sid = s["surah"]
    surah_header(sid)
    if s["mode"] == "analyse":
        st.button("Analyse", key="analyse_btn", type="primary", use_container_width=True,
                  on_click=lambda: go(page="analytics"))
    df = get_ayahs(sid)
    loaded_warning(sid, df)
    # Bismillah rule: shown for every Surah except At-Tawbah (9); in Al-Fatihah it is already Ayah 1.
    rows_html(df, bismillah=sid not in (1, 9))


def scope_picker(sid):
    n = surah_meta(sid)[2]
    s = cur()
    choice = state_select("What do you want to analyse?", SCOPE_OPTS, "scope_type")
    if choice == SCOPE_OPTS[0]:
        return None
    method = st.radio("Select ayahs by", ["Range", "Multi-select"], horizontal=True, key=f"method_{st.session_state.idx}")
    prev = list(s["scope"] or [1])
    if method == "Range":
        a, b = st.columns(2)
        start = a.number_input("From ayah", 1, n, min(prev), key=f"from_{st.session_state.idx}")
        end = b.number_input("To ayah", 1, n, max(prev), key=f"to_{st.session_state.idx}")
        pick = list(range(int(min(start, end)), int(max(start, end)) + 1))
    else:
        pick = st.multiselect("Ayahs", list(range(1, n + 1)), default=[p for p in prev if p <= n],
                              key=f"multi_{st.session_state.idx}")
    st.button("Apply selection", on_click=lambda: go(scope=tuple(sorted(pick))) if pick else None)
    return list(s["scope"]) if s["scope"] else None


def page_analytics():
    s = cur()
    sid = s["surah"]
    surah_header(sid)
    scope = scope_picker(sid)
    st.caption("Scope: whole Surah" if scope is None else f"Scope: ayahs {scope[0]}–{scope[-1]} ({len(scope)} selected)")
    st.divider()
    module = state_select("Module", MODULES, "module")
    st.divider()
    if module == MODULES[0]:
        module_a(sid)
    elif module == MODULES[1]:
        module_b(sid, scope)
    else:
        module_c(sid, scope)


def module_a(sid):
    _, en, _, rev = surah_meta(sid)
    st.markdown(f"### 🕋 Revelation: **{rev}**")
    st.info(MAKKI_NOTE if rev == "Makki" else MADANI_NOTE)
    st.caption("Classification follows the commonly used scholarly listing; a few Surahs have mixed or disputed placement.")
    st.markdown("### 🎯 Central Theme")
    info = SURAH_INFO.get(sid)
    st.write(info["theme"] if info else
             f"A curated central-theme paragraph for {en} is not in the demo dataset yet. "
             "Add an entry to `SURAH_INFO` (or a DB table) to display it here.")


def module_b(sid, scope):
    sec = state_select("Section", ["Key Words: Recurring Words", "Key Words: Pivotal Arabic Terms",
                                   "Section / Passage"], "b_section")
    df = get_ayahs(sid, scope)
    if sec == "Key Words: Recurring Words":
        words = recurring_words(df)
        if words.empty:
            return st.info("No words to analyse.")
        top = int(words["count"].max())
        mn = st.slider("Minimum frequency", 1, max(top, 2), 2 if top >= 2 else 1) if top > 1 else 1
        words = words[words["count"] >= mn].head(40)
        st.dataframe(words.rename(columns={"word": "Word", "key": "Searchable form", "count": "Count"}),
                     hide_index=True, use_container_width=True)
        st.markdown("**Tap a word to see where it appears:**")
        cols = st.columns(4)
        for i, r in enumerate(words.itertuples()):
            cols[i % 4].button(f"{r.word}  ({r.count})", key=f"w_{sid}_{i}", use_container_width=True,
                               on_click=lambda r=r: go(page="drill", drill_term=r.key, drill_label=r.word,
                                                       drill_kind="recurring", drill_partial=False))
    elif sec == "Key Words: Pivotal Arabic Terms":
        terms = PIVOTAL.get(sid)
        if not terms:
            return st.info("No curated pivotal terms for this Surah yet — add them to `PIVOTAL`.")
        cols = st.columns(3)
        for i, (ar, meaning) in enumerate(terms):
            cols[i % 3].button(f"{ar} — {meaning}", key=f"p_{sid}_{i}", use_container_width=True,
                               on_click=lambda ar=ar: go(page="drill", drill_term=norm(ar), drill_label=ar,
                                                         drill_kind="pivotal", drill_partial=True))
    else:
        label = st.selectbox("Passage type", list(CATEGORY_LABELS), key="passage_type")
        cat = CATEGORY_LABELS[label]
        t1, t2 = st.tabs(["In This Surah", "In Whole Quran"])
        with t1:
            show_results(passage_search(cat, sid, scope), "No passage of this type found in this Surah (selection).")
        with t2:
            show_results(passage_search(cat))
        st.caption("Matching uses curated tags plus keyword filters in SQL — an aid for exploration, "
                   "not a scholarly classification.")


def module_c(sid, scope):
    opt = state_select("Option", ["Summary", "Dua / Zikr"], "c_option")
    if opt == "Summary":
        info = SURAH_INFO.get(sid)
        if not info:
            return st.info("A curated summary for this Surah is not in the demo dataset. Add it to `SURAH_INFO`.")
        st.markdown("#### Summary");              st.write(info["summary"])
        st.markdown("#### Historical background / past stories"); st.write(info["history"])
        st.markdown("#### Central lessons");      st.write(info["lessons"])
        st.markdown("#### Practical guidance");   st.write(info["future"])
    else:
        d = dua_search(sid, scope)
        if d.empty:
            return st.info("No Dua / Zikr found in this Surah (selection).")
        for kind, note in d[["kind", "note"]].drop_duplicates().itertuples(index=False):
            st.markdown(f"**{kind}** — {note}")
            rows_html(d[d.kind == kind], show_ref=True)


def page_drill():
    s = cur()
    sid, term = s["surah"], s["drill_term"]
    st.markdown(f'### Word: <span class="ar" style="font-size:2rem">{html.escape(s["drill_label"] or "")}</span>',
                unsafe_allow_html=True)
    partial = st.toggle("Also match with attached prefixes/suffixes (و، ف، ب، ل، ال …)", value=s["drill_partial"],
                        key=f"partial_{st.session_state.idx}")
    names = ("Repeated in this Surah", "Repeated in the Quran") if s["drill_kind"] == "recurring" \
        else ("In This Surah", "In Whole Quran")
    t1, t2 = st.tabs(list(names))
    with t1:
        show_results(word_search(term, sid, partial))
    with t2:
        res = word_search(term, None, partial)
        show_results(res)
        if not res.empty:
            st.markdown("**Occurrences per Surah**")
            st.bar_chart(res.groupby("name_en").size().rename("ayahs"))


# ───────────────────────── 7. MAIN ─────────────────────────
def main():
    st.set_page_config(page_title=f"{APP_NAME_EN} — Quran Read & Analytics", page_icon=str(ICON_PATH) if ICON_PATH.exists() else "📖", layout="wide")
    init_state()
    styles()
    navbar()
    {"surahs": page_surahs, "mode": page_mode, "read": page_read,
     "analytics": page_analytics, "drill": page_drill}[cur()["page"]]()


if __name__ == "__main__":
    main()
