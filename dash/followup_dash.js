// Aba "Avanço por Talhão" (antiga "Follow-up por Talhão") dos dashboards GN.
// Lê CDO_PRODUCAO (REND-Boletim de Produção) + CAD_TALHOES da base e injeta uma aba nova no HTML.
// Realizado = soma da Produção (Tipo Recurso = Principal, Produção > 0, sem APOIO E MANUTENÇÃO)
// por CR + Cód. Projeto + Talhão + Operação + Competência. % = Realizado ÷ Área do talhão (só operações em HA).
'use strict';

function txt(v) { return v === null || v === undefined ? '' : String(v).trim(); }
function num(v) { const n = typeof v === 'number' ? v : parseFloat(String(v).replace(',', '.')); return isFinite(n) ? n : 0; }
function chaveTal(v) {
  if (typeof v === 'number' && Number.isInteger(v)) return String(v);
  const s = txt(v);
  return /^\d+$/.test(s) ? String(parseInt(s, 10)) : s.toUpperCase();
}
function xlData(v) {
  if (typeof v === 'number') { const d = new Date(Date.UTC(1899, 11, 30) + Math.round(v) * 86400000); return d.toISOString().slice(0, 10); }
  return '';
}

function montarDados(grids) {
  const prod = grids['REND-Boletim de Produção'] || [];
  const cad = grids['CAD_TALHOES'] || [];
  const hdr = (prod[4] || []).map(txt);
  const ix = n => hdr.indexOf(n);
  const I = { cdo: ix('CDO'), data: ix('Data'), cr: ix('CR'), codp: ix('Cod. Projeto'), proj: ix('Projeto'), tal: ix('Talhao'),
    op: ix('Operacao'), und: ix('Und. Medida'), prod: ix('Producao'), tipo: ix('Tipo Recurso'), comp: ix('Competência'),
    enc: ix('Encarregado') };
  for (const k in I) if (I[k] < 0) throw new Error('Follow-up: coluna não encontrada em CDO_PRODUCAO: ' + k);

  const D = { cr: [], faz: [], tal: [], op: [], und: [], comp: [], dt: [] }, M = {};
  for (const k in D) M[k] = new Map();
  const id = (k, v) => { let i = M[k].get(v); if (i === undefined) { i = D[k].length; D[k].push(v); M[k].set(v, i); } return i; };

  // fazendas (CR|codp) -> nome; talhões com área
  const fazNome = new Map(), area = new Map(), origem = new Map();
  const hc = (cad[0] || []).map(txt);
  const C = { cr: hc.indexOf('CR'), codp: hc.indexOf('Cód. Projeto'), faz: hc.indexOf('Fazenda'), tal: hc.indexOf('Talhão'),
    area: hc.indexOf('Área (ha)'), org: hc.indexOf('Origem') };
  for (let i = 1; i < cad.length; i++) {
    const r = cad[i] || []; const cr = txt(r[C.cr]); if (!/^GN\d{4}$/.test(cr)) continue;
    const fk = cr + '|' + txt(r[C.codp]);
    if (!fazNome.has(fk)) fazNome.set(fk, txt(r[C.faz]));
    const tk = fk + '|' + chaveTal(r[C.tal]);
    if (r[C.area] !== '' && r[C.area] !== null && r[C.area] !== undefined) area.set(tk, num(r[C.area]));
    origem.set(tk, txt(r[C.org]));
  }

  const agg = new Map(), ultData = new Map(), undOp = new Map();
  for (let i = 5; i < prod.length; i++) {
    const r = prod[i] || []; const cr = txt(r[I.cr]); if (!/^GN\d{4}$/.test(cr)) continue;
    if (txt(r[I.tipo]) !== 'Principal') continue;
    const op = txt(r[I.op]); if (!op || /^APOIO E MANUT/i.test(op)) continue;
    const p = num(r[I.prod]); if (p <= 0) continue;
    const codp = txt(r[I.codp]), fk = cr + '|' + codp;
    if (!fazNome.has(fk)) fazNome.set(fk, txt(r[I.proj]));
    const tal = chaveTal(r[I.tal]);
    const comp = txt(r[I.comp]);
    const dt = xlData(r[I.data]);
    const k = [fk, tal, op, comp, dt].join('§');
    agg.set(k, (agg.get(k) || 0) + p);
    undOp.set(op, txt(r[I.und]).toUpperCase());
    if (dt > (ultData.get(fk) || '')) ultData.set(fk, dt);
  }

  // fazendas: id -> {cr, codp, nome, ult}
  const fazendas = [], fazIdx = new Map();
  const fazId = fk => {
    if (fazIdx.has(fk)) return fazIdx.get(fk);
    const [cr, codp] = fk.split('|');
    const i = fazendas.length; fazendas.push([id('cr', cr), codp, fazNome.get(fk) || codp, ultData.get(fk) || '']); fazIdx.set(fk, i); return i;
  };
  // talhões: [faz, tal, area|null, origem]
  const talhoes = [], talIdx = new Map();
  const talId = (fk, tal) => {
    const k = fk + '|' + tal; if (talIdx.has(k)) return talIdx.get(k);
    const i = talhoes.length; talhoes.push([fazId(fk), tal, area.has(k) ? area.get(k) : null, origem.get(k) || '']); talIdx.set(k, i); return i;
  };
  // cadastrar todos os talhões com área (mesmo sem produção) das fazendas que têm produção
  const fazComProd = new Set([...agg.keys()].map(k => k.split('§')[0]));
  for (const tk of area.keys()) { const p = tk.split('|'); const fk = p[0] + '|' + p[1]; if (fazComProd.has(fk)) talId(fk, p.slice(2).join('|')); }
  const rows = [];
  for (const [k, v] of agg) {
    const [fk, tal, op, comp, dt] = k.split('§');
    rows.push([talId(fk, tal), id('op', op), id('comp', comp), id('dt', dt), Math.round(v * 100) / 100]);
  }
  D.und = D.op.map(o => undOp.get(o) || '');
  return { cr: D.cr, op: D.op, und: D.und, comp: D.comp, dt: D.dt, faz: fazendas, tal: talhoes, rows };
}

