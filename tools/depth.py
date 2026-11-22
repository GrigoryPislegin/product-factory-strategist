"""Управление объёмом колоды и собственные векторные блоки команды."""
import investment
from copy import deepcopy
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
for prefix, uri in (("p",P),("a",A),("r",R)):
    ET.register_namespace(prefix, uri)
KITS = Path(__file__).resolve().parents[1] / "templates/vk-components.xml"


def block(tree, name, x, y, w, h):
    props = deepcopy(ET.parse(KITS).find(name)[0])
    pos = props.find("{*}xfrm")
    pos.find("{*}off").attrib.update(x=str(round(x*9525)), y=str(round(y*9525)))
    pos.find("{*}ext").attrib.update(cx=str(round(w*9525)), cy=str(round(h*9525)))
    sp = ET.Element(f"{{{P}}}sp")
    nv = ET.SubElement(sp,f"{{{P}}}nvSpPr")
    next_id = max([int(v.get("id","0")) for v in tree.findall(".//{*}cNvPr")] or [0])+1
    ET.SubElement(nv,f"{{{P}}}cNvPr",id=str(next_id),name=f"VK {name}")
    ET.SubElement(nv,f"{{{P}}}cNvSpPr");ET.SubElement(nv,f"{{{P}}}nvPr");sp.append(props)
    position = 2 + sum(v.get("name") == "VK card" for v in tree.findall(".//{*}cNvPr")) if name == "pill" else 2
    tree.insert(position,sp)


def apply(data, spec):
    level = spec.get("level","standard")
    if level not in ("quick","standard","deep"):
        raise ValueError("Уровень — quick, standard или deep.")
    with ZipFile(BytesIO(data)) as source:
        parts = {n:source.read(n) for n in source.namelist()}
        infos = {i.filename:i for i in source.infolist()}
    def xml(n): return ET.fromstring(parts[n])
    def write(n,root): parts[n]=ET.tostring(root,encoding="utf-8",xml_declaration=True)
    summary=xml("ppt/slides/slide2.xml"); tree=summary.find(".//{*}spTree")
    for x,w in [(43,368),(432,360),(811,417)]:block(tree,"card",x,147,w,427)
    for x,w in [(49,144),(439,144),(816,371)]:block(tree,"pill",x,156,w,51)
    write("ppt/slides/slide2.xml",summary)
    def bars(root,values):
        numbers=[Decimal(str(v)) for v in values]
        if len(numbers)!=2 or any(not v.is_finite() or v<0 for v in numbers):
            raise ValueError("Для сравнения нужны два конечных неотрицательных значения.")
        top=max(numbers) or Decimal(1);tree=root.find(".//{*}spTree")
        for i,v in enumerate(numbers):
            x=58+i*606
            # insert places new shapes below earlier ones; add actual first, then track.
            if v: block(tree,"bar",x,520,round(490*v/top),10)
            block(tree,"track",x,520,490,10)
    if spec.get("chart_values") is not None:
        fifth=xml("ppt/slides/slide5.xml");bars(fifth,spec["chart_values"]);write("ppt/slides/slide5.xml",fifth)
    pres=xml("ppt/presentation.xml");ids=pres.find("{*}sldIdLst")
    relations=xml("ppt/_rels/presentation.xml.rels");types=xml("[Content_Types].xml")
    if level=="quick":
        for item in list(ids)[2:4]:ids.remove(item)
    extra=spec.get("appendix",[])
    rich = level == "deep" and "investment" in spec
    if level=="deep" and not rich and (not isinstance(extra,list) or len(extra)<3):
        raise ValueError("Для глубокой защиты заполните минимум три приложения с цифрами и основаниями.")
    if level=="deep" and not rich:
        for n,row in enumerate(extra,7):
            slide=xml("ppt/slides/slide5.xml");tree=slide.find(".//{*}spTree")
            # Rebuild the graphic against new values; keep the original editable typography.
            for el in list(tree):
                prop=el.find(".//{*}cNvPr")
                if prop is not None and prop.get("name","").startswith("VK "):tree.remove(el)
            for sp in tree.findall("{*}sp"):
                nv=sp.find("./{*}nvSpPr/{*}cNvPr");key=nv.get("name","")
                texts=sp.findall(".//{*}t")
                if texts:
                    value=row.get(key)
                    if not isinstance(value,str) or not value.strip():raise ValueError(f"Приложение {n}: заполните {key}.")
                    texts[0].text=value
                    for t in texts[1:]:t.text=""
            bars(slide,row["values"]);write(f"ppt/slides/slide{n}.xml",slide)
            note=xml("ppt/notesSlides/notesSlide5.xml")
            for sp in note.findall(".//{*}sp"):
                ph=sp.find(".//{*}ph")
                if ph is not None and ph.get("type")=="body":
                    ts=sp.findall(".//{*}t");ts[0].text=row["source"]
                    for t in ts[1:]:t.text=""
            write(f"ppt/notesSlides/notesSlide{n}.xml",note)
            for prefix,base in (("ppt/slides/_rels/slide","notesSlide"),("ppt/notesSlides/_rels/notesSlide","slide")):
                parts[f"{prefix}{n}.xml.rels"]=parts[prefix+"5.xml.rels"].replace(f"{base}5.xml".encode(),f"{base}{n}.xml".encode())
            rid=f"rIdAppendix{n}";ET.SubElement(ids,f"{{{P}}}sldId",{"id":str(512+n),f"{{{R}}}id":rid})
            ET.SubElement(relations,relations[0].tag,Type=R+"/slide",Target=f"/ppt/slides/slide{n}.xml",Id=rid)
            for part,mime in [(f"/ppt/slides/slide{n}.xml","slide"),(f"/ppt/notesSlides/notesSlide{n}.xml","notesSlide")]:
                ET.SubElement(types,"{http://schemas.openxmlformats.org/package/2006/content-types}Override",PartName=part,ContentType=f"application/vnd.openxmlformats-officedocument.presentationml.{mime}+xml")
    if level!="standard" and not rich:
        first=xml("ppt/slides/slide1.xml")
        for sp in first.findall(".//{*}sp"):
            nv=sp.find("./{*}nvSpPr/{*}cNvPr");key=nv.get("name","");ts=sp.findall(".//{*}t")
            if not ts:continue
            if level=="quick":
                swaps={"03–04":"03","05":"04","06":"",spec["slides"][0]["mechanics"]:"Экономический порог",spec["slides"][0]["economics"]:"Решение и проверка",spec["slides"][0]["decision"]:""}
                ts[0].text=swaps.get(ts[0].text,ts[0].text)
            elif key=="decision":ts[0].text="Решение и аналитические приложения"
        write("ppt/slides/slide1.xml",first)
    write("ppt/presentation.xml",pres);write("ppt/_rels/presentation.xml.rels",relations);write("[Content_Types].xml",types)
    if rich:
        investment.install(parts, spec["investment"])
    out=BytesIO()
    with ZipFile(out,"w") as target:
        for n,raw in parts.items(): target.writestr(infos.get(n) or ZipInfo(n,(2026,1,1,0,0,0)),raw,compress_type=ZIP_DEFLATED)
    return out.getvalue()
