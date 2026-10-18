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
#fupRoot h2{margin:0 0 4px;font-size:20px}
#fupRoot .fup-sub{color:#8AA0C0;font-size:12px;margin-bottom:14px}
#fupRoot .fup-ctl{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px;align-items:flex-end}
#fupRoot .fup-ctl label{font-size:11px;color:#8AA0C0;text-transform:uppercase;letter-spacing:.05em;display:flex;flex-direction:column;gap:4px}
#fupRoot select{background:#12294D;color:#E8EEF8;border:1px solid #2E5FA3;border-radius:6px;padding:7px 10px;font-size:13px;min-width:160px}
#fupRoot .fup-seg{display:flex;border:1px solid #2E5FA3;border-radius:6px;overflow:hidden}
#fupRoot .fup-seg button{background:#12294D;color:#8AA0C0;border:0;padding:8px 14px;font-size:12px;cursor:pointer}
#fupRoot .fup-seg button.on{background:#2E5FA3;color:#fff;font-weight:700}
#fupRoot .fup-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-bottom:16px}
#fupRoot .fup-kpi{background:#12294D;border-radius:8px;padding:11px 15px;border-left:3px solid #2E5FA3}
#fupRoot .fup-kpi b{display:block;font-size:10px;color:#8AA0C0;text-transform:uppercase;letter-spacing:.05em;font-weight:600}
#fupRoot .fup-kpi span{display:block;font-size:20px;font-weight:700;margin-top:4px}
#fupRoot .fup-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}
#fupRoot .fup-card{background:#0D1F55;border:1px solid rgba(46,95,163,.35);border-radius:10px;padding:12px 14px;cursor:pointer;transition:border-color .15s}
#fupRoot .fup-card:hover{border-color:#F5A623}
#fupRoot .fup-card h4{margin:0;font-size:15px;display:flex;justify-content:space-between;align-items:baseline}
#fupRoot .fup-card h4 small{font-size:11px;color:#8AA0C0;font-weight:400}
#fupRoot .fup-bar{margin-top:9px}
#fupRoot .fup-bar .lb{display:flex;justify-content:space-between;gap:8px;font-size:11px;color:#C9D6EA;margin-bottom:3px}
#fupRoot .fup-bar .lb span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#fupRoot .fup-bar .lb b{white-space:nowrap}
#fupRoot .fup-bar .tr{height:10px;border-radius:5px;background:rgba(255,255,255,.08);overflow:hidden}
#fupRoot .fup-bar .tr i{display:block;height:100%;border-radius:5px}
#fupRoot .fup-det{display:grid;grid-template-columns:repeat(auto-fill,minmax(460px,1fr));gap:12px}
#fupRoot .fup-ch{background:#0D1F55;border:1px solid rgba(46,95,163,.35);border-radius:10px;padding:12px 14px}
#fupRoot .fup-ch h4{margin:0 0 2px;font-size:13px;line-height:1.3}
#fupRoot .fup-ch .meta{font-size:11px;color:#8AA0C0;margin-bottom:6px}
#fupRoot .fup-ch .big{font-size:22px;font-weight:700}
#fupRoot .fup-ch svg{width:100%;height:auto;display:block}
#fupRoot .fup-ch svg text{font-family:inherit}
#fupRoot .fup-back{background:#12294D;color:#E8EEF8;border:1px solid #2E5FA3;border-radius:6px;padding:7px 12px;cursor:pointer;font-size:12px}
#fupRoot .fup-wrap{overflow:auto;border-radius:8px;border:1px solid rgba(46,95,163,.35);max-height:calc(100vh - 300px)}
#fupRoot table{border-collapse:separate;border-spacing:0;font-size:12px;min-width:100%}
#fupRoot th{position:sticky;top:0;background:#0A2163;color:#C9D6EA;font-weight:600;padding:8px 10px;text-align:center;z-index:2;border-bottom:1px solid #2E5FA3;vertical-align:bottom}
#fupRoot th.op{min-width:118px;max-width:150px;white-space:normal;line-height:1.25}
#fupRoot th .u{display:block;color:#8AA0C0;font-weight:400;font-size:10px;margin-top:2px}
#fupRoot td{padding:6px 10px;text-align:center;border-bottom:1px solid rgba(46,95,163,.15);white-space:nowrap}
#fupRoot td.tl,#fupRoot th.tl{position:sticky;left:0;background:#0D1F55;z-index:1;text-align:left;font-weight:700}
#fupRoot th.tl{z-index:3;background:#0A2163}
#fupRoot tr.tot td{background:#0A2163;font-weight:700;position:sticky;bottom:0}
#fupRoot td.c .v{display:block;font-weight:600}
#fupRoot td.c .p{display:block;font-size:10px;opacity:.85}
#fupRoot td.ok{background:rgba(39,174,96,.32)}
#fupRoot td.pa{background:rgba(243,156,18,.38)}
#fupRoot td.nh{background:rgba(46,95,163,.18)}
#fupRoot .fup-leg{display:flex;gap:16px;flex-wrap:wrap;font-size:11px;color:#8AA0C0;margin:12px 0 0}
#fupRoot .fup-leg i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-2px}
`;

const JS = `
(function(){
var F=window.__FUP__, VIEW='graf', TAL=-1;
var COR_OK='#27AE60',COR_AND='#F5A623',COR_SEM='#4F7BC4';
function $(id){return document.getElementById(id);}
function fmt(v,d){return Number(v).toLocaleString('pt-BR',{minimumFractionDigits:d==null?2:d,maximumFractionDigits:d==null?2:d});}
function pct(v){return (v*100).toLocaleString('pt-BR',{maximumFractionDigits:0})+'%';}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');}
function curto(s,n){n=n||58;return s.length>n?s.slice(0,n-2)+'…':s;}
function dBR(iso){return iso?iso.slice(8,10)+'/'+iso.slice(5,7):'';}
function dBRc(iso){return iso?iso.split('-').reverse().join('/'):'—';}
var porTal={};F.rows.forEach(function(r){(porTal[r[0]]=porTal[r[0]]||[]).push(r);});
function fazendasDoCR(cr){var o=[];F.faz.forEach(function(f,i){if(F.cr[f[0]]===cr)o.push(i);});return o;}
function temProd(fi){for(var t=0;t<F.tal.length;t++){if(F.tal[t][0]===fi&&porTal[t])return true;}return false;}
function talsDaFaz(fi){var t=[];F.tal.forEach(function(x,i){if(x[0]===fi)t.push(i);});
  t.sort(function(a,b){var x=F.tal[a][1],y=F.tal[b][1],nx=/^\\d+$/.test(x),ny=/^\\d+$/.test(y);if(nx&&ny)return x-y;if(nx)return -1;if(ny)return 1;return x.localeCompare(y);});return t;}
function compSel(){var c=$('fupComp').value;return c?F.comp.indexOf(c):-1;}
function rowsTal(t,ci){return (porTal[t]||[]).filter(function(r){return ci<0||r[2]===ci;});}
function somaOps(t,ci){var o={};rowsTal(t,ci).forEach(function(r){o[r[1]]=(o[r[1]]||0)+r[4];});return o;}
function corPct(p){return p>=0.995?COR_OK:COR_AND;}
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
  var fi=+$('fupFaz').value;var tals=isNaN(fi)?[]:talsDaFaz(fi);
  $('fupTal').innerHTML='<option value="-1">Todos os talhões</option>'+tals.map(function(t){return '<option value="'+t+'">Talhão '+esc(F.tal[t][1])+'</option>';}).join('');
  TAL=-1;render();
}
function k(l,v){return '<div class="fup-kpi"><b>'+l+'</b><span>'+v+'</span></div>';}
function render(){
  var fi=+$('fupFaz').value, ci=compSel();
  TAL=+$('fupTal').value;
  if(isNaN(fi)){$('fupMain').innerHTML='';$('fupKpis').innerHTML='';return;}
  var tals=talsDaFaz(fi);
  var areaTot=0,semArea=0;tals.forEach(function(t){if(F.tal[t][2]!=null)areaTot+=F.tal[t][2];else semArea++;});
  var ops={};tals.forEach(function(t){rowsTal(t,ci).forEach(function(r){ops[r[1]]=1;});});
  var concl=0,anda=0;tals.forEach(function(t){var T=F.tal[t];if(!T[2])return;var s=somaOps(t,ci),mx=0;for(var o in s){if(F.und[o]==='HA'){var p=s[o]/T[2];if(p>mx)mx=p;}}if(mx>=0.995)concl++;else if(mx>0)anda++;});
  $('fupKpis').innerHTML=k('Área cadastrada',fmt(areaTot)+' ha')+k('Talhões',tals.length+(semArea?' <small style="font-size:11px;color:#F5A623">('+semArea+' sem área)</small>':''))+
    k('Atividades',Object.keys(ops).length)+k('Talhões com atividade concluída',concl)+k('Talhões em andamento',anda)+k('Último apontamento',dBRc(F.faz[fi][3]));
  ['graf','tab'].forEach(function(v){$('fupV_'+v).className=VIEW===v?'on':'';});
  $('fupTalBox').style.display=VIEW==='graf'?'':'none';
  if(VIEW==='tab'){tabela(tals,ci);return;}
  if(TAL>=0)detalhe(TAL,ci);else cards(tals,ci);
}
function barra(nome,und,v,area){
  var temP=und==='HA'&&area, p=temP?v/area:null, w=temP?Math.min(p,1)*100:100, cor=temP?corPct(p):COR_SEM;
  return '<div class="fup-bar" title="'+esc(nome)+'"><div class="lb"><span>'+esc(curto(nome,52))+'</span><b>'+(temP?pct(p)+' · ':'')+fmt(v)+' '+und.toLowerCase()+'</b></div>'+
    '<div class="tr"><i style="width:'+w+'%;background:'+cor+(temP?'':';opacity:.55')+'"></i></div></div>';
}
function cards(tals,ci){
  var h='<div class="fup-grid">';
  tals.forEach(function(t){var T=F.tal[t],s=somaOps(t,ci);
    var ol=Object.keys(s).map(Number).sort(function(a,b){return F.op[a].localeCompare(F.op[b]);});
    h+='<div class="fup-card" data-t="'+t+'"><h4>Talhão '+esc(T[1])+'<small>'+(T[2]!=null?fmt(T[2])+' ha':'sem área cadastrada')+' · '+ol.length+' atividade(s)</small></h4>';
    if(!ol.length)h+='<div style="font-size:11px;color:#8AA0C0;margin-top:8px">Sem apontamento no período.</div>';
    ol.forEach(function(o){h+=barra(F.op[o],F.und[o]||'',s[o],T[2]);});
    h+='</div>';});
  $('fupMain').innerHTML=h+'</div>';
  Array.prototype.forEach.call(document.querySelectorAll('#fupRoot .fup-card'),function(c){c.onclick=function(){$('fupTal').value=c.getAttribute('data-t');render();$('fupRoot').scrollTop=0;};});
}
function grafico(serie,und,area){
  // serie: [[iso,valor],...] ordenada; barras = produção do dia, linha = acumulado (% se HA)
  var W=640,H=230,L=46,R=46,T=16,B=34,iw=W-L-R,ih=H-T-B,n=serie.length;
  var mx=Math.max.apply(null,serie.map(function(x){return x[1];}))||1, ac=0, pts=[];
  var temP=und==='HA'&&area, acTot=serie.reduce(function(s,x){return s+x[1];},0);
  var acMax=temP?Math.max(area,acTot):acTot||1;
  var bw=Math.max(2,Math.min(28,iw/n*0.7));
  var svg='<svg viewBox="0 0 '+W+' '+H+'" role="img">';
  for(var g=0;g<=4;g++){var y=T+ih-ih*g/4;svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y+'" y2="'+y+'" stroke="rgba(255,255,255,.08)"/>'+
    '<text x="'+(L-6)+'" y="'+(y+3)+'" fill="#8AA0C0" font-size="10" text-anchor="end">'+fmt(mx*g/4,mx<10?1:0)+'</text>'+
    '<text x="'+(W-R+6)+'" y="'+(y+3)+'" fill="#F5A623" font-size="10">'+(temP?Math.round(acMax/area*100*g/4)+'%':fmt(acMax*g/4,0))+'</text>';}
  if(temP){var y100=T+ih-ih*(area/acMax);svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y100+'" y2="'+y100+'" stroke="#27AE60" stroke-dasharray="4 3"/><text x="'+(L+4)+'" y="'+(y100-4)+'" fill="#27AE60" font-size="10">100% da área ('+fmt(area)+' ha)</text>';}
  var passo=Math.ceil(n/10);
  serie.forEach(function(x,i){var cx=L+iw*(i+0.5)/n,h=ih*x[1]/mx;ac+=x[1];
    svg+='<rect x="'+(cx-bw/2)+'" y="'+(T+ih-h)+'" width="'+bw+'" height="'+h+'" rx="2" fill="#4F7BC4"><title>'+dBRc(x[0])+': '+fmt(x[1])+' '+und.toLowerCase()+' · acumulado '+fmt(ac)+(temP?' ('+pct(ac/area)+')':'')+'</title></rect>';
    pts.push(cx+','+(T+ih-ih*ac/acMax));
    if(i%passo===0||i===n-1)svg+='<text x="'+cx+'" y="'+(H-B+14)+'" fill="#8AA0C0" font-size="10" text-anchor="middle">'+dBR(x[0])+'</text>';});
  svg+='<polyline points="'+pts.join(' ')+'" fill="none" stroke="#F5A623" stroke-width="2.2"/>';
  pts.forEach(function(p){var q=p.split(',');svg+='<circle cx="'+q[0]+'" cy="'+q[1]+'" r="2.6" fill="#F5A623"/>';});
  return svg+'</svg>';
}
function detalhe(t,ci){
  var T=F.tal[t],por={};
  rowsTal(t,ci).forEach(function(r){var o=por[r[1]]=por[r[1]]||{};var d=F.dt[r[3]];o[d]=(o[d]||0)+r[4];});
  var ol=Object.keys(por).map(Number).sort(function(a,b){return F.op[a].localeCompare(F.op[b]);});
  var h='<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px"><button class="fup-back" id="fupVoltar">← Todos os talhões</button>'+
    '<div style="font-size:16px;font-weight:700">Talhão '+esc(T[1])+' <span style="font-size:12px;color:#8AA0C0;font-weight:400">'+(T[2]!=null?fmt(T[2])+' ha':'sem área cadastrada')+' · '+esc(F.faz[T[0]][2])+'</span></div></div>';
  if(!ol.length)h+='<div style="color:#8AA0C0">Sem apontamento no período.</div>';
  h+='<div style="margin-bottom:14px">'+ol.map(function(o){var s=0;for(var d in por[o])s+=por[o][d];return barra(F.op[o],F.und[o]||'',s,T[2]);}).join('')+'</div><div class="fup-det">';
  ol.forEach(function(o){var dias=Object.keys(por[o]).sort(),serie=dias.map(function(d){return [d,por[o][d]];});
    var tot=serie.reduce(function(s,x){return s+x[1];},0),und=F.und[o]||'',temP=und==='HA'&&T[2];
    var rest=temP?Math.max(0,T[2]-tot):0, media=tot/serie.length;
    h+='<div class="fup-ch"><h4>'+esc(F.op[o])+'</h4><div class="meta"><span class="big" style="color:'+(temP?corPct(tot/T[2]):'#E8EEF8')+'">'+(temP?pct(tot/T[2]):fmt(tot)+' '+und.toLowerCase())+'</span> &nbsp; '+
      fmt(tot)+' '+und.toLowerCase()+(temP?' de '+fmt(T[2])+' ha · faltam '+fmt(rest)+' ha':'')+' · '+serie.length+' dia(s) · média '+fmt(media)+'/dia · '+dBRc(dias[0])+' a '+dBRc(dias[dias.length-1])+
      (temP&&rest>0&&media>0?' · previsão: ~'+Math.ceil(rest/media)+' dia(s) de trabalho':'')+'</div>'+grafico(serie,und,temP?T[2]:null)+'</div>';});
  $('fupMain').innerHTML=h+'</div>';
  $('fupVoltar').onclick=function(){$('fupTal').value='-1';render();};
}
function tabela(tals,ci){
  var val={},ops={};
  tals.forEach(function(t){var s=somaOps(t,ci);for(var o in s){val[t+'|'+o]=s[o];ops[o]=1;}});
  var opl=Object.keys(ops).map(Number).sort(function(a,b){return F.op[a].localeCompare(F.op[b]);});
  var areaTot=0;tals.forEach(function(t){if(F.tal[t][2]!=null)areaTot+=F.tal[t][2];});
  var h='<div class="fup-wrap"><table><thead><tr><th class="tl">Talhão</th><th>Área (ha)</th>';
  opl.forEach(function(o){h+='<th class="op" title="'+esc(F.op[o])+'">'+esc(curto(F.op[o]))+'<span class="u">'+(F.und[o]||'')+(F.und[o]==='HA'?' · %':'')+'</span></th>';});
  h+='</tr></thead><tbody>';var tot={};
  tals.forEach(function(t){var T=F.tal[t];h+='<tr><td class="tl">'+esc(T[1])+'</td><td>'+(T[2]!=null?fmt(T[2]):'—')+'</td>';
    opl.forEach(function(o){var v=val[t+'|'+o]||0;tot[o]=(tot[o]||0)+v;if(!v){h+='<td></td>';return;}
      if(F.und[o]==='HA'&&T[2]){var p=v/T[2];h+='<td class="c '+(p>=0.995?'ok':'pa')+'"><span class="v">'+fmt(v)+'</span><span class="p">'+pct(p)+'</span></td>';}
      else h+='<td class="c nh"><span class="v">'+fmt(v)+'</span></td>';});h+='</tr>';});
  h+='<tr class="tot"><td class="tl">TOTAL</td><td>'+fmt(areaTot)+'</td>';
  opl.forEach(function(o){var v=tot[o]||0;h+='<td>'+fmt(v)+(F.und[o]==='HA'&&areaTot?'<span class="p" style="display:block;font-size:10px">'+pct(v/areaTot)+'</span>':'')+'</td>';});
  $('fupMain').innerHTML=h+'</tr></tbody></table></div>';
}
window.fupInit=function(){if(window._fupOk)return;window._fupOk=true;
  $('fupCR').onchange=trocarCR;$('fupFaz').onchange=trocarFaz;$('fupComp').onchange=render;$('fupTal').onchange=render;
  $('fupV_graf').onclick=function(){VIEW='graf';render();};$('fupV_tab').onclick=function(){VIEW='tab';render();};preencher();};
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
  const root = '<style>' + CSS + '</style>\n<div id="fupRoot"><h2>&#127793; Follow-up de Atividades por Talh&atilde;o</h2>' +
    '<div class="fup-sub">Barra = Realizado &divide; &Aacute;rea do talh&atilde;o (atividades em HA) · Clique num talh&atilde;o para ver a evolu&ccedil;&atilde;o di&aacute;ria de cada atividade · &Aacute;reas: CAD_TALHOES (cadastro + CDO&times;BMS)</div>' +
    '<div class="fup-ctl"><label>CR<select id="fupCR"></select></label><label>Fazenda<select id="fupFaz"></select></label>' +
    '<label id="fupTalBox">Talh&atilde;o<select id="fupTal"></select></label><label>Compet&ecirc;ncia<select id="fupComp"></select></label>' +
    '<div class="fup-seg"><button id="fupV_graf" class="on">Gr&aacute;ficos</button><button id="fupV_tab">Tabela</button></div></div>' +
    '<div class="fup-kpis" id="fupKpis"></div><div id="fupMain"></div>' +
    '<div class="fup-leg"><span><i style="background:#27AE60"></i>100% da &aacute;rea</span><span><i style="background:#F5A623"></i>Em andamento</span><span><i style="background:#4F7BC4"></i>Atividade sem % (km, hora, dia) / produ&ccedil;&atilde;o di&aacute;ria</span><span><i style="background:#F5A623;height:3px;vertical-align:3px"></i>Acumulado</span></div></div>\n' +
    '<script>window.__FUP__=' + JSON.stringify(d).replace(/<\//g, '<\\/') + ';' + JS + '</script>\n';
  const k = html.lastIndexOf('</body>');
  return k < 0 ? html + root : html.slice(0, k) + root + html.slice(k);
}

module.exports = { montarDados, injetarFollowup };
