"""Инвестиционная защита: типы доказательств, проверка структуры и редактируемые аналитические слайды."""
import math
import re
import textwrap
from copy import deepcopy
from xml.etree import ElementTree as ET

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NAVY, INK, MUTED = "162D4B", "233952", "506781"
BLUE, PALE, LINE = "0069DA", "E8F3FF", "CDDFF2"
TEAL, AMBER = "067F79", "9A4C14"
ROLES = {"problem", "alternatives", "reach", "communication", "validation", "finance", "sensitivity", "execution"}
KINDS = {"table", "bars", "steps", "choice"}
BAD_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def text(value, label):
    if not isinstance(value, str) or not value.strip() or BAD_XML.search(value):
        raise ValueError(f"Инвестиционная защита — заполните {label} корректным текстом.")
    return value.strip()


def checked(pack):
    if not isinstance(pack, dict):
        raise ValueError("Нужен объект investment с источниками и страницами.")
    sources = pack.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("Нужен реестр источников защиты.")
    for key, record in sources.items():
        text(key, "ID источника")
        if not isinstance(record, dict):
            raise ValueError("Каждая запись источника должна содержать name и locator.")
        for field in ("name", "locator"):
            text(record.get(field), field)
    pages = pack.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("Укажите последовательность pages.")
    roles, ordered = set(), []
    for page in pages:
        if type(page) is int:
            if page not in range(1, 7) or page in ordered:
                raise ValueError("Номер основного слайда повторяется или выходит за границы.")
            ordered.append(page)
            continue
        if not isinstance(page, dict) or page.get("kind") not in KINDS:
            raise ValueError("У аналитической страницы должен быть поддерживаемый kind.")
        for field in ("role", "section", "title", "context", "implication", "notes"):
            text(page.get(field), field)
        refs = page.get("refs")
        if not isinstance(refs,list) or not refs or any(not isinstance(ref,str) or ref not in sources for ref in refs):
            raise ValueError(f"Проверьте источники страницы «{page['title']}».")
        roles.add(page["role"])
    if pages[:2] != [1, 2] or set(ordered) != set(range(1,7)) or not ROLES <= roles:
        raise ValueError("Нужны оглавление, executive summary, шесть основных слайдов и темы " +
                         ", ".join(sorted(ROLES - roles)))
    agenda=pack.get("agenda")
    if not isinstance(agenda,list) or len(agenda)!=4:
        raise ValueError("Оглавление должно содержать четыре раздела.")
    expected=2
    for entry in agenda:
        if not isinstance(entry,dict):
            raise ValueError("Укажите название и границы раздела.")
        text(entry.get("label"), "название раздела")
        start,end=entry.get("from"),entry.get("to")
        if type(start) is not int or type(end) is not int or start!=expected or not start<=end<=len(pages):
            raise ValueError("Диапазоны оглавления должны покрывать все слайды по порядку.")
        expected=end+1
    if expected!=len(pages)+1:
        raise ValueError("Оглавление должно включать последний слайд.")
    return pages, sources


def sub(parent, ns, tag, **attrs):
    return ET.SubElement(parent, f"{{{ns}}}{tag}", {k:str(v) for k,v in attrs.items()})


def fill(parent, color):
    sub(sub(parent, A, "solidFill"), A, "srgbClr", val=color)


