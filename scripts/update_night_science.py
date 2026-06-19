import json, re, time, urllib.request, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

FEEDS = [
    ("Physics", "Phys.org Physics", "https://phys.org/rss-feed/physics-news/"),
    ("Quantum", "Phys.org Quantum", "https://phys.org/rss-feed/physics-news/quantum-physics/"),
    ("Optics", "ScienceDaily Optics", "https://www.sciencedaily.com/rss/matter_energy/optics.xml"),
    ("Quantum", "ScienceDaily Quantum", "https://www.sciencedaily.com/rss/matter_energy/quantum_physics.xml"),
    ("Cool Math", "ScienceDaily Math", "https://www.sciencedaily.com/rss/computers_math/mathematics.xml"),
    ("Space", "NASA", "https://www.nasa.gov/rss/dyn/breaking_news.rss"),
    ("Math/Physics", "Quanta Magazine", "https://www.quantamagazine.org/feed/"),
    ("Space", "Space.com", "https://www.space.com/feeds/all"),
]

def clean(s):
    s = s or ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def short(s, n=280):
    s = clean(s)
    return s if len(s) <= n else re.sub(r"\s+\S*$", "", s[:n]) + "…"

def date_nice(s):
    if not s:
        return "recent"
    try:
        return parsedate_to_datetime(s).strftime("%b %d, %Y")
    except Exception:
        return clean(s)[:24] or "recent"

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

def fetch_feed(topic, source, url):
    req = urllib.request.Request(url, headers={"User-Agent": "NightScienceDispatch/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
    root = ET.fromstring(raw)
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    out = []
    for it in items[:8]:
        title = clean(text_of(it, ["title", "{http://www.w3.org/2005/Atom}title"]))
        desc = short(text_of(it, ["description", "summary", "{http://www.w3.org/2005/Atom}summary", "{http://purl.org/rss/1.0/modules/content/}encoded"]))
        link = clean(get_link(it))
        date = date_nice(text_of(it, ["pubDate", "updated", "published", "{http://www.w3.org/2005/Atom}updated", "{http://www.w3.org/2005/Atom}published"]))
        if title and desc and link:
            out.append({"topic": topic, "source": source, "title": title, "link": link, "desc": desc, "date": date, "image": ""})
    return out

def score(item):
    s = (item["topic"] + " " + item["title"] + " " + item["desc"]).lower()
    keys = ["quantum", "physics", "optic", "photon", "light", "space", "planet", "galaxy", "math", "number", "mystery", "black hole", "ai", "radar", "wave"]
    return sum(2 for k in keys if k in s)

items = []
for feed in FEEDS:
    try:
        items.extend(fetch_feed(*feed))
        time.sleep(0.5)
    except Exception as e:
        print("Feed failed:", feed[1], e)

seen, selected = set(), []
for item in sorted(items, key=score, reverse=True):
    key = re.sub(r"[^a-z0-9]", "", item["title"].lower())[:60]
    if key in seen:
        continue
    seen.add(key)
    selected.append(item)
    if len(selected) == 9:
        break

if len(selected) < 5:
    raise SystemExit("Not enough feed items fetched; leaving existing stories.json unchanged.")

with open("bedtime-physics/stories.json", "w", encoding="utf-8") as f:
    json.dump({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "stories": selected}, f, indent=2, ensure_ascii=False)