function filtrar(dados, crs) {
  if (!crs) return dados;
  const okCr = new Set(dados.cr.map((c, i) => crs.indexOf(c) >= 0 ? i : -1).filter(i => i >= 0));
  const fazOk = new Set(dados.faz.map((f, i) => okCr.has(f[0]) ? i : -1).filter(i => i >= 0));
  const talOk = new Set(dados.tal.map((t, i) => fazOk.has(t[0]) ? i : -1).filter(i => i >= 0));
  return Object.assign({}, dados, { rows: dados.rows.filter(r => talOk.has(r[0])) });
}

const CSS = `
#fupRoot{display:none;position:fixed;inset:0;top:38px;overflow:auto;background:#001450;color:#E8EEF8;font-family:inherit;z-index:9000;padding:16px 20px 40px}
#fupRoot.solo{display:block;position:static;min-height:100vh}
#fupRoot h2{margin:0 0 4px;font-size:20px}
#fupRoot .fup-sub{color:#8AA0C0;font-size:12px;margin-bottom:14px}
#fupRoot .fup-ctl{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px;align-items:flex-end}
#fupRoot .fup-ctl label{font-size:11px;color:#8AA0C0;text-transform:uppercase;letter-spacing:.05em;display:flex;flex-direction:column;gap:4px}
#fupRoot select{background:#12294D;color:#E8EEF8;border:1px solid #2E5FA3;border-radius:6px;padding:7px 10px;font-size:13px;min-width:150px}
#fupRoot .fup-seg{display:flex;border:1px solid #2E5FA3;border-radius:6px;overflow:hidden}
#fupRoot .fup-seg button{background:#12294D;color:#8AA0C0;border:0;padding:8px 14px;font-size:12px;cursor:pointer;font-family:inherit}
#fupRoot .fup-seg button.on{background:#2E5FA3;color:#fff;font-weight:700}
#fupRoot .fup-info{font-size:12px;color:#8AA0C0;margin-bottom:10px}
#fupRoot .fup-info b{color:#E8EEF8}
#fupRoot .fup-tal{background:#0D1F55;border:1px solid rgba(46,95,163,.35);border-radius:10px;padding:12px 16px;margin-bottom:12px}
#fupRoot .fup-tal.ok{border-color:rgba(39,174,96,.45)}
#fupRoot .fup-tal .hd{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;gap:10px}
#fupRoot .fup-tal .hd b{font-size:15px}
#fupRoot .fup-tal .hd span{font-size:11px;color:#8AA0C0}
#fupRoot .fup-ln{display:grid;grid-template-columns:minmax(220px,34%) 1fr minmax(230px,auto);gap:14px;align-items:center;padding:5px 0;border-top:1px solid rgba(46,95,163,.12)}
#fupRoot .fup-ln .nm{font-size:12px;color:#C9D6EA;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#fupRoot .fup-ln .tr{height:12px;border-radius:6px;background:rgba(255,255,255,.08);overflow:hidden}
#fupRoot .fup-ln .tr i{display:block;height:100%;border-radius:6px}
#fupRoot .fup-ln .vl{font-size:12px;text-align:right;white-space:nowrap}
#fupRoot .fup-ln .vl span{color:#8AA0C0}
#fupRoot h3{font-size:14px;margin:0 0 8px;color:#C9D6EA}
#fupRoot .fup-wrap{overflow:auto;border-radius:8px;border:1px solid rgba(46,95,163,.35);margin-bottom:18px}
#fupRoot table{border-collapse:separate;border-spacing:0;font-size:12px;width:100%}
#fupRoot th{background:#0A2163;color:#C9D6EA;font-weight:600;padding:8px 10px;text-align:center;border-bottom:1px solid #2E5FA3;text-transform:uppercase;font-size:11px;letter-spacing:.03em}
#fupRoot th:first-child{text-align:left}
#fupRoot td{padding:7px 10px;text-align:center;border-bottom:1px solid rgba(46,95,163,.15)}
#fupRoot td.at{text-align:left;font-weight:600;white-space:normal;max-width:460px;background:#0D1F55}
#fupRoot td.gr{text-align:left;background:#0A2163;font-weight:700;color:#F5A623;padding:8px 10px}
#fupRoot td.gr span{color:#8AA0C0;font-weight:400}
#fupRoot .pill{display:inline-block;min-width:46px;padding:2px 8px;border-radius:10px;font-weight:700}
#fupRoot .fup-leg{display:flex;gap:16px;flex-wrap:wrap;font-size:11px;color:#8AA0C0;margin:12px 0 0}
#fupRoot .fup-leg i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-2px}
@media (max-width:760px){#fupRoot{padding:12px}#fupRoot .fup-ln{grid-template-columns:1fr;gap:4px}#fupRoot .fup-ln .vl{text-align:left}}
`;

