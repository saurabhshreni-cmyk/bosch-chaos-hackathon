import html
import os
import struct
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "submission" / "team28-presentation.pptx"

W, H = 13.333, 7.5
EMU = 914400


def emu(value):
    return int(value * EMU)


def esc(value):
    return html.escape(str(value), quote=True)


def png_size(path):
    with open(path, "rb") as f:
        sig = f.read(24)
    if sig[:8] != b"\x89PNG\r\n\x1a\n":
        return 1280, 720
    return struct.unpack(">II", sig[16:24])


def crop_fit(path, x, y, w, h):
    iw, ih = png_size(path)
    box_ratio = w / h
    img_ratio = iw / ih
    src = ""
    if img_ratio > box_ratio:
        keep = box_ratio / img_ratio
        margin = int((1 - keep) * 50000)
        src = f'<a:srcRect l="{margin}" r="{margin}"/>'
    elif img_ratio < box_ratio:
        keep = img_ratio / box_ratio
        margin = int((1 - keep) * 50000)
        src = f'<a:srcRect t="{margin}" b="{margin}"/>'
    return x, y, w, h, src


class Deck:
    def __init__(self):
        self.slides = []
        self.media = {}

    def image_id(self, path):
        path = Path(path)
        if path not in self.media:
            self.media[path] = f"image{len(self.media) + 1}{path.suffix.lower()}"
        return self.media[path]

    def slide(self, title, subtitle=None, accent="d0005f"):
        slide = {"title": title, "subtitle": subtitle, "accent": accent, "items": []}
        self.slides.append(slide)
        return slide

    def text(self, slide, x, y, w, h, text, size=18, color="1f2933", bold=False, align="l"):
        slide["items"].append(("text", x, y, w, h, text, size, color, bold, align))

    def bullets(self, slide, x, y, w, h, lines, size=18, color="263238"):
        slide["items"].append(("bullets", x, y, w, h, lines, size, color))

    def pill(self, slide, x, y, w, h, text, fill="008c95", color="ffffff"):
        slide["items"].append(("pill", x, y, w, h, text, fill, color))

    def card(self, slide, x, y, w, h, title, body, fill="f3f7fa", line="d7e2ea"):
        slide["items"].append(("card", x, y, w, h, title, body, fill, line))

    def image(self, slide, path, x, y, w, h, crop=True):
        slide["items"].append(("image", path, x, y, w, h, crop))

    def table(self, slide, x, y, w, h, headers, rows):
        slide["items"].append(("table", x, y, w, h, headers, rows))


def tx_body(text, size, color, bold=False, align="l"):
    weight = ' b="1"' if bold else ""
    return (
        f'<p:txBody><a:bodyPr wrap="square"/><a:lstStyle/>'
        f'<a:p><a:pPr algn="{align}"/><a:r><a:rPr lang="en-US" sz="{size * 100}"{weight}>'
        f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:rPr>'
        f'<a:t>{esc(text)}</a:t></a:r></a:p></p:txBody>'
    )


def shape_xml(shape_id, x, y, w, h, body, fill=None, line=None, radius=False):
    prst = "roundRect" if radius else "rect"
    fill_xml = f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else '<a:noFill/>'
    line_xml = f'<a:ln><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>' if line else '<a:ln><a:noFill/></a:ln>'
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="Shape {shape_id}"/>'
        f'<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr>'
        f'<a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{emu(w)}" cy="{emu(h)}"/></a:xfrm>'
        f'<a:prstGeom prst="{prst}"><a:avLst/></a:prstGeom>{fill_xml}{line_xml}</p:spPr>{body}</p:sp>'
    )


def bullet_body(lines, size, color):
    paras = []
    for line in lines:
        paras.append(
            f'<a:p><a:pPr marL="285750" indent="-171450"><a:buChar char="&#8226;"/></a:pPr>'
            f'<a:r><a:rPr lang="en-US" sz="{size * 100}"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:rPr>'
            f'<a:t>{esc(line)}</a:t></a:r></a:p>'
        )
    return '<p:txBody><a:bodyPr wrap="square"/><a:lstStyle/>' + "".join(paras) + '</p:txBody>'


