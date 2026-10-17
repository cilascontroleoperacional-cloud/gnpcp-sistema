// Aba "Follow-up por Talhão" dos dashboards GN.
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

  const D = { cr: [], faz: [], tal: [], op: [], und: [], comp: [] }, M = {};
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
    const k = [fk, tal, op, comp].join('§');
    agg.set(k, (agg.get(k) || 0) + p);
    undOp.set(op, txt(r[I.und]).toUpperCase());
    const dt = xlData(r[I.data]); if (dt > (ultData.get(fk) || '')) ultData.set(fk, dt);
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
    const [fk, tal, op, comp] = k.split('§');
    rows.push([talId(fk, tal), id('op', op), id('comp', comp), Math.round(v * 100) / 100]);
  }
  D.und = D.op.map(o => undOp.get(o) || '');
  return { cr: D.cr, op: D.op, und: D.und, comp: D.comp, faz: fazendas, tal: talhoes, rows };
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
#fupRoot h2{margin:0 0 4px;font-size:20px}
#fupRoot .fup-sub{color:#8AA0C0;font-size:12px;margin-bottom:14px}
#fupRoot .fup-ctl{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px}
#fupRoot .fup-ctl label{font-size:11px;color:#8AA0C0;text-transform:uppercase;letter-spacing:.05em;display:flex;flex-direction:column;gap:4px}
#fupRoot select{background:#12294D;color:#E8EEF8;border:1px solid #2E5FA3;border-radius:6px;padding:7px 10px;font-size:13px;min-width:170px}
#fupRoot .fup-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-bottom:16px}
#fupRoot .fup-kpi{background:#12294D;border-radius:8px;padding:11px 15px;border-left:3px solid #2E5FA3}
#fupRoot .fup-kpi b{display:block;font-size:10px;color:#8AA0C0;text-transform:uppercase;letter-spacing:.05em;font-weight:600}
#fupRoot .fup-kpi span{display:block;font-size:20px;font-weight:700;margin-top:4px}
#fupRoot .fup-wrap{overflow:auto;border-radius:8px;border:1px solid rgba(46,95,163,.35);max-height:calc(100vh - 290px)}
#fupRoot table{border-collapse:separate;border-spacing:0;font-size:12px;min-width:100%}
#fupRoot th{position:sticky;top:0;background:#0A2163;color:#C9D6EA;font-weight:600;padding:8px 10px;text-align:center;z-index:2;border-bottom:1px solid #2E5FA3;vertical-align:bottom}
#fupRoot th.op{min-width:118px;max-width:150px;white-space:normal;line-height:1.25}
#fupRoot th .u{display:block;color:#8AA0C0;font-weight:400;font-size:10px;margin-top:2px}
#fupRoot td{padding:6px 10px;text-align:center;border-bottom:1px solid rgba(46,95,163,.15);white-space:nowrap}
#fupRoot td.tl,#fupRoot th.tl{position:sticky;left:0;background:#0D1F55;z-index:1;text-align:left;font-weight:700}
#fupRoot th.tl{z-index:3;background:#0A2163}
#fupRoot td.ar{color:#8AA0C0}
#fupRoot tr.tot td{background:#0A2163;font-weight:700;position:sticky;bottom:0}
#fupRoot td.c{position:relative}
#fupRoot td.c .v{display:block;font-weight:600}
#fupRoot td.c .p{display:block;font-size:10px;opacity:.85}
#fupRoot td.ok{background:rgba(39,174,96,.32)}
#fupRoot td.pa{background:rgba(243,156,18,.38)}
#fupRoot td.nh{background:rgba(46,95,163,.18)}
#fupRoot .fup-leg{display:flex;gap:16px;font-size:11px;color:#8AA0C0;margin:10px 0 0}
#fupRoot .fup-leg i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-2px}
#fupRoot .fup-sec{margin-top:22px}
#fupRoot .fup-sec h3{font-size:14px;margin:0 0 8px;color:#C9D6EA}
#fupRoot .fup-faz td{text-align:left}
#fupRoot .fup-faz tr{cursor:pointer}
#fupRoot .fup-faz tr:hover td{background:rgba(46,95,163,.25)}
#fupRoot .bar{height:6px;border-radius:3px;background:rgba(255,255,255,.1);overflow:hidden;min-width:90px}
#fupRoot .bar i{display:block;height:100%;background:#27AE60}
`;

const JS = `
(function(){
var F=window.__FUP__;
function $(id){return document.getElementById(id);}
function fmt(v,d){return Number(v).toLocaleString('pt-BR',{minimumFractionDigits:d==null?2:d,maximumFractionDigits:d==null?2:d});}
function pct(v){return (v*100).toLocaleString('pt-BR',{maximumFractionDigits:0})+'%';}
function curto(s){return s.length>58?s.slice(0,56)+'…':s;}
var porTal={};F.rows.forEach(function(r){(porTal[r[0]]=porTal[r[0]]||[]).push(r);});
function fazendasDoCR(cr){var o=[];F.faz.forEach(function(f,i){if(F.cr[f[0]]===cr)o.push(i);});return o;}
function temProd(fi){for(var t=0;t<F.tal.length;t++){if(F.tal[t][0]===fi&&porTal[t])return true;}return false;}
function preencher(){
  var crs=[];F.cr.forEach(function(c,i){if(F.faz.some(function(f,fi){return f[0]===i&&temProd(fi);}))crs.push(c);});
  crs.sort();$('fupCR').innerHTML=crs.map(function(c){return '<option>'+c+'</option>';}).join('');
  var comps=F.comp.slice();var MES=['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
  comps.sort(function(a,b){var pa=a.split('-'),pb=b.split('-');return (pb[1]-pa[1])||(MES.indexOf(pb[0])-MES.indexOf(pa[0]));});
  $('fupComp').innerHTML='<option value="">Acumulado (todas)</option>'+comps.map(function(c){return '<option>'+c+'</option>';}).join('');
  trocarCR();
}
function trocarCR(){
  var cr=$('fupCR').value;var lst=fazendasDoCR(cr).filter(temProd);
  lst.sort(function(a,b){return F.faz[a][2].localeCompare(F.faz[b][2]);});
  $('fupFaz').innerHTML=lst.map(function(i){return '<option value="'+i+'">'+F.faz[i][2]+'</option>';}).join('');
  render();
}
function render(){
  var fi=+$('fupFaz').value, comp=$('fupComp').value, ci=comp?F.comp.indexOf(comp):-1;
  if(isNaN(fi)){$('fupTab').innerHTML='';return;}
  var tals=[];F.tal.forEach(function(t,i){if(t[0]===fi)tals.push(i);});
  tals.sort(function(a,b){var x=F.tal[a][1],y=F.tal[b][1],nx=/^\\d+$/.test(x),ny=/^\\d+$/.test(y);
    if(nx&&ny)return x-y;if(nx)return -1;if(ny)return 1;return x.localeCompare(y);});
  var val={},ops={};
  tals.forEach(function(t){(porTal[t]||[]).forEach(function(r){if(ci>=0&&r[2]!==ci)return;var k=t+'|'+r[1];val[k]=(val[k]||0)+r[3];ops[r[1]]=1;});});
  var opl=Object.keys(ops).map(Number).sort(function(a,b){return F.op[a].localeCompare(F.op[b]);});
  var areaTot=0,semArea=0;tals.forEach(function(t){if(F.tal[t][2]!=null)areaTot+=F.tal[t][2];else semArea++;});
  var h='<table><thead><tr><th class="tl">Talhão</th><th>Área (ha)</th>';
  opl.forEach(function(o){h+='<th class="op" title="'+F.op[o].replace(/"/g,'&quot;')+'">'+curto(F.op[o])+'<span class="u">'+(F.und[o]||'')+(F.und[o]==='HA'?' · %':'')+'</span></th>';});
  h+='</tr></thead><tbody>';
  var tot={};
  tals.forEach(function(t){var T=F.tal[t];
    h+='<tr><td class="tl">'+T[1]+'</td><td class="ar">'+(T[2]!=null?fmt(T[2]):'—')+'</td>';
    opl.forEach(function(o){var v=val[t+'|'+o]||0;tot[o]=(tot[o]||0)+v;
      if(!v){h+='<td></td>';return;}
      if(F.und[o]==='HA'&&T[2]){var p=v/T[2];h+='<td class="c '+(p>=0.995?'ok':'pa')+'" title="'+fmt(v)+' de '+fmt(T[2])+' ha"><span class="v">'+fmt(v)+'</span><span class="p">'+pct(p)+'</span></td>';}
      else h+='<td class="c nh"><span class="v">'+fmt(v)+'</span></td>';});
    h+='</tr>';});
  h+='<tr class="tot"><td class="tl">TOTAL</td><td>'+fmt(areaTot)+'</td>';
  opl.forEach(function(o){var v=tot[o]||0;h+='<td>'+fmt(v)+(F.und[o]==='HA'&&areaTot?'<span class="p" style="display:block;font-size:10px">'+pct(v/areaTot)+'</span>':'')+'</td>';});
  h+='</tr></tbody></table>';
  $('fupTab').innerHTML=tals.length?h:'<div style="padding:20px;color:#8AA0C0">Sem talhões para esta fazenda.</div>';
  // KPIs
  var concl=0,anda=0;tals.forEach(function(t){var T=F.tal[t];if(!T[2])return;var mx=0;opl.forEach(function(o){if(F.und[o]==='HA'){var p=(val[t+'|'+o]||0)/T[2];if(p>mx)mx=p;}});if(mx>=0.995)concl++;else if(mx>0)anda++;});
  $('fupKpis').innerHTML=k('Área cadastrada',fmt(areaTot)+' ha')+k('Talhões',tals.length+(semArea?' <small style="font-size:11px;color:#F39C12">('+semArea+' sem área)</small>':''))+
    k('Operações',opl.length)+k('Talhões com operação concluída (100%)',concl)+k('Talhões em andamento',anda)+k('Último apontamento',F.faz[fi][3]?F.faz[fi][3].split('-').reverse().join('/'):'—');
  resumoFazendas(ci);
}
function k(l,v){return '<div class="fup-kpi"><b>'+l+'</b><span>'+v+'</span></div>';}
function resumoFazendas(ci){
  var cr=$('fupCR').value;var lst=fazendasDoCR(cr).filter(temProd);
  var linhas=lst.map(function(fi){var area=0,nt=0,ha=0,ops={};
    F.tal.forEach(function(t,i){if(t[0]!==fi)return;nt++;if(t[2])area+=t[2];(porTal[i]||[]).forEach(function(r){if(ci>=0&&r[2]!==ci)return;ops[r[1]]=1;if(F.und[r[1]]==='HA')ha+=r[3];});});
    return {fi:fi,nome:F.faz[fi][2],area:area,nt:nt,nops:Object.keys(ops).length,ha:ha,ult:F.faz[fi][3]};});
  linhas.sort(function(a,b){return b.ult.localeCompare(a.ult)||a.nome.localeCompare(b.nome);});
  var h='<table class="fup-faz"><thead><tr><th class="tl">Fazenda</th><th>Cód.</th><th>Talhões</th><th>Área (ha)</th><th>Operações</th><th>Produção em HA</th><th>Último apontamento</th></tr></thead><tbody>';
  linhas.forEach(function(l){h+='<tr data-fi="'+l.fi+'"><td class="tl">'+l.nome+'</td><td>'+F.faz[l.fi][1]+'</td><td>'+l.nt+'</td><td>'+(l.area?fmt(l.area):'—')+'</td><td>'+l.nops+'</td><td>'+fmt(l.ha)+'</td><td>'+(l.ult?l.ult.split('-').reverse().join('/'):'—')+'</td></tr>';});
  $('fupFazTab').innerHTML=h+'</tbody></table>';
  Array.prototype.forEach.call(document.querySelectorAll('#fupFazTab tr[data-fi]'),function(tr){tr.onclick=function(){$('fupFaz').value=tr.getAttribute('data-fi');render();$('fupRoot').scrollTop=0;};});
}
window.fupInit=function(){if(window._fupOk)return;window._fupOk=true;
  $('fupCR').onchange=trocarCR;$('fupFaz').onchange=render;$('fupComp').onchange=render;preencher();};
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

function injetarFollowup(html, dados, crs) {
  const d = filtrar(dados, crs);
  if (!d.rows.length) return html;
  const tab = '<div class="dash-tab" onclick="switchDashTab(\'fup\',this)">&#127793; Follow-up por Talh&atilde;o</div>';
  const i = html.indexOf('class="dash-tabs">');
  if (i < 0) throw new Error('Follow-up: barra de abas (.dash-tabs) não encontrada');
  const re = /<div class="dash-tab"[^>]*>[^<]*<\/div>/g; let m, j = i + 'class="dash-tabs">'.length;
  re.lastIndex = i; while ((m = re.exec(html)) && m.index < i + 4000) j = m.index + m[0].length;
  html = html.slice(0, j) + '\n' + tab + html.slice(j);
  const root = '<style>' + CSS + '</style>\n<div id="fupRoot"><h2>&#127793; Follow-up de Opera&ccedil;&otilde;es por Talh&atilde;o</h2>' +
    '<div class="fup-sub">Realizado = Produ&ccedil;&atilde;o apontada (Principal) por talh&atilde;o e opera&ccedil;&atilde;o · % = Realizado &divide; &Aacute;rea do talh&atilde;o (opera&ccedil;&otilde;es em HA) · &Aacute;reas: CAD_TALHOES (cadastro + CDO&times;BMS)</div>' +
    '<div class="fup-ctl"><label>CR<select id="fupCR"></select></label><label>Fazenda<select id="fupFaz"></select></label><label>Compet&ecirc;ncia<select id="fupComp"></select></label></div>' +
    '<div class="fup-kpis" id="fupKpis"></div><div class="fup-wrap" id="fupTab"></div>' +
    '<div class="fup-leg"><span><i style="background:rgba(39,174,96,.6)"></i>100% da &aacute;rea</span><span><i style="background:rgba(243,156,18,.5)"></i>Em andamento</span><span><i style="background:rgba(46,95,163,.5)"></i>Opera&ccedil;&atilde;o sem % (km, hora, dia)</span></div>' +
    '<div class="fup-sec"><h3>Fazendas do CR (clique para abrir)</h3><div class="fup-wrap" id="fupFazTab" style="max-height:none"></div></div></div>\n' +
    '<script>window.__FUP__=' + JSON.stringify(d).replace(/<\//g, '<\\/') + ';' + JS + '</script>\n';
  const k = html.lastIndexOf('</body>');
  return k < 0 ? html + root : html.slice(0, k) + root + html.slice(k);
}

module.exports = { montarDados, injetarFollowup };
