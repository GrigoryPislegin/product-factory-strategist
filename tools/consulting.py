"""Редактируемые компоненты консалтинговой защиты команды, холст 1280 × 720."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
import math
from pathlib import Path
from xml.etree import ElementTree as ET

from investment import A, Slide

BLUE, NAVY, BODY, MUTED = "0077FF", "14283D", "263A4E", "506579"
PALE, LINE, SILVER, WHITE = "E8F3FF", "BCD5EC", "BCD0E2", "FFFFFF"
KIT = Path(__file__).resolve().parents[1] / "templates" / "vk-components.xml"


@lru_cache(maxsize=1)
def kit():
    return ET.parse(KIT).getroot()


class ConsultingSlide(Slide):
    def component(self, kind, x, y, w, h, color=None):
        shape = self.shape(x, y, w, h, name="VK " + kind)
        old = shape.find("{*}spPr")
        props = deepcopy(kit().find(kind)[0])
        props.remove(props.find("{*}xfrm"))
        props.insert(0, deepcopy(old.find("{*}xfrm")))
        if color:
            props.find("./{*}solidFill/{*}srgbClr").set("val", color)
        shape.remove(old)
        shape.append(props)

    def pill(self, x, y, w, label):
        self.component("pill", x, y, w, 29, PALE)
        self.label(x+9, y+3, w-18, 24, label, 16, True, "075FAF", "ctr")

    def navigation(self, project, tabs, active, pos):
        self.label(43, 18, 218, 27, project, 19, True, "0768BD")
        x = 265
        for i, tab in enumerate(tabs):
            width = min(206, max(83, len(tab)*9+24))
            if active == i:
                self.pill(x, 15, width, tab)
            else:
                self.label(x+5, 18, width-10, 25, tab, 16, False, MUTED, "ctr")
            x += width+13
        self.label(1161, 18, 76, 25, f"{pos:02d}", 16, True, MUTED, "r")
        self.shape(43, 52, 1194, 1, "DEE9F1")

    def heading(self, title, context=None):
        self.label(43, 68, 1194, 79, title, 38, True, NAVY)
        if context:
            self.label(44, 151, 1186, 63, context, 21, False, MUTED)

    def takeaway(self, value):
        self.component("card", 43, 636, 1194, 58, PALE)
        self.label(65, 647, 1150, 41, value, 21, True, "154C80")

    def table(self, page):
        rows, columns = page["rows"], page["columns"]
        if not 2 <= len(columns) <= 5 or not 1 <= len(rows) <= 6 or any(len(r) != len(columns) for r in rows):
            raise ValueError("Проверьте размер таблицы инвестиционной защиты.")
        weights = page.get("widths", [1]*len(columns))
        if len(weights) != len(columns) or any(type(w) not in (int,float) or not math.isfinite(w) or w <= 0 for w in weights):
            raise ValueError("Проверьте ширины колонок.")
        widths = [1170*w/sum(weights) for w in weights]
        self.component("card", 43, 218, 1194, 397)
        x = 55
        for name, w in zip(columns, widths):
            self.pill(x+5, 231, min(w-12, max(90, len(name)*9+30)), name)
            x += w
        start, height = 277, 323/len(rows)
        for i, row in enumerate(rows):
            y = start+i*height
            self.shape(61, y-5, 1158, 1, LINE)
            x = 55
            for j, (v, w) in enumerate(zip(row, widths)):
                self.label(x+11, y+3, w-21, height-9, v, 21, j == 0, NAVY if j == 0 else BODY)
                x += w

    def bars(self, page):
        series, cats = page["series"], page["categories"]
        if not 1 <= len(series) <= 2 or not 2 <= len(cats) <= 5 or any(len(s["values"]) != len(cats) for s in series):
            raise ValueError("Проверьте серии и категории диаграммы.")
        self.component("card", 43, 224, 806, 389)
        self.component("card", 866, 224, 371, 389)
        self.pill(62, 240, 221, page["unit"])
        colors = [BLUE, "71A6D8"]
        for j, s in enumerate(series):
            x = 365+j*202
            self.shape(x, 251, 17, 10, colors[j])
            self.label(x+23, 241, 161, 29, s["label"], 17, True, BODY)
        vals = [v for s in series for v in s["values"]]
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in vals):
            raise ValueError("Диаграмме нужны конечные числовые значения.")
        lo, hi = min(0, min(vals)), max(0, max(vals))
        scale = 217/(hi-lo or 1)
        zero = 307+hi*scale
        self.shape(77, zero, 735, 1.5, LINE)
        positions = 724/len(cats)
        for i, cat in enumerate(cats):
            center = 83+(i+.5)*positions
            bw = min(43, positions/(len(series)+2))
            for j, s in enumerate(series):
                v = s["values"][i]
                x = center+(j-(len(series)-1)/2)*(bw+9)-bw/2
                y = zero-v*scale
                self.shape(x, min(zero,y), bw, max(1,abs(v)*scale), colors[j])
                val = str(Decimal(str(v)).quantize(Decimal(1).scaleb(-page.get("precision",2)), rounding=ROUND_HALF_UP)).replace(".",",")
                if v == 0 and j: continue
                self.label(x-9, y-25 if v >= 0 else y+3, bw+18, 25, val, 16, True, "174E7C", "ctr")
            self.label(center-positions/2, 565, positions, 29, cat, 17, True, MUTED, "ctr")
        self.pill(884, 240, 170, "Для решения")
        self.label(890, 292, 323, 110, page["callout"], 33, True, BLUE)
        self.label(890, 408, 323, 181, page["explain"], 22, False, BODY)

    def steps(self, page):
        items = page["items"]
        if not 2 <= len(items) <= 4:
            raise ValueError("Нужны два–четыре шага.")
        gap = 15
        width = (1194-gap*(len(items)-1))/len(items)
        for i, item in enumerate(items):
            x = 43+i*(width+gap)
            self.component("card", x, 224, width, 389)
            self.pill(x+14, 239, min(width-28, 95), f"Шаг {i+1}")
            self.label(x+18, 293, width-36, 82, item["headline"], 27, True, NAVY)
            self.label(x+18, 383, width-36, 88, item["value"], 32, True, BLUE)
            self.label(x+18, 478, width-36, 119, item["detail"], 22, False, BODY)

    def choice(self, page):
        if len(page["items"]) != 2:
            raise ValueError("Нужны две сравнимые позиции.")
        for i, item in enumerate(page["items"]):
            x = 43+i*604
            self.component("card", x, 224, 590, 389)
            self.pill(x+17, 241, min(500,max(176,len(item["headline"])*10+32)), item["headline"])
            self.label(x+24, 305, 545, 104, item["value"], 36, True, BLUE)
            self.shape(x+24, 419, 531, 1, LINE)
            self.label(x+24, 445, 540, 140, item["detail"], 24, False, BODY)


def cover(s, fields, pack, style):
    s.shape(0, 0, 643, 720, BLUE)
    s.label(48, 53, 542, 50, style["project"], 25, True, WHITE)
    s.label(48, 169, 551, 240, fields["title"], 58, True, WHITE)
    s.label(49, 470, 531, 174, fields["lead"], 27, False, WHITE)
    s.label(694, 70, 505, 68, "Содержание", 40, True, NAVY)
    for i, item in enumerate(pack["agenda"]):
        y = 184+i*109
        s.pill(695, y, 100, f'{item["from"]:02d}–{item["to"]:02d}' if item["from"] != item["to"] else f'{item["from"]:02d}')
        s.label(816, y-1, 357, 79, item["label"], 25, True, NAVY)
        s.shape(694, y+79, 503, 1, LINE)


def summary(s, fields, style):
    s.heading(fields["title"], style.get("summary_context"))
    panels = [(43,372), (428,390), (831,406)]
    for (x,w), title in zip(panels, ("Анализ проблемы","Инициатива","Результат")):
        s.component("card",x,204,w,407)
        s.pill(x+13,218,min(w-26, max(160,len(title)*12+32)),title)
        s.shape(x+16, 425, w-32, 1, LINE)
    rows = style.get("summary_rows", [{},{}])
    if not isinstance(rows,list) or len(rows) != 2 or any(not isinstance(r,dict) for r in rows):
        raise ValueError("В executive summary нужны две строки сравнения.")
    for i, (key, row) in enumerate(zip("AB",rows)):
        y = 269+i*177
        s.label(62,y,335,45,row.get("reach",fields["label"+key]),29,True,BLUE)
        s.label(62,y+53,332,107,fields["problem"+key],21,False,BODY)
        s.label(448,y,350,45,row.get("action",fields["label"+key]),25,True,NAVY)
        s.label(448,y+53,347,107,fields["action"+key],21,False,BODY)
        result = row.get("outcome",fields["value"+key])
        s.label(851,y,371,45,result,31,True,BLUE)
        s.label(851,y+50,361,77,fields["result"+key],20,False,BODY)
        if "outcome" in row:
            s.label(851,y+137,360,28,"Скоринг "+fields["value"+key].removeprefix("Скоринг "),16,True,MUTED)
    s.takeaway(fields["takeaway"])


def journey(s, base, fields, style, n):
    editorial = style.get("journeys", {}).get(str(n), {})
    s.heading(fields["title"], editorial.get("lead",fields["actor"]))
    s.component("card",43,219,557,401)
    s.pill(58,228,190,fields["example"])
    # Preserve the team's original product component and its native editable labels.
    for sp in base.findall(".//{*}sp"):
        p = sp.find("./{*}nvSpPr/{*}cNvPr")
        if p is None or p.get("name") not in ("UI-CARD","actor","message","action"):continue
        clone = deepcopy(sp)
        off = clone.find("./{*}spPr/{*}xfrm/{*}off")
        if off is not None: off.set("y",str(int(off.get("y")) + 15*9525))
        s.index += 1
        clone.find("./{*}nvSpPr/{*}cNvPr").set("id",str(s.index))
        s.tree.append(clone)
    headers = editorial.get("stages",["Условие","Действие","Подтверждение"])
    for i, key in enumerate("ABC"):
        y = 219+i*139
        s.component("card",617,y,620,123)
        s.pill(630,y+10, min(380,max(130,len(headers[i])*10+24)),headers[i])
        s.label(636,y+53,577,64,fields["step"+key],23,False,BODY)
    if editorial.get("outcome"):s.takeaway(editorial["outcome"])


def paired(s, fields):
    s.heading(fields["title"], fields["lead"])
    for i,key in enumerate("AB"):
        x=43+i*605
        s.component("card",x,232,589,376)
        s.pill(x+21,249,188,"Условие расчёта")
        s.label(x+27,306,529,99,fields["value"+key],64,True,BLUE)
        s.shape(x+28,416,517,1,LINE)
        s.label(x+28,447,518,128,fields["label"+key],27,False,BODY)
    s.takeaway(fields["takeaway"])


def decision(s, fields):
    s.heading(fields["title"],fields["lead"])
    for i,key in enumerate("ABC"):
        x=43+i*403
        s.component("card",x,245,388,336)
        s.pill(x+15,263,205,fields["label"+key])
        s.label(x+20,331,346,204,fields["detail"+key],25,False,BODY)
        s.component("track",x+21,548,343,10)
        s.component("bar",x+21,548,(i+1)*343/3,10)


def render(base, page, pos, pack, style, fields=None):
    slide = ConsultingSlide(base)
    if not isinstance(style,dict) or not isinstance(style.get("project"),str) or len(style.get("tabs",[])) != 4:
        raise ValueError("Для оформления нужны название проекта и четыре раздела.")
    if page == 1:
        cover(slide,fields,pack,style)
        return slide.root
    active=next(i for i,entry in enumerate(pack["agenda"]) if entry["from"]<=pos<=entry["to"])
    slide.navigation(style["project"], style["tabs"], active, pos)
    if isinstance(page,dict):
        slide.heading(page["title"],page["context"])
        getattr(slide,page["kind"])(page)
        slide.takeaway(page["implication"])
    elif page==2:summary(slide,fields,style)
    elif page in (3,4):journey(slide,base,fields,style,page)
    elif page==5:paired(slide,fields)
    else:decision(slide,fields)
    return slide.root
