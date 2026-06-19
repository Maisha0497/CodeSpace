import json, re, time, urllib.request, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

# Night Science Dispatch
# Target flavor:
# physics, optics, waves, sensors, quantum, thermodynamics, electrodynamics,
# strange/mystery-like science, sci-fi-adjacent ideas, cool math.
# Remote sensing is still allowed, but it should appear as science/measurement,
# not as commercial satellite, procurement, press-release, or event news.
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
    "physics", "thermodynamic", "entropy", "heat", "temperature", "energy", "phase transition",
    "electromagnetic", "electrodynamics", "electric field", "magnetic field", "magnet", "spin",
    "plasma", "condensed matter", "material", "semiconductor", "superconduct", "exciton",
    "quantum", "atom", "electron", "photon", "particle", "wavefunction", "interference",
]

OPTICS_WAVES_SENSORS = [
    "optic", "light", "laser", "lens", "spectral", "spectroscopy", "interfer", "polarization",
    "wavelength", "frequency", "wave", "microwave", "radar", "sar", "synthetic aperture",
    "sensor", "detector", "instrument", "measurement", "signal", "antenna", "radiometer",
    "lidar", "altimeter", "permittivity", "dielectric", "backscatter", "scattering", "polarimetric",
]

MATH_AI = [
    "mathematics", "geometry", "topology", "probability", "algorithm", "inverse problem",
    "artificial intelligence", "machine learning", "neural", "deep learning", "physics-informed",
    "model", "simulation",
]

REMOTE_SENSING_OK = [
    "remote sensing", "earth observation", "sea ice", "ice sheet", "glacier", "cryosphere",
    "snow", "permafrost", "arctic", "antarctic", "greenland", "iceberg", "freeze", "melt",
    "sentinel-1", "sentinel-2", "nisar", "icesat", "cryosat", "copernicus", "satellite image",
]

CURIOSITY_FLAVOR = [
    "mystery", "puzzle", "hidden", "strange", "weird", "unknown", "surprising", "paradox",
    "detect", "clue", "reveals", "invisible", "unseen", "ancient", "extreme", "first evidence",
]

# These produce exactly the tone you disliked: satellite-business / agency-admin news.
BORING_OR_COMMERCIAL = [
    "contract", "awards contract", "procurement", "tender", "commercial", "market", "company",
    "industry", "partnership", "agreement", "memorandum", "funding", "budget", "roadmap",
    "capabilities", "defence", "defense", "security", "user consultation", "consultation meeting",
    "registration", "webinar", "workshop", "conference", "event", "press release",
]

# Space is fine when it involves instruments/waves/satellites, but not as the main flavor.
GENERIC_ASTRONOMY = [
    "exoplanet", "supernova", "star formation", "telescope sees", "james webb", "webb telescope",
    "distant galaxy", "cosmic dawn", "alien", "mars rover", "asteroid", "comet",
]

REMOTE_TOPICS = {"Remote Sensing", "Earth Observation", "Cryosphere", "Geoscience"}
CORE_TOPICS = {"Physics", "Optics", "Quantum", "Cool Math", "Math/Physics"}


def clean(s):
    s = s or ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;", " ", s)
    s = re.sub(r"&ndash;", "–", s)
    s = re.sub(r"&mdash;", "—", s)
    s = re.sub(r"&amp;", "&", s)
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


def tag_name(elem):
    return str(elem.tag).split("}", 1)[-1].lower()


def clean_image_url(url):
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return ""
    lowered = url.lower()
    if any(x in lowered for x in ["/1x1", "pixel", "tracker"]):
        return ""
    return url


def image_from_html(html):
    html = html or ""
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, flags=re.I)
    return clean_image_url(m.group(1)) if m else ""


def get_image(node):
    """Use only RSS/Atom-provided images or images already embedded in the feed item.
    This keeps the updater lightweight and avoids scraping full articles.
    """
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

    if not candidates:
        return ""

    candidates.sort(key=lambda x: x[0])
    seen = set()
    for _, url in candidates:
        if url not in seen:
            return url
        seen.add(url)
    return ""


