import fs from 'node:fs/promises';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
import {fileURLToPath} from 'node:url';
const dir=fileURLToPath(new URL('.',import.meta.url)), book=Workbook.create();
const [sum,build,inp]=['Решение','Когорты','Допущения'].map(n=>book.worksheets.add(n));
const csv=(await fs.readFile(dir+'/scenarios.csv','utf8')).trim().split('\n').slice(1).map(x=>x.split(','));
const baseline=(await fs.readFile(new URL('../../demo/family/baseline.csv',import.meta.url),'utf8')).split('\n')[1].split(',');
const labels=['Семьи · база','Семьи · стресс','Свои номера · база','Свои номера · стресс'];
const cols=['B','C','D','E'], R=(sh,a)=>sh.getRange(a);
const val=(sh,cell,v)=>R(sh,cell).values=[[v]],formula=(sh,cell,v)=>R(sh,cell).formulas=[['='+v]];
function title(sh,txt){sh.showGridLines=false;sh.getRange('A1:E1').merge();val(sh,'A1',txt);const r=R(sh,'A1:E1');r.format.fill='#213762';r.format.font.color='#ffffff';r.format.font.bold=true;r.format.font.size=17;r.format.rowHeight=38;R(sh,'A:A').format.columnWidth=47;R(sh,'B:E').format.columnWidth=23;R(sh,'A3:E42').format.rowHeight=19;}
function band(sh,n,txt){val(sh,'A'+n,txt);let r=R(sh,'A'+n+':E'+n);r.format.fill='#e5efff';r.format.font.bold=true;r.format.font.color='#204f9b';r.format.rowHeight=24;}
function hdr(sh,n){for(let i=0;i<4;i++)val(sh,cols[i]+n,labels[i]);R(sh,'B'+n+':E'+n).format.font.bold=true;}
function labelsAt(sh,n,values){values.forEach((v,i)=>val(sh,'A'+(n+i),v));}
function fmt(sh,r,format){sh.getRange(r).setNumberFormat(format);}
title(inp,'Допущения и источники · плановый год');band(inp,3,'Значения из учебного брифа');labelsAt(inp,4,['Валовая прибыль без изменений, ₽','Минимальная цель прибыли, ₽','Вклад оплаченного номеро-месяца, ₽','Недель набора на квартал']);[+baseline[4]*1e6,+baseline[5]*1e6,500,13].forEach((v,i)=>val(inp,'B'+(4+i),v));val(inp,'C4','Бриф, стр. 3');val(inp,'C5','Бриф, стр. 3');val(inp,'C6','Бриф, стр. 9');val(inp,'C7','Допущение плана: II–IV кв.');
band(inp,9,'Изменяемые параметры');hdr(inp,9);
labelsAt(inp,10,['Доступные семьи / владельцы, ед.','Доля первых рисков в неделю','Совместная доля пригодных среди первых рисков','Охват среди пригодных','Доп. месяцы в квартале включения','Доп. месяцы в следующем квартале','Доп. месяцы через два квартала','Новые прямые расходы за год, ₽','Разработка во II квартале, ₽']);
csv.forEach((row,i)=>row.slice(2).forEach((v,j)=>val(inp,cols[i]+(10+j),Number(v))));
R(inp,'B10:E18').format.fill='#eff5ff';R(inp,'B10:E18').format.font.color='#2459ad';fmt(inp,'B11:E13','0.0%');fmt(inp,'B14:E16','0.00');fmt(inp,'B17:E18','#,##0');fmt(inp,'B4:B7','#,##0');
for(const [r,txt] of [[21,'Доступные базы и ставка — числа из брифа. Остальные параметры сценариев — учебные допущения.'],[22,'Семьи и владельцы сравниваются отдельно. Для каждого целевого номера учитывается только первый эпизод.'],[23,'Измените любую голубую ячейку. Вклад, разрыв до цели и пороги на первом листе пересчитаются.']]){R(inp,'A'+r+':E'+r).merge();val(inp,'A'+r,txt);}
title(build,'Календарные когорты · дополнительные результаты');band(build,3,'Воронка');hdr(build,3);labelsAt(build,4,['Первые риски за неделю, ед.','Пригодные в неделю, ед.','Включены за квартал, ед.']);band(build,8,'Дополнительные оплаченные месяцы');labelsAt(build,9,['I квартал','II квартал','III квартал','IV квартал']);band(build,14,'Вклад после прямых расходов, ₽');labelsAt(build,15,['I квартал','II квартал','III квартал','IV квартал']);band(build,20,'Накоплено после разработки, ₽');labelsAt(build,21,['I квартал','II квартал','III квартал','IV квартал']);
for(const c of cols){const src=r=>"'Допущения'!"+c+r;
const f=(r,form)=>formula(build,c+r,form);
f(4,src(10)+'*'+src(11));f(5,c+'4*'+src(12));f(6,c+"5*"+src(13)+"*'Допущения'!$B$7");val(build,c+'9',0);f(10,c+'6*'+src(14));f(11,c+'6*('+src(14)+'+'+src(15)+')');f(12,c+'6*SUM('+src(14)+':'+c+'16)');
val(build,c+'15',0);for(let q=0;q<3;q++)f(16+q,c+(10+q)+"*'Допущения'!$B$6-"+src(17)+'/3');
f(21,c+'15');f(22,c+'21+'+c+'16-'+src(18));f(23,c+'22+'+c+'17');f(24,c+'23+'+c+'18');}
fmt(build,'B4:E24','#,##0.0;[Red](#,##0.0);–');
title(sum,'Решение · окупаемость двух пилотов');band(sum,3,'Результаты планового года');hdr(sum,3);
labelsAt(sum,4,['Пригодные в неделю, ед.','Дополнительные номеро-месяцы за год','Дополнительная валовая прибыль, ₽','Валовая прибыль оператора, ₽','Недобор до годовой цели, ₽','Вложения в разработку, ₽','Итог после разработки, ₽','Первый квартал окупаемости']);
for(const c of cols){const f=(r,v)=>formula(sum,c+r,v);f(4,"'Когорты'!"+c+'5');f(5,"SUM('Когорты'!"+c+'9:'+c+'12)');f(6,"SUM('Когорты'!"+c+'15:'+c+'18)');f(7,"'Допущения'!$B$4+"+c+'6');f(8,"'Допущения'!$B$5-"+c+'7');f(9,"'Допущения'!"+c+'18');f(10,"'Когорты'!"+c+'24');f(11,'IF(\'Когорты\'!'+c+'22>=0,"II",IF(\'Когорты\'!'+c+'23>=0,"III",IF(\'Когорты\'!'+c+'24>=0,"IV","За пределами года")))');}
band(sum,14,'Порог выбора · базовые сценарии');labelsAt(sum,15,['Вклад одного добавочного случая/нед. за год, ₽','Минимум случаев/нед. для годовой цели','Порог для опережения другого пилота, ед./нед.']);
for(const [c,other] of [['B','D'],['D','B']]){formula(sum,c+'15',"'Допущения'!$B$6*'Допущения'!$B$7*'Допущения'!"+c+"13*(3*'Допущения'!"+c+"14+2*'Допущения'!"+c+"15+'Допущения'!"+c+"16)");formula(sum,c+'16','IF('+c+'15<=0,"Неприменимо",ROUNDUP((\'Допущения\'!$B$5-\'Допущения\'!$B$4+\'Допущения\'!'+c+'17)/'+c+'15,0))');formula(sum,c+'17','IF('+c+'15<=0,"Неприменимо",MAX(0,INT(('+other+'10+\'Допущения\'!'+c+'17+\'Допущения\'!'+c+'18)/'+c+'15)+1))');}
fmt(sum,'B4:E10','#,##0;[Red](#,##0);–');fmt(sum,'B15:E17','#,##0;[Red](#,##0);–');
for (const [r,txt] of [[20,'Сравнивайте строку 10 при одинаковом горизонте. Разработка учтена после валовой прибыли.'],[21,'В строке 17 держим другой пилот на его базовом потоке. Для победы нужен строго лучший результат.'],[22,'Все сценарии условны. До инвестиционного решения нужны срез биллинга, подтверждение прав и смета.']]) {R(sum,'A'+r+':E'+r).merge();val(sum,'A'+r,txt);}
const out=await SpreadsheetFile.exportXlsx(book);await out.save(dir+'/investment-model.xlsx');
console.log('итоги',JSON.stringify(sum.getRange('B10:E10').values),'переключение',JSON.stringify(sum.getRange('B17:E17').values));
