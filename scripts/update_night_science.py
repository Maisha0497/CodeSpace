import json, re, time, urllib.request, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

# Feed list tuned for Maisha's interests:
# physics, optics, quantum, cool math, AI, cryosphere, remote sensing,
# microwave/SAR, sea ice, electrodynamics, Earth observation.
# A few broader feeds remain, but the scoring below downranks generic astronomy.
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

PRIMARY_KEYWORDS = [
    # thesis / remote sensing / cryosphere
    "remote sensing", "satellite", "earth observation", "radar", "sar", "synthetic aperture",
    "microwave", "polarimetric", "polarimetry", "backscatter", "scatter", "scattering",
    "radiometer", "altimeter", "lidar", "insar", "sentinel", "nisar", "icesat", "cryosat",
    "sea ice", "ice sheet", "glacier", "cryosphere", "snow", "permafrost", "arctic",
    "antarctic", "greenland", "iceberg", "frozen", "freeze", "melt",
    # electrodynamics / waves / optics / quantum / physics
    "electromagnetic", "electrodynamics", "wave", "photon", "light", "optic", "laser",
    "interfer", "polarization", "dielectric", "permittivity", "antenna", "frequency",
    "quantum", "condensed matter", "plasma", "magnetic", "magnet", "exciton",
    # AI / math
    "artificial intelligence", "machine learning", "neural", "deep learning", "physics-informed",
    "inverse problem", "model", "algorithm", "mathematics", "geometry", "probability",
]

SECONDARY_KEYWORDS = [
    "climate", "ocean", "atmosphere", "cloud", "water", "temperature", "earth", "hazard",
    "sensor", "mission", "instrument", "data", "map", "imaging", "measurement", "signal",
]

# Space is fine when it involves instruments/waves/satellites, but not as the main flavor.
GENERIC_ASTRONOMY = [
    "exoplanet", "supernova", "star formation", "telescope sees", "james webb", "webb telescope",
    "distant galaxy", "cosmic dawn", "alien", "mars rover", "asteroid", "comet",
]


def clean(s):
    s = s or ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def short(s, n=300):
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
    req = urllib.request.Request(url, headers={"User-Agent": "NightScienceDispatch/2.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
    root = ET.fromstring(raw)
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    out = []
    for it in items[:12]:
        title = clean(text_of(it, ["title", "{http://www.w3.org/2005/Atom}title"]))
        desc = short(text_of(it, ["description", "summary", "{http://www.w3.org/2005/Atom}summary", "{http://purl.org/rss/1.0/modules/content/}encoded"]))
        link = clean(get_link(it))
        date = date_nice(text_of(it, ["pubDate", "updated", "published", "{http://www.w3.org/2005/Atom}updated", "{http://www.w3.org/2005/Atom}published"]))
        if title and desc and link:
            out.append({"topic": topic, "source": source, "title": title, "link": link, "desc": desc, "date": date, "image": ""})
    return out


def score(item):
    s = (item["topic"] + " " + item["source"] + " " + item["title"] + " " + item["desc"]).lower()
    value = 0
    value += sum(5 for k in PRIMARY_KEYWORDS if k in s)
    value += sum(2 for k in SECONDARY_KEYWORDS if k in s)

    # Boost feeds/topics closest to the thesis direction.
    if item["topic"] in {"Remote Sensing", "Cryosphere", "Earth Observation"}:
        value += 8
    if item["topic"] in {"Physics", "Optics", "Quantum", "AI", "Cool Math", "Math/Physics"}:
        value += 4
    if item["source"] in {"Eos", "NASA Earth Observatory", "ESA Observing Earth", "APS Physics"}:
        value += 4

    # Downrank generic astronomy unless it also has remote-sensing/instrument/wave relevance.
    if any(k in s for k in GENERIC_ASTRONOMY):
        if not any(k in s for k in ["satellite", "instrument", "sensor", "radar", "microwave", "wave", "light", "spect", "earth observation"]):
            value -= 12
    return value


items = []
for feed in FEEDS:
    try:
        got = fetch_feed(*feed)
        print(f"Fetched {len(got)} from {feed[1]}")
        items.extend(got)
        time.sleep(0.5)
    except Exception as e:
        print("Feed failed:", feed[1], e)

seen, selected = set(), []
for item in sorted(items, key=score, reverse=True):
    key = re.sub(r"[^a-z0-9]", "", item["title"].lower())[:70]
    if key in seen:
        continue
    if score(item) <= 0:
        continue
    seen.add(key)
    selected.append(item)
    if len(selected) == 9:
        break

if len(selected) < 5:
    raise SystemExit("Not enough relevant feed items fetched; leaving existing stories.json unchanged.")

with open("bedtime-physics/stories.json", "w", encoding="utf-8") as f:
    json.dump({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "stories": selected}, f, indent=2, ensure_ascii=False)