def fetch_feed(topic, source, url):
    req = urllib.request.Request(url, headers={"User-Agent": "NightScienceDispatch/3.1"})
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
        image = get_image(it)
        if title and desc and link:
            out.append({"topic": topic, "source": source, "title": title, "link": link, "desc": desc, "date": date, "image": image})
    return out


def text_blob(item):
    return (item["topic"] + " " + item["source"] + " " + item["title"] + " " + item["desc"]).lower()


def hits(s, words):
    return sum(1 for k in words if k in s)


def has_any(s, words):
    return any(k in s for k in words)


def score(item):
    s = text_blob(item)
    topic = item["topic"]
    source = item["source"]

    core = hits(s, CORE_PHYSICS)
    waves = hits(s, OPTICS_WAVES_SENSORS)
    math_ai = hits(s, MATH_AI)
    remote = hits(s, REMOTE_SENSING_OK)
    curiosity = hits(s, CURIOSITY_FLAVOR)

    value = 0
    value += 8 * core
    value += 7 * waves
    value += 5 * math_ai
    value += 2 * remote
    value += 3 * curiosity

    if topic in {"Physics", "Optics", "Quantum"}:
        value += 14
    if topic in {"Cool Math", "Math/Physics"}:
        value += 11
    if source in {"APS Physics", "Quanta Magazine"}:
        value += 6

    if topic == "AI":
        value += 4
        if not (core or waves or "physics-informed" in s or "model" in s or "simulation" in s):
            value -= 8

    if topic in REMOTE_TOPICS:
        value += 2
        if waves or core or remote >= 2:
            value += 4
        else:
            value -= 10

    if has_any(s, BORING_OR_COMMERCIAL):
        value -= 35

    if item["title"].lower().startswith("earth from space:"):
        if not (waves or core or has_any(s, ["radar", "sentinel-1", "microwave", "thermal", "permafrost", "sea ice", "ice", "glacier", "snow"])):
            value -= 12

    if has_any(s, GENERIC_ASTRONOMY):
        if not has_any(s, ["instrument", "sensor", "radar", "microwave", "wave", "light", "spect", "lens", "optical"]):
            value -= 14

    return value


def group_for_quota(item):
    s = text_blob(item)
    if item["topic"] in REMOTE_TOPICS:
        if hits(s, CORE_PHYSICS) + hits(s, OPTICS_WAVES_SENSORS) >= 2:
            return "physics_sensors"
        return "remote_earth"
    if item["topic"] == "AI":
        return "ai"
    if item["topic"] in CORE_TOPICS:
        return "core_physics"
    return "other"


def key_for(item):
    return re.sub(r"[^a-z0-9]", "", item["title"].lower())[:70]


items = []
for feed in FEEDS:
    try:
        got = fetch_feed(*feed)
        with_images = sum(1 for item in got if item.get("image"))
        print(f"Fetched {len(got)} from {feed[1]} ({with_images} with feed images)")
        items.extend(got)
        time.sleep(0.5)
    except Exception as e:
        print("Feed failed:", feed[1], e)

ranked = sorted(items, key=score, reverse=True)
selected = []
seen = set()
group_counts = {}

MAX_GROUP = {
    "remote_earth": 2,
    "ai": 1,
}

for item in ranked:
    k = key_for(item)
    if k in seen or score(item) <= 0:
        continue
    g = group_for_quota(item)
    if group_counts.get(g, 0) >= MAX_GROUP.get(g, 99):
        continue
    selected.append(item)
    seen.add(k)
    group_counts[g] = group_counts.get(g, 0) + 1
    if len(selected) == 9:
        break

for item in ranked:
    if len(selected) == 9:
        break
    k = key_for(item)
    if k in seen or score(item) <= 5:
        continue
    selected.append(item)
    seen.add(k)

if len(selected) < 5:
    raise SystemExit("Not enough relevant feed items fetched; leaving existing stories.json unchanged.")

with open("bedtime-physics/stories.json", "w", encoding="utf-8") as f:
    json.dump({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "stories": selected}, f, indent=2, ensure_ascii=False)