def pic_xml(shape_id, rel_id, path, x, y, w, h, crop=True):
    src = ""
    if crop:
        x, y, w, h, src = crop_fit(path, x, y, w, h)
    return (
        f'<p:pic><p:nvPicPr><p:cNvPr id="{shape_id}" name="{esc(Path(path).name)}"/>'
        f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
        f'<p:blipFill><a:blip r:embed="{rel_id}"/>{src}<a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        f'<p:spPr><a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{emu(w)}" cy="{emu(h)}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
    )


def table_xml(shape_start, x, y, w, h, headers, rows):
    nrows = len(rows) + 1
    ncols = len(headers)
    cell_w = w / ncols
    cell_h = h / nrows
    xml = []
    sid = shape_start
    for r, row in enumerate([headers] + rows):
        for c, value in enumerate(row):
            fill = "d0005f" if r == 0 else ("f5f9fb" if r % 2 else "ffffff")
            color = "ffffff" if r == 0 else "263238"
            bold = r == 0
            xml.append(shape_xml(sid, x + c * cell_w, y + r * cell_h, cell_w, cell_h, tx_body(value, 11, color, bold), fill, "d7e2ea"))
            sid += 1
    return "".join(xml), sid


def slide_xml(deck, slide, index):
    sp = []
    rels = [("rId1", "../slideLayouts/slideLayout1.xml", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout")]
    shape_id = 2
    accent = slide["accent"]
    sp.append(shape_xml(shape_id, 0, 0, W, H, tx_body("", 1, "ffffff"), "ffffff", None)); shape_id += 1
    sp.append(shape_xml(shape_id, 0.0, 0, 0.12, H, tx_body("", 1, "ffffff"), accent, None)); shape_id += 1
    sp.append(shape_xml(shape_id, 0.45, 0.3, 8.9, 0.55, tx_body(slide["title"], 27, accent, True), None, None)); shape_id += 1
    if slide.get("subtitle"):
        sp.append(shape_xml(shape_id, 0.48, 0.86, 9.5, 0.35, tx_body(slide["subtitle"], 13, "4b5963"), None, None)); shape_id += 1
    sp.append(shape_xml(shape_id, 11.55, 0.35, 1.1, 0.28, tx_body("TEAM 28", 10, "008c95", True, "r"), None, None)); shape_id += 1

    for item in slide["items"]:
        kind = item[0]
        if kind == "text":
            _, x, y, w, h, text, size, color, bold, align = item
            sp.append(shape_xml(shape_id, x, y, w, h, tx_body(text, size, color, bold, align), None, None)); shape_id += 1
        elif kind == "bullets":
            _, x, y, w, h, lines, size, color = item
            sp.append(shape_xml(shape_id, x, y, w, h, bullet_body(lines, size, color), None, None)); shape_id += 1
        elif kind == "pill":
            _, x, y, w, h, text, fill, color = item
            sp.append(shape_xml(shape_id, x, y, w, h, tx_body(text, 12, color, True, "ctr"), fill, fill, True)); shape_id += 1
        elif kind == "card":
            _, x, y, w, h, title, body, fill, line = item
            sp.append(shape_xml(shape_id, x, y, w, h, tx_body("", 1, "ffffff"), fill, line, True)); shape_id += 1
            sp.append(shape_xml(shape_id, x + 0.18, y + 0.14, w - 0.36, 0.35, tx_body(title, 15, "0b5961", True), None, None)); shape_id += 1
            sp.append(shape_xml(shape_id, x + 0.18, y + 0.55, w - 0.36, h - 0.66, bullet_body(body if isinstance(body, list) else [body], 12, "25323a"), None, None)); shape_id += 1
        elif kind == "image":
            _, path, x, y, w, h, crop = item
            media = deck.image_id(path)
            rid = f"rId{len(rels) + 1}"
            rels.append((rid, f"../media/{media}", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"))
            sp.append(pic_xml(shape_id, rid, path, x, y, w, h, crop)); shape_id += 1
        elif kind == "table":
            _, x, y, w, h, headers, rows = item
            table, shape_id = table_xml(shape_id, x, y, w, h, headers, rows)
            sp.append(table)

    body = "".join(sp)
    slide_doc = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>{body}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'''
    rel_doc = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(
        f'<Relationship Id="{rid}" Type="{rtype}" Target="{target}"/>' for rid, target, rtype in rels
    ) + '</Relationships>'
    return slide_doc, rel_doc


def build_deck():
    d = Deck()
    assets = ROOT / "submission"
    garage = ROOT / "pitstop-garage.png"
    arch = assets / "architecture-preview.png"
    dash = assets / "live-failure-dashboard.png"
    dep = assets / "dependency-map.png"
    frame1 = assets / "demo-frame-1.png"
    frame2 = assets / "demo-frame-2.png"
    frame3 = assets / "demo-frame-3.png"

    s = d.slide("AI-Driven Chaos Engineering", "Cloud-native resilience demo using Pitstop, Docker Compose, Ollama and a live dashboard")
    d.image(s, garage, 8.3, 0.9, 4.4, 5.9)
    d.pill(s, 0.65, 1.45, 2.1, 0.42, "Team No. 28")
    d.text(s, 0.65, 2.0, 6.8, 0.8, "Build an AI system that introduces controlled local failures, observes impact, verifies recovery and reports ranked findings.", 23, "263238", True)
    d.bullets(s, 0.75, 3.1, 6.2, 2.2, ["Sandbox only: no production systems", "Model: qwen2.5:1.5b via local Ollama", "Application: Pitstop microservices garage"], 17)

    s = d.slide("Problem Statement", "What the challenge asked us to build")
    d.card(s, 0.65, 1.35, 3.9, 4.6, "Team solution should", ["Select and map a cloud-native sample app", "Plan failures intelligently", "Inject controlled failures with safety limits", "Observe errors, slowdowns and recovery time", "Analyze and report ranked weaknesses"], "f7fbfc")
    d.card(s, 4.85, 1.35, 3.7, 4.6, "Accepted failure types", ["Service/container crash", "Slow or lossy network responses", "Failed shared dependency", "Traffic spike / combined scenario"], "fff6fa")
    d.card(s, 8.85, 1.35, 3.7, 4.6, "Out of scope", ["Production or shared infrastructure", "Unbounded destructive faults", "Unverified model-generated commands", "Claims of write durability without tests"], "f7fbfc")

    s = d.slide("Day-1 Baseline And Safety", "Foundation before running AI-selected experiments")
    d.bullets(s, 0.75, 1.35, 5.4, 4.8, ["Pitstop running end-to-end in Docker Compose", "Mapped services, dependencies and data flows", "Captured baseline latency and health", "Implemented manual STOP and automatic rollback", "Verified no arbitrary model shell commands"], 18)
    d.image(s, dep, 6.45, 1.25, 6.3, 4.5)
    d.pill(s, 6.55, 6.0, 4.8, 0.42, "Day-1 minimum: running app + dependency map + safe failure + kill switch")

    s = d.slide("Solution Architecture", "AI planning is separated from deterministic execution")
    d.image(s, arch, 0.55, 1.05, 6.1, 5.75)
    d.card(s, 7.0, 1.1, 5.4, 1.35, "Planner", ["Ranks registered experiments from dependency map, baseline and discovery evidence."], "f7fbfc")
    d.card(s, 7.0, 2.7, 5.4, 1.35, "Injection worker", ["Runs only code-owned, bounded tools; one fault at a time; rollback watchdog active."], "fff6fa")
    d.card(s, 7.0, 4.3, 5.4, 1.35, "Detection + recommendation", ["Measures availability/latency and produces evidence-linked findings with caveats."], "f7fbfc")

    s = d.slide("AI Agent Workflow", "From healthy baseline to ranked recommendations")
    d.table(s, 0.65, 1.25, 12.0, 3.0, ["Stage", "What happens", "Safety gate"], [
        ["Baseline", "Probe Customer, Vehicle, Workshop pages", "Unhealthy baseline blocks injection"],
        ["Plan", "AI ranks allowed experiment catalog", "Schema + ID validation"],
        ["Inject", "Crash or delay selected target", "Duration + blast-radius thresholds"],
        ["Recover", "Restore target and verify pages", "All three module pages must recover"],
        ["Analyze", "Rank anomalies and recommend fixes", "Evidence only; no root-cause certainty"]
    ])
    d.bullets(s, 1.0, 4.75, 11.0, 1.4, ["The AI chooses among registered experiments; it never invents a target or command.", "Reports retain model caveats when explanations are uncertain."], 17)

    s = d.slide("Experiments Executed", "Three required scenarios plus a combined stretch scenario")
    d.table(s, 0.55, 1.15, 12.25, 3.25, ["Experiment", "Fault", "Observed impact", "Recovery"], [
        ["workshop-crash", "Workshop API crash", "Workshop offline; Customer/Vehicle stable", "0.74 sec"],
        ["database-crash", "SQL dependency outage", "Two modules impacted; safety rollback", "30.29 sec"],
        ["workshop-delay", "500 ms network delay", "Workshop latency / timeouts", "1.07 sec"],
        ["crash + traffic", "Workshop crash under read load", "Combined failure stretch", "4.55 sec"]
    ])
    d.card(s, 0.8, 4.8, 5.6, 1.35, "What this proves", ["Controlled faults, measured degradation, automatic restoration and recorded evidence."], "f7fbfc")
    d.card(s, 6.8, 4.8, 5.6, 1.35, "What we do not claim", ["Read probes do not prove write correctness or message durability."], "fff6fa")

    s = d.slide("Live Dashboard", "Operator view for experiments, monitor, topology and evidence")
    d.image(s, dash, 0.55, 1.05, 6.25, 5.0)
    d.bullets(s, 7.15, 1.3, 5.4, 3.2, ["Agent lifecycle and worker status", "Live module health probes", "Failure monitor with incident-specific AI recommendations", "3D topology and dependency map", "Downloadable evidence and findings"], 18)
    d.pill(s, 7.2, 5.2, 4.9, 0.42, "Stretch goal: live dashboard / simple UI")

    s = d.slide("Findings And Scores", "AI-ranked findings grounded in measured evidence")
    d.card(s, 0.7, 1.25, 3.75, 4.65, "High severity", ["Workshop crash caused repeated Workshop page failures.", "SQL outage affected multiple modules.", "Workshop delay produced severe latency/availability anomalies."], "fff6fa")
    d.card(s, 4.75, 1.25, 3.75, 4.65, "Recommended fixes", ["Inspect service logs and dependency errors.", "Use bounded timeouts and safer fallback behavior.", "Rerun matched experiments after changes."], "f7fbfc")
    d.card(s, 8.8, 1.25, 3.75, 4.65, "Score method", ["Transparent read-probe heuristic, not an SLA.", "Recovery and healthy fault probes improve score.", "Unequal sampling is reported, not hidden."], "f7fbfc")

    s = d.slide("Applied Fix And Retest", "Timeout/fallback behavior improved responsiveness, with a reported tradeoff")
    d.table(s, 0.7, 1.25, 11.9, 2.15, ["Module", "Before p95", "After p95", "Interpretation"], [
        ["Customer", "5044 ms", "165 ms", "Faster fallback path"],
        ["Vehicle", "23 ms", "113 ms", "Stable reads"],
        ["Workshop", "4555 ms", "2064 ms", "Fails fast under delay"]
    ])
    d.bullets(s, 0.9, 4.0, 11.5, 1.6, ["We do not present the fix as universally better: it improves responsiveness while exposing an availability tradeoff.", "This is a matched retest, not a statistical proof."], 18)

    s = d.slide("Demo And Deliverables", "All required submission materials prepared")
    d.image(s, frame1, 0.65, 1.05, 3.75, 2.2)
    d.image(s, frame2, 4.85, 1.05, 3.75, 2.2)
    d.image(s, frame3, 9.05, 1.05, 3.75, 2.2)
    d.table(s, 0.75, 3.85, 11.8, 2.15, ["Deliverable", "File"], [
        ["Source code + README", "GitHub branch / README.md"],
        ["Demo video", "submission/demo.webm (88.4 sec)"],
        ["Architecture overview", "submission/architecture.pdf"],
        ["Findings report", "submission/findings.md"],
        ["Team form", "submission/team-form.json"]
    ])

    s = d.slide("Final Demo Flow", "What we will show the instructor")
    d.bullets(s, 0.8, 1.25, 5.9, 4.8, ["Open Pitstop and show Customer, Vehicle, Workshop are healthy", "Open dashboard Overview and explain worker lifecycle", "Show Dependencies and 3D topology", "Show Evidence & findings with ranked AI report", "Play the under-3-minute demo video"], 18)
    d.card(s, 7.15, 1.35, 5.0, 1.35, "Live rerun defaults", ["Use Workshop crash, Database crash and Workshop delay; keep RabbitMQ unchecked for the final live run."], "fff6fa")
    d.card(s, 7.15, 3.1, 5.0, 1.35, "Safety message", ["All faults are local, bounded, reversible, and blocked by STOP / recovery gates."], "f7fbfc")
    d.card(s, 7.15, 4.85, 5.0, 1.0, "Close", ["AI helps prioritize experiments and summarize evidence; humans still review findings."], "f7fbfc")

    return d


def write_package(deck):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    slide_docs = []
    for i, slide in enumerate(deck.slides, start=1):
        slide_docs.append(slide_xml(deck, slide, i))

    content_types = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Default Extension="png" ContentType="image/png"/>',
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>']
    for i in range(1, len(deck.slides) + 1):
        content_types.append(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>')
    content_types.append('</Types>')

    pres_rels = '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>' + ''.join(
        f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>'
        for i in range(1, len(deck.slides) + 1)
    )
    slide_ids = ''.join(f'<p:sldId id="{255 + i}" r:id="rId{i + 1}"/>' for i in range(1, len(deck.slides) + 1))
    presentation = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>{slide_ids}</p:sldIdLst><p:sldSz cx="{emu(W)}" cy="{emu(H)}" type="wide"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>'''
    core = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>AI-Driven Chaos Engineering Presentation</dc:title><dc:creator>Team 28</dc:creator><cp:lastModifiedBy>Team 28</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>'''
    app = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Codex</Application><PresentationFormat>On-screen Show (16:9)</PresentationFormat><Slides>{len(deck.slides)}</Slides></Properties>'''
    presentation_rels = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{pres_rels}</Relationships>'''
    master = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/><p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>'''
    master_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>'''
    layout = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1"><p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'''
    layout_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>'''
    theme = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Team 28"><a:themeElements><a:clrScheme name="Team 28"><a:dk1><a:srgbClr val="111827"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="263238"/></a:dk2><a:lt2><a:srgbClr val="F7FBFC"/></a:lt2><a:accent1><a:srgbClr val="D0005F"/></a:accent1><a:accent2><a:srgbClr val="008C95"/></a:accent2><a:accent3><a:srgbClr val="E2BE69"/></a:accent3><a:accent4><a:srgbClr val="78B7F0"/></a:accent4><a:accent5><a:srgbClr val="F17895"/></a:accent5><a:accent6><a:srgbClr val="5B6770"/></a:accent6><a:hlink><a:srgbClr val="008C95"/></a:hlink><a:folHlink><a:srgbClr val="D0005F"/></a:folHlink></a:clrScheme><a:fontScheme name="Office"><a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/></a:minorFont></a:fontScheme><a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>'''

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(content_types))
        z.writestr("_rels/.rels", root_rels)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
        z.writestr("ppt/presentation.xml", presentation)
        z.writestr("ppt/_rels/presentation.xml.rels", presentation_rels)
        z.writestr("ppt/slideMasters/slideMaster1.xml", master)
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", master_rels)
        z.writestr("ppt/slideLayouts/slideLayout1.xml", layout)
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", layout_rels)
        z.writestr("ppt/theme/theme1.xml", theme)
        for i, (sxml, rxml) in enumerate(slide_docs, start=1):
            z.writestr(f"ppt/slides/slide{i}.xml", sxml)
            z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", rxml)
        for path, name in deck.media.items():
            z.write(path, f"ppt/media/{name}")
    print(OUT)


if __name__ == "__main__":
    write_package(build_deck())