const JS = `
(function(){
var F=window.__FUP__, VIEW='barras';
var VERDE='#27AE60',LAR='#F5A623',AZUL='#4F7BC4',VERM='#E74C3C';
function $(id){return document.getElementById(id);}
function fmt(v){return Number(v).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});}
function pct(v,d){return (v*100).toLocaleString('pt-BR',{maximumFractionDigits:d||0})+'%';}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');}
function dBR(i){return i&&i!=='9'?i.split('-').reverse().join('/'):'—';}
function pill(p){return p==null?'—':'<span class="pill" style="background:'+(p>=0.995?'rgba(39,174,96,.35)':'rgba(245,166,35,.35)')+'">'+pct(p)+'</span>';}
var porTal={};F.rows.forEach(function(r){(porTal[r[0]]=porTal[r[0]]||[]).push(r);});
function fazendasDoCR(cr){var o=[];F.faz.forEach(function(f,i){if(F.cr[f[0]]===cr)o.push(i);});return o;}
function temProd(fi){for(var t=0;t<F.tal.length;t++){if(F.tal[t][0]===fi&&porTal[t])return true;}return false;}
function ordTal(a,b){var x=F.tal[a][1],y=F.tal[b][1],nx=/^\\d+$/.test(x),ny=/^\\d+$/.test(y);if(nx&&ny)return x-y;if(nx)return -1;if(ny)return 1;return x.localeCompare(y);}
function talsSel(){var fi=+$('fupFaz').value,ti=+$('fupTal').value,o=[];F.tal.forEach(function(t,i){if(t[0]===fi&&(ti<0||i===ti))o.push(i);});return o.sort(ordTal);}
function compSel(){var c=$('fupComp').value;return c?F.comp.indexOf(c):-1;}
function atvSel(){var v=$('fupAtv').value;return v===''?-1:+v;}
function soAtv(ops){var a=atvSel();return a<0?ops:ops.filter(function(o){return o===a;});}
function agreg(lst,ci){var ag={},set={};lst.forEach(function(t){set[t]=1;});
  lst.forEach(function(t){(porTal[t]||[]).forEach(function(r){if(ci>=0&&r[2]!==ci)return;
    var a=ag[r[1]]=ag[r[1]]||{v:0,ini:'9',fim:'',dias:{}};a.v+=r[4];var d=F.dt[r[3]];a.dias[d]=1;if(d<a.ini)a.ini=d;if(d>a.fim)a.fim=d;});});return ag;}
function opsOrd(ag){return Object.keys(ag).map(Number).sort(function(a,b){return F.op[a].localeCompare(F.op[b]);});}
function preencher(){
  var crs=[];F.cr.forEach(function(c,i){if(F.faz.some(function(f,fi){return f[0]===i&&temProd(fi);}))crs.push(c);});
  crs.sort();$('fupCR').innerHTML=crs.map(function(c){return '<option>'+c+'</option>';}).join('');
  var MES=['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
  var comps=F.comp.slice().sort(function(a,b){var pa=a.split('-'),pb=b.split('-');return (pb[1]-pa[1])||(MES.indexOf(pb[0])-MES.indexOf(pa[0]));});
  $('fupComp').innerHTML='<option value="">Acumulado (todas)</option>'+comps.map(function(c){return '<option>'+c+'</option>';}).join('');
  trocarCR();
}
function trocarCR(){
  var lst=fazendasDoCR($('fupCR').value).filter(temProd);
  lst.sort(function(a,b){return F.faz[a][2].localeCompare(F.faz[b][2]);});
  $('fupFaz').innerHTML=lst.map(function(i){return '<option value="'+i+'">'+esc(F.faz[i][2])+'</option>';}).join('');
  var rec=lst.slice().sort(function(a,b){return (F.faz[b][3]||'').localeCompare(F.faz[a][3]||'');})[0];
  if(rec!==undefined)$('fupFaz').value=rec;
  trocarFaz();
}
function trocarFaz(){
  var fi=+$('fupFaz').value,tals=[];F.tal.forEach(function(t,i){if(t[0]===fi)tals.push(i);});tals.sort(ordTal);
  $('fupTal').innerHTML='<option value="-1">Todos os talhões</option>'+tals.map(function(t){return '<option value="'+t+'">Talhão '+esc(F.tal[t][1])+'</option>';}).join('');
  var atual=$('fupAtv').value,ops=opsOrd(agreg(tals,-1));
  $('fupAtv').innerHTML='<option value="">Todas as atividades</option>'+ops.map(function(o){return '<option value="'+o+'">'+esc(F.op[o])+'</option>';}).join('');
  if(atual!==''&&ops.indexOf(+atual)>=0)$('fupAtv').value=atual;
  render();
}
function render(){
  ['barras','tabela','concl'].forEach(function(v){$('fupV_'+v).className=VIEW===v?'on':'';});
  $('fupLeg').style.display=VIEW==='barras'?'':'none';
  if(isNaN(+$('fupFaz').value)){$('fupMain').innerHTML='';return;}
  if(VIEW==='tabela')tabela();else barras(VIEW==='concl');
}
function barras(soConcl){
  var ci=compSel(),tals=talsSel(),h='',nAt=0,nTal=0,haT=0,ai=atvSel(),cnt={c:0,a:0,p:0,s:0};
  tals.forEach(function(t){var T=F.tal[t],ag=agreg([t],ci),ops=soAtv(opsOrd(ag));
    if(soConcl){if(!T[2])return;ops=ops.filter(function(o){if(F.und[o]!=='HA')return false;var p=ag[o].v/T[2];return p>=0.98&&p<=1.05;});}
    if(ai>=0&&!soConcl){
      if(!ops.length){cnt.p++;nTal++;
        h+='<div class="fup-tal"><div class="hd"><b>Talhão '+esc(T[1])+'</b><span>'+(T[2]!=null?fmt(T[2])+' ha':'sem área cadastrada')+' · sem apontamento</span></div>'+
          '<div class="fup-ln"><span class="nm" title="'+esc(F.op[ai])+'">'+esc(F.op[ai])+'</span><div class="tr"><i style="width:0"></i></div><span class="vl"><b style="color:'+VERM+'">0% · pendente</b></span></div></div>';
        return;}
      var a0=ag[ai];if(F.und[ai]==='HA'&&T[2]){if(a0.v/T[2]>=0.98)cnt.c++;else cnt.a++;}else cnt.s++;
    }
    if(!ops.length)return;nTal++;
    h+='<div class="fup-tal'+(soConcl?' ok':'')+'"><div class="hd"><b>Talhão '+esc(T[1])+'</b><span>'+(T[2]!=null?fmt(T[2])+' ha':'sem área cadastrada')+' · '+ops.length+' atividade(s)'+(soConcl?' concluída(s)':'')+'</span></div>';
    ops.forEach(function(o){var a=ag[o],u=F.und[o]||'',ha=u==='HA'&&T[2],p=ha?a.v/T[2]:null,w=ha?Math.min(p,1)*100:100,cor=ha?(p>=0.995?VERDE:LAR):AZUL;
      nAt++;haT+=ha?a.v:0;
      h+='<div class="fup-ln"><span class="nm" title="'+esc(F.op[o])+'">'+esc(F.op[o])+'</span><div class="tr"><i style="width:'+w+'%;background:'+cor+(ha?'':';opacity:.55')+'"></i></div>'+
        '<span class="vl"><b>'+(p!=null?pct(p,soConcl?1:0)+' · ':'')+fmt(a.v)+' '+u.toLowerCase()+'</b> <span>· '+(soConcl?dBR(a.ini)+' a '+dBR(a.fim):'últ. '+dBR(a.fim))+'</span></span></div>';});
    h+='</div>';});
  if(ai>=0&&!soConcl){var hasHA=F.und[ai]==='HA';
    $('fupMain').innerHTML='<div class="fup-info">Atividade <b>'+esc(F.op[ai])+'</b> · <b>'+tals.length+'</b> talhão(ões)'+
      (hasHA?' · <b>'+cnt.c+'</b> concluído(s) · <b>'+cnt.a+'</b> em andamento':'')+(cnt.s?' · <b>'+cnt.s+'</b> com apontamento (sem % de área)':'')+' · <b style="color:'+VERM+'">'+cnt.p+'</b> pendente(s)</div>'+h;
    return;}
  var info=soConcl?'<div class="fup-info">Atividades com realização entre <b>98% e 105%</b> da área do talhão · <b>'+nAt+'</b> atividade(s) em <b>'+nTal+'</b> talhão(ões) · <b>'+fmt(haT)+' ha</b> concluídos</div>':'';
  $('fupMain').innerHTML=info+(h||'<div class="fup-info" style="padding:16px 0">'+(soConcl?'Nenhuma atividade concluída para o filtro.':'Sem apontamento para o filtro.')+'</div>');
}
function tabela(){
  var ci=compSel(),tals=talsSel(),fi=+$('fupFaz').value,ti=+$('fupTal').value,cs=$('fupComp').value;
  var cab='<thead><tr><th>Atividade</th><th>Und.</th><th>Realizado</th><th>Área (ha)</th><th>% da área</th><th>Dias apontados</th><th>1º apontamento</th><th>Último apontamento</th></tr></thead>';
  function linhas(ag,area){return soAtv(opsOrd(ag)).map(function(o){var a=ag[o],u=F.und[o]||'',ha=u==='HA'&&area,p=ha?a.v/area:null;
    return '<tr><td class="at">'+esc(F.op[o])+'</td><td>'+u+'</td><td><b>'+fmt(a.v)+'</b></td><td>'+(ha?fmt(area):'—')+'</td><td>'+pill(p)+'</td><td>'+Object.keys(a.dias).length+'</td><td>'+dBR(a.ini)+'</td><td>'+dBR(a.fim)+'</td></tr>';}).join('');}
  var h='';
  if(ti<0){var at=0;tals.forEach(function(t){if(F.tal[t][2])at+=F.tal[t][2];});var agF=agreg(tals,ci);
    h+='<h3>Total da fazenda — '+esc(F.faz[fi][2])+' · '+fmt(at)+' ha · '+tals.length+' talhões · '+(cs||'acumulado')+'</h3>'+
      '<div class="fup-wrap"><table>'+cab+'<tbody>'+(linhas(agF,at)||'<tr><td colspan="8">Sem apontamento.</td></tr>')+'</tbody></table></div><h3>Por talhão</h3>';}
  var ai=atvSel();
  var corpo='';tals.forEach(function(t){var T=F.tal[t],ag=agreg([t],ci);
    if(ai>=0&&!ag[ai]){corpo+='<tr><td colspan="8" class="gr">Talhão '+esc(T[1])+' <span>· '+(T[2]!=null?fmt(T[2])+' ha':'sem área cadastrada')+'</span></td></tr><tr><td class="at">'+esc(F.op[ai])+'</td><td colspan="7" style="color:'+VERM+';font-weight:700">Pendente — sem apontamento</td></tr>';return;}
    if(!Object.keys(ag).length)return;
    corpo+='<tr><td colspan="8" class="gr">Talhão '+esc(T[1])+' <span>· '+(T[2]!=null?fmt(T[2])+' ha':'sem área cadastrada')+'</span></td></tr>'+linhas(ag,T[2]);});
  h+='<div class="fup-wrap"><table>'+cab+'<tbody>'+(corpo||'<tr><td colspan="8">Sem apontamento para o filtro.</td></tr>')+'</tbody></table></div>';
  $('fupMain').innerHTML=h;
}
window.fupInit=function(){if(window._fupOk)return;window._fupOk=true;
  $('fupCR').onchange=trocarCR;$('fupFaz').onchange=trocarFaz;$('fupComp').onchange=render;$('fupTal').onchange=render;$('fupAtv').onchange=render;
  ['barras','tabela','concl'].forEach(function(v){$('fupV_'+v).onclick=function(){VIEW=v;render();};});preencher();};
if(document.getElementById('fupRoot').classList.contains('solo')){window.fupInit();return;}
var _sw=window.switchDashTab;
window.switchDashTab=function(id,el){
  var r=$('fupRoot');
  if(id==='fup'){
    ['metaRoot','opacRoot'].forEach(function(x){var e=$(x);if(e)e.style.display='none';});
    var app=document.querySelector('.app');if(app)app.style.display='none';
    var fr=$('frRoot');if(fr){fr.classList.remove('on');document.body.classList.remove('fr-mode');}
    var sb=$('sidebar');if(sb)sb.style.display='none';var so=$('sidebarOverlay');if(so)so.style.display='none';
    var dt=document.querySelector('.dash-tabs');if(dt){dt.style.position='fixed';dt.style.top='0';dt.style.left='0';dt.style.right='0';dt.style.zIndex='10001';dt.style.background='#001450';dt.style.padding='4px 12px';}
    document.querySelectorAll('.dash-tab').forEach(function(d){d.classList.remove('active');});if(el)el.classList.add('active');
    r.style.display='block';window.fupInit();return;
  }
  if(r)r.style.display='none';
  var sb2=$('sidebar');if(sb2)sb2.style.display='';var so2=$('sidebarOverlay');if(so2)so2.style.display='';
  var app2=document.querySelector('.app');if(app2&&id!=='meta'&&id!=='opac')app2.style.display='';
  var dt2=document.querySelector('.dash-tabs');if(dt2&&id!=='meta'&&id!=='opac'){dt2.style.position='';dt2.style.top='';dt2.style.left='';dt2.style.right='';dt2.style.zIndex='';dt2.style.background='';dt2.style.padding='';}
  return _sw(id,el);
};
})();
`;