class Slide:
    def __init__(self, base):
        self.root = deepcopy(base)
        self.tree = self.root.find(".//{*}spTree")
        for child in list(self.tree)[2:]:
            self.tree.remove(child)
        self.index = 1

    def shape(self, x, y, w, h, color=None, name=""):
        self.index += 1
        shp = sub(self.tree, P, "sp")
        nv = sub(shp, P, "nvSpPr")
        sub(nv, P, "cNvPr", id=self.index, name=name or f"Элемент {self.index}")
        sub(nv, P, "cNvSpPr")
        sub(nv, P, "nvPr")
        props = sub(shp, P, "spPr")
        xf = sub(props, A, "xfrm")
        sub(xf, A, "off", x=round(x*9525), y=round(y*9525))
        sub(xf, A, "ext", cx=round(w*9525), cy=round(h*9525))
        sub(sub(props,A,"prstGeom",prst="rect"), A, "avLst")
        if color:
            fill(props, color)
        else:
            sub(props, A, "noFill")
        sub(sub(props, A, "ln", w=0), A, "noFill")
        return shp

    def label(self, x, y, w, h, value, size=23, bold=False, color=INK, align="l"):
        value = text(value, "текст слайда")
        shp = self.shape(x,y,w,h,name=value[:52])
        body = sub(shp, P, "txBody")
        sub(body,A,"bodyPr",lIns=0,rIns=0,tIns=0,bIns=0,wrap="none",anchor="t")
        sub(body,A,"lstStyle")
        # Переносы задаются до экспорта и одинаковы для PowerPoint и PDF.
        def wrapped(pt):
            width = max(2, int(w / (pt * .55)))
            return [line for part in value.splitlines() for line in textwrap.wrap(part,width,break_long_words=False,break_on_hyphens=False)]
        lines = wrapped(size)
        while len(lines) * size * 1.16 > h and size > 15:
            size -= 1
            lines = wrapped(size)
        if len(lines) * size * 1.16 > h + 2:
            raise ValueError(f"Сократите текст для слайда: {value[:60]}")
        for line in lines:
            para = sub(body,A,"p")
            pp = sub(para,A,"pPr",algn=align)
            sub(sub(pp,A,"lnSpc"), A,"spcPts",val=round(size*.75*1.16*100))
            run = sub(para,A,"r")
            rp = sub(run,A,"rPr",lang="ru-RU",sz=round(size*75),b=int(bold))
            fill(rp,color)
            sub(rp,A,"latin",typeface="Arial")
            sub(rp,A,"cs",typeface="Arial")
            sub(run,A,"t").text=line

    def frame(self, page, pos, count):
        self.label(52,26,610,32,page["section"],19,True,BLUE)
        self.label(1050,27,178,30,f"{pos:02d} / {count:02d}",17,False,MUTED,"r")
        self.shape(52,68,1176,2,LINE)
        self.label(52,86,1180,58,page["title"],38,True,NAVY)
        self.label(53,153,1170,63,page["context"],22,False,MUTED)
        self.shape(52,611,1176,75,PALE)
        self.label(71,623,1134,53,page["implication"],22,True,NAVY)

    def table(self,page):
        columns = page["columns"]
        rows = page["rows"]
        if not 2<=len(columns)<=5 or not 1<=len(rows)<=6 or any(len(row)!=len(columns) for row in rows):
            raise ValueError("Таблица требует 2–5 колонок с равной длиной строк и 1–6 строк.")
        weights = page.get("widths", [1]*len(columns))
        if len(weights)!=len(columns) or any(type(w) not in (float,int) or not math.isfinite(w) or w<=0 for w in weights):
            raise ValueError("Проверьте ширины колонок таблицы.")
        widths = [1176*w/sum(weights) for w in weights]
        self.shape(52,224,1176,47,PALE)
        x=52
        for name,width in zip(columns,widths):
            self.label(x+10,234,width-19,32,name,18,True,BLUE)
            x+=width
        height=min(90,320/len(rows))
        for i,row in enumerate(rows):
            y=273+i*height
            self.shape(52,y+height-1,1176,1,LINE)
            x=52
            for j,(val,width) in enumerate(zip(row,widths)):
                self.label(x+10,y+9,width-18,height-13,val,21,j==0,NAVY if j==0 else INK)
                x+=width

    def steps(self,page):
        items=page["items"]
        if not 2<=len(items)<=4:
            raise ValueError("Для пути нужны от двух до четырёх шагов.")
        width=(1176-22*(len(items)-1))/len(items)
        for i,item in enumerate(items):
            x=52+i*(width+22)
            self.shape(x,236,width,5,BLUE if i==0 else LINE)
            self.label(x,255,width,52,item["headline"],28,True,NAVY)
            self.label(x,331,width,73,item["value"],34,True,BLUE)
            self.label(x,412,width-9,174,item["detail"],23)

    def bars(self,page):
        categories=page["categories"]
        series=page["series"]
        if not 2<=len(categories)<=5 or not 1<=len(series)<=2:
            raise ValueError("Графику нужны 2–5 категорий и одна или две серии.")
        for s in series:
            if len(s["values"])!=len(categories) or any(type(v) not in (int,float) or not math.isfinite(v) for v in s["values"]):
                raise ValueError("Данные графика должны содержать конечное число для каждой категории.")
        vals=[v for s in series for v in s["values"]]
        lo,hi=min([0]+vals),max([0]+vals)
        scale=547/(hi-lo or 1)
        zero=215-lo*scale
        self.label(54,221,320,32,page["unit"],18,True,MUTED)
        for j,s in enumerate(series):
            x=392+j*210
            self.shape(x,230,14,11,(BLUE,TEAL)[j])
            self.label(x+20,219,186,32,s["label"],17,False,MUTED)
        step=315/len(categories)
        self.shape(zero,268,1.5,step*len(categories)-6,LINE)
        for i,cat in enumerate(categories):
            y=268+i*step
            self.label(54,y+5,152,step-7,cat,20,True)
            for j,s in enumerate(series):
                v=s["values"][i]
                line_y=y+4+j*min(27,step*.39)
                self.shape(min(zero,zero+v*scale),line_y, max(1,abs(v)*scale),13,(BLUE,TEAL)[j])
                value=f"{v:,.{page.get('precision',1)}f}".replace(","," ").replace(".",",")
                self.label(770,line_y-5,91,25,value,17,True,(BLUE,TEAL)[j],"r")
        self.shape(884,232,1.5,350,LINE)
        self.label(906,247,307,95,page["callout"],30,True,BLUE)
        self.label(906,348,310,225,page["explain"],22)

    def choice(self,page):
        for i,item in enumerate(page["items"]):
            if i>1: raise ValueError("Защитите две сравнимые позиции.")
            x=52+i*603
            self.shape(x,229,567,4,(BLUE,TEAL)[i])
            self.label(x,252,561,51,item["headline"],28,True,NAVY)
            self.label(x,316,553,86,item["value"],34,True,(BLUE,TEAL)[i])
            self.label(x,414,554,165,item["detail"],23)
        if len(page["items"])!=2:raise ValueError("Нужны две позиции для сравнения.")


