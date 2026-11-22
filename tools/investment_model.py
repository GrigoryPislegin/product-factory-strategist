"""Собрать переносимую редактируемую модель двух вариантов средствами стандартного Python."""
import csv
import io
import itertools
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
FIELDS = ["option","scenario","period","units","additional_per_unit","margin","operating","investment","source"]
METRICS = ["Вариант","Сценарий","Период","Единиц","Доп. исходов на единицу","Вклад одного исхода","Прямые расходы","Инвестиции","Источник / статус","Доп. исходы","Валовой вклад","После инвестиций","Накоплено"]
BOOK = Path(__file__).resolve().parents[1] / "templates/investment-base.xlsx"


def blank(options):
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(FIELDS)
    for option,scenario,period in itertools.product(options or ["A","B"],("base","stress"),("1","2")):
        writer.writerow([option,scenario,period]+[""]*6)
    return out.getvalue().encode()


def sheet(matrix, widths, input_sheet=False):
    root=ET.Element("worksheet",xmlns=NS)
    cols=ET.SubElement(root,"cols")
    for i,w in enumerate(widths,1):
        ET.SubElement(cols,"col",min=str(i),max=str(i),width=str(w),customWidth="1")
    data=ET.SubElement(root,"sheetData")
    for rowno,values in enumerate(matrix,1):
        row=ET.SubElement(data,"row",r=str(rowno),ht="25",customHeight="1")
        for idx,value in enumerate(values):
            reference=f"{chr(65+idx)}{rowno}"
            style=1 if rowno==1 else (2 if input_sheet and 3<=idx<=7 else 0)
            cell=ET.SubElement(row,"c",r=reference,s=str(style))
            if isinstance(value,tuple):
                formula,result=value
                ET.SubElement(cell,"f").text=formula
                ET.SubElement(cell,"v").text=str(result)
            elif isinstance(value,Decimal):
                ET.SubElement(cell,"v").text=str(value)
            else:
                cell.set("t","inlineStr")
                ET.SubElement(ET.SubElement(cell,"is"),"t").text=value
    return ET.tostring(root,encoding="utf-8",xml_declaration=True)


def render(path, options):
    with path.open(encoding="utf-8-sig",newline="") as stream:
        reader=csv.DictReader(stream)
        if reader.fieldnames!=FIELDS:
            raise ValueError("В финансовом CSV нужны колонки "+", ".join(FIELDS))
        records=list(reader)
    opts=list(dict.fromkeys(r["option"] for r in records))
    if len(opts)!=2 or (options and set(opts)!=set(options)):
        raise ValueError("Финансовая модель сравнивает два выбранных варианта.")
    scenarios=("base","stress")
    if any(r["scenario"] not in scenarios for r in records):
        raise ValueError("Сценарий модели должен иметь значение base или stress.")
    model=[METRICS]
    summary=[["Вариант","Сценарий","Доп. исходы","Валовой вклад","Инвестиции","После инвестиций"]]
    periods=None
    for option,scenario in itertools.product(opts,scenarios):
        rows=[r for r in records if r["option"]==option and r["scenario"]==scenario]
        sequence=[r["period"] for r in rows]
        if not sequence or any(not p.strip() for p in sequence) or len(sequence)!=len(set(sequence)) or (periods is not None and sequence!=periods):
            raise ValueError("Во всех четырёх сценариях укажите одинаковые уникальные периоды по порядку.")
        periods=sequence
        start=len(model)+1
        total=[Decimal(0)]*4
        for r in rows:
            if not r.get("source") or not r["source"].strip():
                raise ValueError("Укажите источник или статус допущений каждой строки финансовой модели.")
            try:
                numbers=[Decimal(r[k]) for k in FIELDS[3:8]]
            except (InvalidOperation,TypeError):
                raise ValueError("Заполните числовые допущения финансовой модели.") from None
            if not all(n.is_finite() and abs(n)<Decimal("1e30") for n in numbers) or any(numbers[i]<0 for i in (0,3,4)):
                raise ValueError("Проверьте знаки и конечность значений финансовой модели.")
            units,effect,margin,operating,capex=numbers
            outcomes=units*effect
            gross=outcomes*margin-operating
            net=gross-capex
            total=[a+b for a,b in zip(total,(outcomes,gross,capex,net))]
            i=len(model)+1
            model.append([option,scenario,r["period"],*numbers,r["source"],
                          (f"D{i}*E{i}",outcomes),(f"J{i}*F{i}-G{i}",gross),
                          (f"K{i}-H{i}",net),(f"SUM(L{start}:L{i})",total[3])])
        end=len(model)
        summary.append([option,scenario,*[(f"SUM('Периоды'!{col}{start}:{col}{end})",v) for col,v in zip("JKHL",total)]])
    parts={"xl/worksheets/sheet1.xml":sheet(summary,[26,15,20,22,18,23]),
           "xl/worksheets/sheet2.xml":sheet(model,[24,14,18,18,28,25,20,18,68,19,19,24,23],True)}
    result=io.BytesIO()
    with ZipFile(BOOK) as base,ZipFile(result,"w") as out:
        for name in base.namelist():
            info=ZipInfo(name,(2026,1,1,0,0,0))
            out.writestr(info,parts.get(name,base.read(name)),compress_type=ZIP_DEFLATED)
    return result.getvalue()