function blocoRaiz(d, solo, atualizado) {
  return '<style>' + CSS + '</style>\n<div id="fupRoot"' + (solo ? ' class="solo"' : '') + '><h2>&#127793; Avan&ccedil;o F&iacute;sico das Atividades por Talh&atilde;o</h2>' +
    '<div class="fup-sub">Barras = Realizado &divide; &Aacute;rea do talh&atilde;o (atividades em HA) · &uacute;lt. = &uacute;ltimo apontamento · Conclu&iacute;das = entre 98% e 105% da &aacute;rea · &Aacute;reas: CAD_TALHOES (cadastro + CDO&times;BMS)' +
    (atualizado ? ' · Atualizado em ' + atualizado : '') + '</div>' +
    '<div class="fup-ctl"><label>CR<select id="fupCR"></select></label><label>Fazenda<select id="fupFaz"></select></label>' +
    '<label>Talh&atilde;o<select id="fupTal"></select></label><label>Atividade<select id="fupAtv" style="min-width:280px;max-width:420px"></select></label><label>Compet&ecirc;ncia<select id="fupComp"></select></label>' +
    '<div class="fup-seg"><button id="fupV_barras" class="on">&#9776; Barras por talh&atilde;o</button><button id="fupV_tabela">&#9638; Tabela de totais</button><button id="fupV_concl">&#10004; Conclu&iacute;das (98% a 105%)</button></div></div>' +
    '<div id="fupMain"></div>' +
    '<div class="fup-leg" id="fupLeg"><span><i style="background:#27AE60"></i>100% da &aacute;rea</span><span><i style="background:#F5A623"></i>Em andamento</span><span><i style="background:#4F7BC4"></i>Atividade sem % (km, hora, dia)</span></div></div>\n' +
    '<script>window.__FUP__=' + JSON.stringify(d).replace(/<\//g, '<\\/') + ';' + JS + '</script>\n';
}

function injetarFollowup(html, dados, crs) {
  const d = filtrar(dados, crs);
  if (!d.rows.length) return html;
  const tab = '<div class="dash-tab" onclick="switchDashTab(\'fup\',this)">&#127793; Avan&ccedil;o por Talh&atilde;o</div>';
  const i = html.indexOf('class="dash-tabs">');
  if (i < 0) throw new Error('Follow-up: barra de abas (.dash-tabs) não encontrada');
  const re = /<div class="dash-tab"[^>]*>[^<]*<\/div>/g; let m, j = i + 'class="dash-tabs">'.length;
  re.lastIndex = i; while ((m = re.exec(html)) && m.index < i + 4000) j = m.index + m[0].length;
  html = html.slice(0, j) + '\n' + tab + html.slice(j);
  const root = blocoRaiz(d, false, '');
  const k = html.lastIndexOf('</body>');
  return k < 0 ? html + root : html.slice(0, k) + root + html.slice(k);
}

// Página independente (5º link): só a aba Follow-up, todos os CRs.
function paginaFollowup(dados) {
  const agora = new Date(Date.now() - 4 * 3600 * 1000).toISOString().replace('T', ' ').slice(0, 16).split(' ');
  const atual = agora[0].split('-').reverse().join('/') + ' ' + agora[1];
  return '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<title>GN Florestal · Avanço por Talhão</title>' +
    '<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">' +
    '<style>html,body{margin:0;background:#001450;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}</style></head><body>' +
    blocoRaiz(dados, true, atual) + '</body></html>';
}

module.exports = { montarDados, injetarFollowup, paginaFollowup };
