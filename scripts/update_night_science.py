import json, re, time, urllib.request, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta

FRESH_HOURS = 24
MAX_STORIES = 9

FEEDS = [
    ("Physics", "Phys.org Physics", "https://phys.org/rss-feed/physics-news/"),
    ("Quantum", "Phys.org Quantum", "https://phys.org/rss-feed/physics-news/quantum-physics/"),
    ("Optics", "ScienceDaily Optics", "https://www.sciencedaily.com/rss/matter_energy/optics.xml"),
    ("Quantum", "ScienceDaily Quantum", "https://www.sciencedaily.com/rss/matter_energy/quantum_physics.xml"),
    ("Cool Math", "ScienceDaily Math", "https://www.sciencedaily.com/rss/computers_math/mathematics.xml"),
    ("AI", "ScienceDaily AI", "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml"),
    ("Cryosphere", "ScienceDaily Snow & Ice", "https://www.sciencedaily.com/rss/earth_climate/snow_and_ice.xml"),
    ("Earth Observation", "NASA Earth Observatory", "https://earthobservatory.nasa.gov/feeds/image-of-the-day.rss"),
    ("Earth Observation", "NASA Earth News", "https://www.nasa.gov/rss/dyn/earth.rss"),
    ("Remote Sensing", "ESA Observing Earth", "https://www.esa.int/rssfeed/Our_Activities/Observing_the_Earth"),
    ("Geoscience", "Eos", "https://eos.org/feed"),
    ("Physics", "APS Physics", "https://physics.aps.org/rss/recent.xml"),
    ("Math/Physics", "Quanta Magazine", "https://www.quantamagazine.org/feed/"),
]

CORE_PHYSICS = [
    "physics", "quantum", "thermodynamic", "entropy", "heat", "temperature", "energy",
    "electromagnetic", "electrodynamics", "electric", "magnetic", "magnet", "spin",
    "plasma", "material", "semiconductor", "superconduct", "exciton", "atom",
    "electron", "photon", "particle", "interference",
]
OPTICS_WAVES_SENSORS = [
    "optic", "light", "laser", "lens", "spectral", "spectroscopy", "polarization",
    "wavelength", "frequency", "wave", "microwave", "radar", "sar", "sensor",
    "detector", "instrument", "measurement", "signal", "antenna", "radiometer",
    "lidar", "altimeter", "dielectric", "backscatter", "scattering", "polarimetric",
]
MATH_AI = [
    "mathematics", "geometry", "topology", "probability", "algorithm", "inverse",
    "artificial intelligence", "machine learning", "neural", "deep", "physics-informed",
    "model", "simulation",
]
REMOTE_OK = [
    "remote sensing", "earth observation", "sea ice", "ice sheet", "glacier", "cryosphere",
    "snow", "permafrost", "arctic", "antarctic", "greenland", "iceberg", "freeze", "melt",
    "sentinel", "nisar", "icesat", "cryosat", "copernicus",
]
CURIOSITY = [
    "mystery", "puzzle", "hidden", "strange", "weird", "unknown", "surprising", "paradox",
    "detect", "clue", "reveals", "invisible", "unseen", "extreme", "evidence",
]
BORING = [
    "contract", "procurement", "tender", "commercial", "market", "company", "industry",
    "partnership", "agreement", "memorandum", "funding", "budget", "roadmap", "capabilities",
    "consultation", "registration", "webinar", "workshop", "conference", "event", "press release",
]

REMOTE_TOPICS = {"Remote Sensing", "Earth Observation", "Cryosphere", "Geoscience"}
CORE_TOPICS = {"Physics", "Optics", "Quantum", "Cool Math", "Math/Physics"}


def clean(s):
    s = s or ""
    s = re.sub(r"<[^>]+>", " ", s)
    for a, b in [("&nbsp;", " "), ("&ndash;", "–"), ("&mdash;", "—"), ("&amp;", "&")]:
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def short(s, n=300):
    s = clean(s)
    return s if len(s) <= n else re.sub(r"\s+\S*$", "", s[:n]) + "…"


def parse_dt(s):
    s = clean(s)
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
    except Exception:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def text_of(node, names):
    for name in names:
        found = node.find(name)
        if found is not None and found.text:
            return found.text
    return ""


def get_link(node):
    link = node.find("link")
    if link is not None:
        return link.attrib.get("href") or (link.text or "")
    return ""


def tag_name(elem):
    return str(elem.tag).split("}", 1)[-1].lower()


def clean_image_url(url):
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return ""
    if any(x in url.lower() for x in ["/1x1", "pixel", "tracker"]):
        return ""
    return url


def image_from_html(html):
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html or "", flags=re.I)
    return clean_image_url(m.group(1)) if m else ""


def get_image(node):
    candidates = []
    for elem in node.iter():
        name = tag_name(elem)
        url = clean_image_url(elem.attrib.get("url") or elem.attrib.get("href"))
        medium = (elem.attrib.get("medium") or "").lower()
        typ = (elem.attrib.get("type") or "").lower()
        rel = (elem.attrib.get("rel") or "").lower()

        if name == "thumbnail" and url:
            candidates.append((0, url))
        elif name in {"content", "enclosure"} and url and (medium == "image" or typ.startswith("image/")):
            candidates.append((1, url))
        elif name == "link" and url and typ.startswith("image/") and rel in {"enclosure", "image", "preview"}:
            candidates.append((2, url))

    html_fields = [
        text_of(node, ["description", "summary", "{http://www.w3.org/2005/Atom}summary"]),
        text_of(node, ["{http://purl.org/rss/1.0/modules/content/}encoded"]),
    ]
    for html in html_fields:
        url = image_from_html(html)
        if url:
            candidates.append((3, url))

    candidates.sort(key=lambda x: x[0])
    for _, url in candidates:
        return url
    return ""