def render_page(base, page, index, count):
    slide=Slide(base)
    try:
        slide.frame(page,index,count)
        getattr(slide,page["kind"])(page)
    except (KeyError,TypeError,IndexError) as exc:
        raise ValueError(f"Страница «{page['title']}» содержит неполные данные: {exc}") from exc
    return slide.root


def install(parts, pack):
    pages, sources=checked(pack)
    parse=lambda n: ET.fromstring(parts[n])
    def write(n,root):
        parts[n]=ET.tostring(root,encoding="utf-8",xml_declaration=True)
    pres=parse("ppt/presentation.xml")
    ids=pres.find("{*}sldIdLst")
    original=list(ids)
    for old in original:ids.remove(old)
    rels=parse("ppt/_rels/presentation.xml.rels");types=parse("[Content_Types].xml")
    base=parse("ppt/slides/slide5.xml");notes=parse("ppt/notesSlides/notesSlide5.xml")
    style = pack.get("consulting_style")
    if style is not None:
        import consulting
    n=6
    for index,page in enumerate(pages,1):
        if type(page) is int:
            ids.append(original[page-1])
            if style is not None:
                path = f"ppt/slides/slide{page}.xml"
                source = parse(path)
                fields = {sp.find("./{*}nvSpPr/{*}cNvPr").get("name"): " ".join(sp.itertext()).strip()
                          for sp in source.findall(".//{*}sp") if sp.find("./{*}nvSpPr/{*}cNvPr") is not None}
                write(path, consulting.render(source,page,index,pack,style,fields))
            continue
        n+=1
        output = (consulting.render(base,page,index,pack,style) if style is not None
                  else render_page(base,page,index,len(pages)))
        write(f"ppt/slides/slide{n}.xml",output)
        note=deepcopy(notes)
        refs="\n".join(f"{ref} — {sources[ref]['name']}, {sources[ref]['locator']}" for ref in page["refs"])
        for sp in note.findall(".//{*}sp"):
            ph=sp.find(".//{*}ph")
            if ph is not None and ph.get("type")=="body":
                nodes=sp.findall(".//{*}t")
                nodes[0].text=page["notes"]+"\n\n"+refs
                for t in nodes[1:]:t.text=""
        write(f"ppt/notesSlides/notesSlide{n}.xml",note)
        for prefix,name in (("ppt/slides/_rels/slide","notesSlide"),("ppt/notesSlides/_rels/notesSlide","slide")):
            parts[f"{prefix}{n}.xml.rels"]=parts[prefix+"5.xml.rels"].replace(f"{name}5.xml".encode(),f"{name}{n}.xml".encode())
        rid=f"rIdInvestment{n}"
        ET.SubElement(ids,f"{{{P}}}sldId",{"id":str(800+n),f"{{{R}}}id":rid})
        ET.SubElement(rels,rels[0].tag,Type=R+"/slide",Target=f"/ppt/slides/slide{n}.xml",Id=rid)
        for path,kind in [(f"/ppt/slides/slide{n}.xml","slide"),(f"/ppt/notesSlides/notesSlide{n}.xml","notesSlide")]:
            ET.SubElement(types,f"{{{CT}}}Override",PartName=path,ContentType=f"application/vnd.openxmlformats-officedocument.presentationml.{kind}+xml")
    write("ppt/presentation.xml",pres);write("ppt/_rels/presentation.xml.rels",rels);write("[Content_Types].xml",types)
    # Позиции оглавления исходят из физического порядка показа, включая приложения.
    if style is not None:
        return
    cover=parse("ppt/slides/slide1.xml")
    agenda=pack["agenda"]
    if len(agenda)!=4:raise ValueError("Оглавление содержит четыре раздела.")
    words={k:text(v["label"],"подпись оглавления") for k,v in zip(("summary","mechanics","economics","decision"),agenda)}
    spans={}
    for old,v in zip(("02","03–04","05","06"),agenda):
        start,end=v["from"],v["to"]
        if not (type(start) is int and type(end) is int and 2<=start<=end<=len(pages)):
            raise ValueError("Диапазон оглавления выходит за пределы показа.")
        spans[old]=f"{start:02d}" if start==end else f"{start:02d}–{end:02d}"
    for sp in cover.findall(".//{*}sp"):
        nv=sp.find("./{*}nvSpPr/{*}cNvPr");ts=sp.findall(".//{*}t")
        if ts:
            key=nv.get("name","")
            ts[0].text=words.get(key,spans.get(ts[0].text,ts[0].text))
    write("ppt/slides/slide1.xml",cover)