def fetch_feed(topic, source, url):
    req = urllib.request.Request(url, headers={"User-Agent": "NightScienceDispatch/4.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        root = ET.fromstring(r.read())

    nodes = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    out = []

    for it in nodes[:25]:
        title = clean(text_of(it, ["title", "{http://www.w3.org/2005/Atom}title"]))
        desc = short(text_of(it, [
            "description", "summary", "{http://www.w3.org/2005/Atom}summary",
            "{http://purl.org/rss/1.0/modules/content/}encoded"
        ]))
        link = clean(get_link(it))
        raw_date = text_of(it, [
            "pubDate", "updated", "published",
            "{http://www.w3.org/2005/Atom}updated",
            "{http://www.w3.org/2005/Atom}published"
        ])
        dt = parse_dt(raw_date)

        if title and desc and link:
            out.append({
                "topic": topic,
                "source": source,
                "title": title,
                "link": link,
                "desc": desc,
                "date": dt.strftime("%b %d, %Y") if dt else (clean(raw_date)[:24] or "recent"),
                "published_utc": dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "",
                "image": get_image(it),
                "_dt": dt,
            })

    return out


def blob(item):
    return (item["topic"] + " " + item["source"] + " " + item["title"] + " " + item["desc"]).lower()


def hits(s, words):
    return sum(1 for k in words if k in s)


def has_any(s, words):
    return any(k in s for k in words)


def is_fresh(item, now):
    dt = item.get("_dt")
    return bool(dt and dt <= now + timedelta(hours=2) and now - dt <= timedelta(hours=FRESH_HOURS))


def score(item):
    s = blob(item)

    value = 0
    value += 8 * hits(s, CORE_PHYSICS)
    value += 7 * hits(s, OPTICS_WAVES_SENSORS)
    value += 5 * hits(s, MATH_AI)
    value += 2 * hits(s, REMOTE_OK)
    value += 3 * hits(s, CURIOSITY)

    if item["topic"] in {"Physics", "Optics", "Quantum"}:
        value += 14
    if item["topic"] in {"Cool Math", "Math/Physics"}:
        value += 11
    if item["source"] in {"APS Physics", "Quanta Magazine"}:
        value += 6

    if item["topic"] == "AI" and not has_any(s, CORE_PHYSICS + OPTICS_WAVES_SENSORS + ["physics-informed", "model", "simulation"]):
        value -= 8

    if item["topic"] in REMOTE_TOPICS and not has_any(s, CORE_PHYSICS + OPTICS_WAVES_SENSORS + REMOTE_OK):
        value -= 10

    if has_any(s, BORING):
        value -= 35

    if item["title"].lower().startswith("earth from space:") and not has_any(
        s, ["radar", "sentinel", "microwave", "thermal", "permafrost", "sea ice", "ice", "glacier", "snow"]
    ):
        value -= 12

    return value


def group_for_quota(item):
    if item["topic"] in REMOTE_TOPICS:
        return "remote_earth"
    if item["topic"] == "AI":
        return "ai"
    if item["topic"] in CORE_TOPICS:
        return "core_physics"
    return "other"


def key_for(item):
    return re.sub(r"[^a-z0-9]", "", item["title"].lower())[:70]


now = datetime.now(timezone.utc)
items = []

for feed in FEEDS:
    try:
        got = fetch_feed(*feed)
        fresh = [item for item in got if is_fresh(item, now)]
        print(f"Fetched {len(got)} from {feed[1]} ({len(fresh)} within {FRESH_HOURS}h)")
        items.extend(fresh)
        time.sleep(0.5)
    except Exception as e:
        print("Feed failed:", feed[1], e)

ranked = sorted(items, key=score, reverse=True)
selected, seen, group_counts = [], set(), {}
max_group = {"remote_earth": 2, "ai": 1}

for item in ranked:
    k = key_for(item)
    if k in seen or score(item) <= 0:
        continue

    g = group_for_quota(item)
    if group_counts.get(g, 0) >= max_group.get(g, 99):
        continue

    selected.append(item)
    seen.add(k)
    group_counts[g] = group_counts.get(g, 0) + 1

    if len(selected) == MAX_STORIES:
        break

for item in ranked:
    if len(selected) == MAX_STORIES:
        break

    k = key_for(item)
    if k in seen or score(item) <= 5:
        continue

    selected.append(item)
    seen.add(k)

output = []
for item in selected:
    item = dict(item)
    item.pop("_dt", None)
    output.append(item)

with open("bedtime-physics/stories.json", "w", encoding="utf-8") as f:
    json.dump({
        "updated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "fresh_window_hours": FRESH_HOURS,
        "stories": output,
    }, f, indent=2, ensure_ascii=False)

print(f"Selected {len(output)} stories from the last {FRESH_HOURS} hours.")
