
/* ============================== PCM ============================== */
var PCM_COLS=["dt","ctr","cr","maq","desc","rec","tiporec","op","agr","tal","oper","enc","tpar","par","cls","mapa","h","htrab","hperd","pmec","pope","pdisp","preco","limite","comp2"];
var PCM_ENC=[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0,1];

function xlDate(v){
  if(v==null)return null;
  if(typeof v==='number'){try{return new Date(Math.round((v-25569)*86400000)).toISOString().slice(0,10);}catch(e){return null;}}
  if(v instanceof Date)return v.toISOString().slice(0,10);
  var s=String(v).trim();
  if(/^\d{4}-\d{2}-\d{2}/.test(s))return s.slice(0,10);
  var m=s.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
  return m?(m[3]+'-'+m[2]+'-'+m[1]):null;
}
function cs(v,d){d=(d===undefined)?'N/D':d;return(String(v==null?'':v).trim())||d;}
function tn(v){var n=parseFloat(v);return isNaN(n)?0:n;}

function compress(rows){
  var n=PCM_COLS.length,D=[],M=[],R=[];
  for(var i=0;i<n;i++){D.push([]);M.push({});}
  rows.forEach(function(row){
    R.push(row.map(function(v,j){
      if(PCM_ENC[j]){var k=String(v);if(!(k in M[j])){M[j][k]=D[j].length;D[j].push(v);}return M[j][k];}
      return typeof v==='number'?Math.round(v*1e4)/1e4:v;
    }));
  });
  return {c:PCM_COLS,e:PCM_ENC,d:D,r:R};
}

function processPCM(wb){
  addLog('Lendo aba "CDO de M\u00e1quinas"...');
  var ws=wb.Sheets['CDO de M\u00e1quinas'];
  if(!ws)throw new Error('Aba "CDO de M\u00e1quinas" n\u00e3o encontrada no dados.xlsb');
  var raw=XLSX.utils.sheet_to_json(ws,{header:1,raw:true,defval:null});
  if(raw.length<9)throw new Error('Aba CDO com poucas linhas');
  var hdr=raw[7],col={};
  // Usar PRIMEIRA ocorr\u00eancia de cada coluna (evita col 54 "CR" duplicada sobrescrever col 3)
  for(var i=0;i<hdr.length;i++){if(hdr[i]!=null){var k=String(hdr[i]).trim();if(col[k]==null)col[k]=i;}}
  var obrig=['Data','CR','Cod. Maquina','Horas','Tipo Paraliza\u00e7\u00e3o'];
  for(var oi=0;oi<obrig.length;oi++){if(col[obrig[oi]]==null)throw new Error('Coluna "'+obrig[oi]+'" n\u00e3o encontrada na CDO');}
  var out=[],dtMax=null;
  for(var ri=8;ri<raw.length;ri++){
    var r=raw[ri];
    if(!r||r[col['Data']]==null)continue;
    var crv=String(r[col['CR']]||'').trim();
    if(!/^GN\d{4}$/.test(crv))continue;
    var dt=xlDate(r[col['Data']]);
    if(!dt)continue;
    if(!dtMax||dt>dtMax)dtMax=dt;
    var tp=cs(r[col['Tipo Paraliza\u00e7\u00e3o']]),h=tn(r[col['Horas']]);
    var lim=r[col['Limites de Perdas']];
    if(lim==null||lim===''){lim=-1;}else{var ln=parseFloat(lim);lim=isNaN(ln)?-1:(ln>1?ln/100:ln);}
    out.push([dt,cs(r[col['Contrato']]),crv,cs(r[col['Cod. Maquina']]),cs(r[col['Descricao']]),
      cs(r[col['Recurso']]),cs(r[col['Tipo de Recurso']]),cs(r[col['Operacao']]),
      cs(r[col['Agrupamento de Atividades']]),cs(r[col['Talhao']]),cs(r[col['Operador']]),
      cs(r[col['Encarregado']]),tp,cs(r[col['Paraliza\u00e7\u00e3o']]),cs(r[col['Classificacao_BI']]),
      cs(r[col['Mapa_Perdas']]),h,
      tp==='TRABALHADA'?h:0, tp!=='TRABALHADA'?h:0,
      tp==='Mec\u00e2nicas'?h:0, tp==='Operacionais'?h:0, tp==='\u00c0 disposi\u00e7\u00e3o'?h:0,
      Math.round(tn(r[col['Pre\u00e7o do Recurso']])*1e4)/1e4,
      Math.round(lim*1e6)/1e6, cs(r[col['Compet\u00eancia2']])]);
  }
  if(!out.length)throw new Error('Nenhum registro PCM v\u00e1lido encontrado');
  addLog('  '+out.length+' registros PCM (at\u00e9 '+dtMax+')');
  return {payload:compress(out),count:out.length,dtMax:dtMax};
}

/* ============================== FR4 ============================== */
function processFR4(wb){
  addLog('Lendo aba "REND-Boletim de Produção"...');
  var ws=wb.Sheets['REND-Boletim de Produção'];
  if(!ws)throw new Error('Aba "REND-Boletim de Produção" não encontrada');
  var raw=XLSX.utils.sheet_to_json(ws,{header:1,raw:true,defval:null});
  var hdr=raw[4],col={};
  for(var i=0;i<hdr.length;i++){if(hdr[i]!=null)col[String(hdr[i]).trim()]=i;}
  // Suportar tanto "Competência" (com acento) quanto "Competencia" e "Comp/Semana"
  var colComp = col['Competência']!=null ? col['Competência']
              : col['Competencia']!=null ? col['Competencia']
              : col['Comp/Semana']!=null ? col['Comp/Semana'] : null;
  if(colComp==null)throw new Error('Coluna de Competência não encontrada no Boletim');

  var dim={cr:[],sup:[],enc:[],op:[],tip:[],comp:[],agr:[],cod_op:[]},dm={};
  for(var kk in dim)dm[kk]={};
  function gd(k,v){if(!(v in dm[k])){dm[k][v]=dim[k].length;dim[k].push(v);}return dm[k][v];}
  ['Principal','Apoio','Suporte','N/D'].forEach(function(t){gd('tip',t);});

  var rows=[],dtMin=null,dtMax=null,ranges={};
  for(var ri=5;ri<raw.length;ri++){
    var r=raw[ri];
    if(!r)continue;
    var crv=String(r[col['CR']]||'').trim();
    if(!/^GN\d{4}$/.test(crv))continue;
    var tip=cs(r[col['Tipo Recurso']]);
    if(['Principal','Apoio','Suporte','N/D'].indexOf(tip)<0)tip='N/D';
    var dt=xlDate(r[col['Data']]),cmp=cs(r[colComp]);
    if(dt){
      if(!dtMin||dt<dtMin)dtMin=dt;
      if(!dtMax||dt>dtMax)dtMax=dt;
      if(!ranges[cmp])ranges[cmp]={ini:dt,fim:dt};
      else{if(dt<ranges[cmp].ini)ranges[cmp].ini=dt;if(dt>ranges[cmp].fim)ranges[cmp].fim=dt;}
    }
    var contIdx=col['Contagem de Recurso'];
    rows.push([gd('cr',crv),gd('sup',cs(r[col['Supervisor']])),gd('enc',cs(r[col['Encarregado']])),
      gd('op',cs(r[col['Operacao']])),gd('tip',tip),gd('comp',cmp),dt,
      tn(r[col['Hora Trabalhada']]),tn(r[col['Producao']]),tn(r[col['Rendimento Previsto']]),
      tn(r[col['Preço do Recurso']]),tn(r[col['Valor Total']]),
      gd('agr',cs(r[col['Agrupamentos de Atividades']]||'','')),
      tn(r[col['Total Horas']]),tn(r[col['Escala de Horas']]),tn(r[col['Preço']]),
      contIdx!=null?tn(r[contIdx]):1,gd('cod_op',cs(r[col['Cod. Operacao']]||'',''))]);
  }
  if(!rows.length)throw new Error('Nenhum registro FR4 válido encontrado');
  addLog('  '+rows.length+' apontamentos (até '+dtMax+')');

  // ── FATURAMENTO_COMPILADO ── nova estrutura: múltiplas linhas por CR, uma por competência
  addLog('Lendo aba "FATURAMENTO_COMPILADO"...');
  var wm=wb.Sheets['FATURAMENTO_COMPILADO'];
  if(!wm)throw new Error('Aba "FATURAMENTO_COMPILADO" não encontrada');
  var rm=XLSX.utils.sheet_to_json(wm,{header:1,raw:true,defval:null});
  var hm=rm[4],cm={};
  for(var i2=0;i2<hm.length;i2++){if(hm[i2]!=null)cm[String(hm[i2]).trim()]=i2;}

  // Índices diretos de cada coluna
  var CI={
    GN   : cm['GN'],
    RESP : cm['RESPONSÁVEL']!=null?cm['RESPONSÁVEL']:cm['RESPONSAVEL'],
    CTR  : cm['CONTRATO'],
    FAT  : cm['FAT. TOTAL (R$)'],
    META : cm['META (R$)'],
    PROJ : cm['PROJEÇÃO (R$)'],
    REST : cm['VALOR REST. (R$)'],
    MEDIA: cm['MÉDIA DIÁRIA (R$)'],
    RITMO: cm['% RITMO'],
    MAJST: cm['META AJUST. DIÁRIA (R$)'],
    ESPER: cm['FAT. ESPERADO (R$)'],
    DU   : cm['Dias Úteis']!=null?cm['Dias Úteis']:cm['Dias Uteis'],
    DT   : cm['Dias Trabalhados'],
    DR   : cm['Dias Restantes'],
    COMP : cm['Competencia']!=null?cm['Competencia']:cm['Competência']
  };

  // Ordem de precedência de competência (mais recente primeiro)
  // Rank calculado pelo nome "Mês-AA" (menor = mais recente) — não depende de lista fixa
  var MESES_CR=['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
  function compRank(c){var mm=/^(.+)-(\d{2})$/.exec(String(c||'').trim());if(!mm)return 9999;var i=MESES_CR.indexOf(mm[1]);if(i<0)return 9999;return -((+mm[2])*12+i);}

  // histMeta[CR][comp] = {fat, meta, ritmo, du, dtr, dr}
  var movByCR={}, hist={};
  for(var mi=5;mi<rm.length;mi++){
    var r2=rm[mi]; if(!r2)continue;
    var gn=CI.GN!=null?String(r2[CI.GN]||'').trim():'';
    if(!/^GN\d{4}$/.test(gn))continue;

    var fat2 = CI.FAT!=null  ? tn(r2[CI.FAT])  : 0;
    var meta2= CI.META!=null ? tn(r2[CI.META]) : 0;
    var du2  = CI.DU!=null   ? tn(r2[CI.DU])   : 0;
    var dtr2 = CI.DT!=null   ? tn(r2[CI.DT])   : 0;
    var dr2  = CI.DR!=null   ? tn(r2[CI.DR])   : 0;
    var ctr2 = CI.CTR!=null  ? cs(r2[CI.CTR],'') : '';
    var resp2= CI.RESP!=null ? cs(r2[CI.RESP],'') : '';
    var comp2= CI.COMP!=null ? cs(r2[CI.COMP],'') : '';
    var proj2= CI.PROJ!=null ? tn(r2[CI.PROJ]) : (dtr2>0?fat2/dtr2*du2:0);
    var ritmo2=CI.RITMO!=null?tn(r2[CI.RITMO]):(meta2>0?proj2/meta2:0);
    var majst2=CI.MAJST!=null?tn(r2[CI.MAJST]):0;
    var esper2=CI.ESPER!=null?tn(r2[CI.ESPER]):0;

    // histMeta por CR → competência
    if(!hist[gn])hist[gn]={};
    if(!hist[gn][comp2])hist[gn][comp2]={};
    hist[gn][comp2].fat   = fat2;
    hist[gn][comp2].meta  = meta2;
    hist[gn][comp2].ritmo = ritmo2;
    hist[gn][comp2].du    = du2;
    hist[gn][comp2].dtr   = dtr2;
    hist[gn][comp2].dr    = dr2;
    hist[gn][comp2].majst = majst2;
    hist[gn][comp2].esper = esper2;

    // mov consolidado: usar fat/meta/dias SOMENTE da competência mais recente com meta > 0
    // (antes somava o fat de todas as competências contra a meta da atual -> % realização inflada)
    if(!movByCR[gn]){
      movByCR[gn]={cr:gn,contrato:ctr2,gestor:resp2,
        fat:0,proj:0,meta:0,restante:0,media_dia:0,pct_real:0,pct_ritmo:0,
        meta_ajust:majst2,esperado:esper2,dias_uteis:du2,dias_trab:dtr2,dias_rest:dr2,
        _bestRank:999};
    }
    var rank2=compRank(comp2);
    if(meta2>0 && rank2<movByCR[gn]._bestRank){
      movByCR[gn]._bestRank=rank2;
      movByCR[gn].fat=fat2;
      movByCR[gn].meta=meta2;
      movByCR[gn].dias_uteis=du2;
      movByCR[gn].dias_trab=dtr2;
      movByCR[gn].dias_rest=dr2;
      movByCR[gn].meta_ajust=majst2;
      movByCR[gn].esperado=esper2;
    }
  }

  var mov=[];
  Object.keys(movByCR).forEach(function(gn){
    var m=movByCR[gn];
    var media2=m.dias_trab>0?m.fat/m.dias_trab:0;
    m.proj=media2*m.dias_uteis;
    m.media_dia=media2;
    m.pct_real=m.meta>0?m.fat/m.meta:0;
    m.pct_ritmo=m.meta>0?m.proj/m.meta:0;
    m.restante=Math.max(0,m.meta-m.fat);
    delete m._bestRank;
    mov.push(m);
  });
  if(!mov.length)throw new Error('Nenhum contrato válido no FATURAMENTO_COMPILADO');

  var hcrs=Object.keys(hist);
  var allComps=[]; hcrs.forEach(function(c){Object.keys(hist[c]).forEach(function(k){if(allComps.indexOf(k)<0)allComps.push(k);});});
  addLog('  '+mov.length+' contratos · competências no hist: '+(allComps.join(', ')||'nenhuma'));

  var compAtual=dim.comp.length?dim.comp[dim.comp.length-1]:'N/D';
  var NOMES={"GN1270":"GN1270 — LACAN","GN1400":"GN1400 — ARAUCO",
    "GN1410":"GN1410 — BRACELL MS","GN1420":"GN1420 — INNOVATECH",
    "GN1421":"GN1421 — INNOVATECH/COLPAR","GN1430":"GN1430 — EUCATEX"};

  // Reordenar dim.cr alfabeticamente e reindexar rows[C_CR] para manter consistência
  (function(){
    var sorted = dim.cr.slice().sort(function(a,b){ return String(a).localeCompare(String(b),'pt-BR'); });
    if(sorted.join('|') === dim.cr.join('|')) return; // já está em ordem
    var oldToNew = {};
    dim.cr.forEach(function(cr, i){ oldToNew[i] = sorted.indexOf(cr); });
    dim.cr = sorted;
    rows = rows.map(function(r){ var x=r.slice(); x[0]=oldToNew[r[0]]; return x; });
  })();

  return {
    fr4:{mov:mov,rows:rows,dim:dim,dtMin:dtMin,dtMax:dtMax,competencia:compAtual,
      contrato:"GN MS — COMPILADO",compAtual:compAtual,compRanges:ranges,
      nomeRend:NOMES,nomeEvo:NOMES},
    histMeta:hist,count:rows.length,dtMax:dtMax
  };
}

/* ========================= INJETAR / FILTRAR ========================= */
function inject(html,pcm,fr4,histMeta){
  var TAG_CLOSE='</'+'script>';

  var s1=html.indexOf('<script>window.__DASH_DATA__');
  if(s1<0)throw new Error('Bloco PCM (window.__DASH_DATA__) n\u00e3o encontrado no index.html');
  var e1=html.indexOf(TAG_CLOSE,s1);
  if(e1<0)throw new Error('Fim do bloco PCM n\u00e3o encontrado');
  var nb='<'+'script>window.__DASH_DATA__ = (function(){var P='+JSON.stringify(pcm)+
    ';var D=P.d,E=P.e,n=P.c.length;var rows=new Array(P.r.length);'+
    'for(var i=0;i<P.r.length;i++){var s=P.r[i],o=new Array(n);'+
    'for(var j=0;j<n;j++){o[j]=E[j]?(s[j]>=0?D[j][s[j]]:null):s[j];}rows[i]=o;}'+
    'return {cols:P.c,rows:rows};})()'+TAG_CLOSE;
  var h=html.slice(0,s1)+nb+html.slice(e1+TAG_CLOSE.length);

  var s4=h.indexOf('var FR4 =');
  if(s4<0)throw new Error('Bloco "var FR4 =" n\u00e3o encontrado no index.html');
  var m=h.slice(s4).search(/\nvar C_CR=/);
  if(m<0)throw new Error('Marcador "var C_CR=" n\u00e3o encontrado no index.html');
  h=h.slice(0,s4)+'var FR4 = '+JSON.stringify(fr4)+';'+h.slice(s4+m);

  var histStr=JSON.stringify(histMeta||{});
  if(h.indexOf('var HIST_META')>=0){
    h=h.replace(/var HIST_META\s*=\s*\{[\s\S]*?\};/,'var HIST_META = '+histStr+';');
  }else{
    h=h.replace('\nvar frSel = {};','\nvar HIST_META = '+histStr+';\nvar frSel = {};');
  }

  return h;
}

/* Injetar patch de Paradas (chamado APÓS aplicarExtras1421/removerMetaOpac) */
function injetarPatchParadas(h){
  /* Construir PARADAS_PATCH inline para manter coesão */
  var PARADAS_PATCH = '<'+'style>\n'+
'#paradasDrillModal{display:none;position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.72);align-items:center;justify-content:center;}\n'+
'#paradasDrillModal.open{display:flex;}\n'+
'#paradasDrillBox{background:#0D1B2E;border:1.5px solid #22406E;border-radius:12px;padding:22px 26px;max-width:900px;width:96%;max-height:82vh;overflow-y:auto;position:relative;}\n'+
'#paradasDrillBox h3{font-size:14px;font-weight:700;color:#EAF0FA;margin-bottom:14px;border-bottom:1px solid #22406E;padding-bottom:10px;}\n'+
'#paradasDrillBox .close-btn{position:absolute;top:12px;right:16px;background:none;border:none;color:#8AA0C0;font-size:20px;cursor:pointer;line-height:1;}\n'+
'#paradasDrillBox .close-btn:hover{color:#EAF0FA;}\n'+
'#paradasDrillTable{width:100%;border-collapse:collapse;font-size:12px;}\n'+
'#paradasDrillTable th{background:#12294D;color:#8AA0C0;padding:8px 10px;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #22406E;white-space:nowrap;}\n'+
'#paradasDrillTable td{padding:7px 10px;border-bottom:1px solid rgba(46,95,163,.18);color:#EAF0FA;}\n'+
'#paradasDrillTable tr:hover td{background:rgba(46,95,163,.1);}\n'+
'.tp-label.clickable{cursor:pointer;text-decoration:underline dotted #8AA0C0;transition:color .15s;}\n'+
'.tp-label.clickable:hover{color:#F39C12;}\n'+
'</'+'style>\n'+
'<div id="paradasDrillModal"><div id="paradasDrillBox">'+
'<button class="close-btn" onclick="document.getElementById(\'paradasDrillModal\').classList.remove(\'open\')">&times;<\/button>'+
'<h3 id="paradasDrillTitle">Detalhamento<\/h3>'+
'<table id="paradasDrillTable"><thead><tr>'+
'<th>Data<\/th><th>Máquina<\/th><th>Descrição<\/th><th>Encarregado<\/th><th>Competência<\/th><th style="text-align:right">Horas Perdidas<\/th>'+
'<\/tr><\/thead><tbody id="paradasDrillBody"><\/tbody>'+
'<tfoot><tr style="background:#12294D;font-weight:700"><td colspan="5">TOTAL<\/td><td id="paradasDrillTotal" style="text-align:right;padding:7px 10px"><\/td><\/tr><\/tfoot>'+
'<\/table><\/div><\/div>\n'+
'<'+'script>\n'+
'(function(){\n'+
'function _renderTiposParadasV2(){\n'+
'  var baseSort=(typeof FILTERED!=="undefined"&&FILTERED.length)?FILTERED:FILTERED_ALLMONTHS;\n'+
'  var baseAll=FILTERED_ALLMONTHS;\n'+
'  var pd=computeParadasData(baseAll);\n'+
'  var pdF=computeParadasData(baseSort);\n'+
'  var months=pd.months,monthLabels=pd.monthLabels;\n'+
'  var calPerMonth=pd.calPerMonth,calTotal=Object.values(pd.calPerMonth).reduce(function(a,b){return a+b;},0);\n'+
'  var grandTotal=pd.grandTotal,map=pd.map;\n'+
'  var rows=Object.entries(map).sort(function(a,b){\n'+
'    var ta=(pdF.map[a[0]]||{}).total||0;\n'+
'    var tb=(pdF.map[b[0]]||{}).total||0;\n'+
'    return tb-ta;\n'+
'  });\n'+
'  document.getElementById("paradasTotalTag").textContent="Total: "+num(grandTotal)+"h perdidas";\n'+
'  if(!rows.length){document.getElementById("paradasWrap").innerHTML=\'<p class="cap" style="padding:14px;">Sem horas perdidas no período filtrado.<\/p>\';return;}\n'+
'  var html=\'<table class="paradas-table"><thead><tr><th>Tipos de Paradas<\/th>\';\n'+
'  monthLabels.forEach(function(m){html+=\'<th>\'+m+\'<\/th>\';});\n'+
'  html+=\'<th class="tp-total">Média<\/th><th>Limite de Perda<\/th><\/tr><\/thead><tbody>\';\n'+
'  rows.forEach(function(entry){\n'+
'    var par=entry[0],vals=entry[1];\n'+
'    var limite=vals.limite;\n'+
'    html+=\'<tr><td class="tp-label clickable" data-par="\'+par.replace(/"/g,"&quot;")+\'" title="Clique para ver máquinas e encarregados">\'+par+\'<\/td>\';\n'+
'    months.forEach(function(m){\n'+
'      var v=vals[m]||0,denom=calPerMonth[m]||0,pctv=denom>0?v/denom*100:0;\n'+
'      var over=v>0&&limite!=null&&pctv>limite*100;\n'+
'      html+=\'<td class="\'+( over?"tp-over":"")+\'">\'+( v>0?pctv.toFixed(0)+"%":"—")+\'<\/td>\';\n'+
'    });\n'+
'    var pctTotal=calTotal>0?vals.total/calTotal*100:0;\n'+
'    var overTotal=limite!=null&&pctTotal>limite*100;\n'+
'    html+=\'<td class="tp-total \'+(overTotal?"tp-over-total":"")+\'">\'+pctTotal.toFixed(0)+\'%<\/td>\';\n'+
'    html+=\'<td class="tp-limit">\'+(limite!=null?(limite*100).toFixed(1)+"%":"—")+\'<\/td><\/tr>\';\n'+
'  });\n'+
'  html+=\'<tr class="tp-footer"><td>Total<\/td>\';\n'+
'  months.forEach(function(){html+=\'<td>—<\/td>\';});\n'+
'  html+=\'<td class="tp-total">—<\/td><td><\/td><\/tr><\/tbody><\/table>\';\n'+
'  document.getElementById("paradasWrap").innerHTML=html;\n'+
'  var wrap=document.getElementById("paradasWrap");\n'+
'  if(wrap){wrap.addEventListener("click",function(e){var td=e.target.closest("td.tp-label");if(td&&td.dataset.par)_paradasDrill(td.dataset.par);},{once:false});}\n'+
'}\n'+
'window._paradasDrill=function(par){\n'+
'  var base=(typeof FILTERED!=="undefined"?FILTERED:FILTERED_ALLMONTHS).filter(function(r){\n'+
'    return r[IDX.hperd]>0&&r[IDX.par]===par;\n'+
'  });\n'+
'  /* Uma linha por apontamento (dt+maq+enc), sem agregação */ \n'+
'  var fn=function(v){return Math.round(v*100)/100;};\n'+
'  /* Formatar data ISO -> DD/MM/AAAA */\n'+
'  var fmtDt=function(d){\n'+
'    if(!d)return"—";\n'+
'    var s=String(d);\n'+
'    if(/^\\d{4}-\\d{2}-\\d{2}$/.test(s)){var p=s.split("-");return p[2]+"/"+p[1]+"/"+p[0];}\n'+
'    return s.slice(0,10);\n'+
'  };\n'+
'  /* Ordenar por data desc, depois maq */\n'+
'  var rows=base.slice().sort(function(a,b){\n'+
'    var da=String(a[IDX.dt]||""),db=String(b[IDX.dt]||"");\n'+
'    if(db!==da)return db<da?-1:1;\n'+
'    return String(a[IDX.maq]||"").localeCompare(String(b[IDX.maq]||""));\n'+
'  });\n'+
'  var total=rows.reduce(function(s,r){return s+r[IDX.hperd];},0);\n'+
'  document.getElementById("paradasDrillTitle").textContent="Parada: "+par+" — "+rows.length+" apontamentos";\n'+
'  document.getElementById("paradasDrillBody").innerHTML=rows.map(function(r,i){\n'+
'    var bg=i%2===0?"rgba(18,41,77,.4)":"transparent";\n'+
'    return \'<tr style="background:\'+bg+\'">\'+\n'+
'      \'<td style="white-space:nowrap">\'+fmtDt(r[IDX.dt])+\'<\/td>\'+\n'+
'      \'<td>\'+( r[IDX.maq]||"N/D")+\'<\/td>\'+\n'+
'      \'<td style="color:#8AA0C0;font-size:11px">\'+( r[IDX.desc]||"")+\'<\/td>\'+\n'+
'      \'<td>\'+( r[IDX.enc]||"N/D")+\'<\/td>\'+\n'+
'      \'<td>\'+( r[IDX.comp2]||"N/D")+\'<\/td>\'+\n'+
'      \'<td style="text-align:right;font-weight:700">\'+fn(r[IDX.hperd])+"h<\/td><\/tr>";\n'+
'  }).join("");\n'+
'  document.getElementById("paradasDrillTotal").textContent=fn(total)+"h";\n'+
'  document.getElementById("paradasDrillModal").classList.add("open");\n'+
'};\n'+
'document.getElementById("paradasDrillModal").addEventListener("click",function(e){\n'+
'  if(e.target===this)this.classList.remove("open");\n'+
'});\n'+
'if(typeof renderTiposParadas!=="undefined")renderTiposParadas=_renderTiposParadasV2;\n'+
'window.renderTiposParadas=_renderTiposParadasV2;\n'+
'})();\n'+
'<\/script>\n';
  var CT='</'+'body>';
  var iB=h.lastIndexOf(CT);
  if(iB>=0) h=h.slice(0,iB)+PARADAS_PATCH+CT+h.slice(iB+CT.length);
  return h;
}

function filterPCM(p,crs){
  var C=p.c,E=p.e,D=p.d,R=p.r,n=C.length,ci=C.indexOf('cr');
  var dec=R.map(function(s){return s.map(function(v,j){return (E[j]&&v>=0)?D[j][v]:v;});});
  var flt=dec.filter(function(r){return crs.indexOf(r[ci])>=0;});
  var D2=[],M2=[];
  for(var i=0;i<n;i++){D2.push([]);M2.push({});}
  var R2=flt.map(function(row){
    return row.map(function(v,j){
      if(E[j]){var k=String(v);if(!(k in M2[j])){M2[j][k]=D2[j].length;D2[j].push(v);}return M2[j][k];}
      return typeof v==='number'?Math.round(v*1e4)/1e4:v;
    });
  });
  return {c:C,e:E,d:D2,r:R2};
}

function filterFR4(f0,crs){
  var f=JSON.parse(JSON.stringify(f0)),set={};
  crs.forEach(function(c){set[c]=1;});
  f.mov=f.mov.filter(function(m){return set[m.cr];});
  f.nomeEvo={};f.nomeRend={};
  crs.forEach(function(c){
    if(f0.nomeEvo[c])f.nomeEvo[c]=f0.nomeEvo[c];
    if(f0.nomeRend[c])f.nomeRend[c]=f0.nomeRend[c];
  });
  var o2n={},nc=[];
  f0.dim.cr.forEach(function(cr,i){if(set[cr]){o2n[i]=nc.length;nc.push(cr);}});
  f.dim.cr=nc;
  f.rows=f.rows.filter(function(r){return o2n[r[0]]!=null;})
               .map(function(r){var x=r.slice();x[0]=o2n[r[0]];return x;});
  return f;
}

function filterHist(h,crs){var o={};crs.forEach(function(c){if(h[c])o[c]=h[c];});return o;}

function fixROWS(html,crs){
  var expr=crs.map(function(c){return "cr==='"+c+"'";}).join('||');
  var NEW="let RAW = window.__DASH_DATA__ || {cols:COLS, rows:[]};\n"+
          "let ROWS = RAW.rows.filter(function(r){ var cr=r[COLS.indexOf('cr')]; return "+expr+"; });";
  var OLD="let RAW = window.__DASH_DATA__ || {cols:COLS, rows:[]};\nlet ROWS = RAW.rows.slice();";
  if(html.indexOf(OLD)>=0)return html.replace(OLD,NEW);
  return html.replace(/let RAW = window\.__DASH_DATA__ \|\| \{cols:COLS, rows:\[\]\};\nlet ROWS = RAW\.rows\.filter\(function\(r\)\{[\s\S]*?\}\);/,NEW);
}

function removeFat(html){
  html=html.replace(/[ \t]*<div class="dash-tab" onclick="switchDashTab\('fat',this\)">[\s\S]*?<\/div>\n?/,'');
  var i=html.indexOf('<div id="frRoot"');
  if(i<0)return html;
  var d=0,end=-1,k=i;
  while(k<html.length){
    if(html.slice(k,k+4)==='<div'){d++;k+=4;}
    else if(html.slice(k,k+6)==='</div>'){d--;if(d===0){end=k+6;break;}k+=6;}
    else k++;
  }
  return end>0?html.slice(0,i)+html.slice(end):html;
}


/* ============ ABAS EXTRAS DO CR1421 ============ */
var CR1421_EXTRAS_TPL = "\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\nvar DET_1421 = __DET_JSON__;\nvar META_1421 = __META_JSON__;\nvar OPAC_1421 = __OPAC_JSON__;\n\n/* \u2500\u2500 helpers de formata\u00e7\u00e3o \u2500\u2500 */\nfunction _brl(v){ return v==null?'\\u2014':'R$ '+Number(v).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2}); }\nfunction _num(v){ return v==null?'\\u2014':Number(v).toLocaleString('pt-BR',{maximumFractionDigits:2}); }\nfunction _pctTag(v){\n  var p = Number(v)*100;\n  var col = p>=90?'#27AE60':(p>=70?'#E67E22':'#E74C3C');\n  var fill = Math.min(Math.max(p,0),100);\n  return '<div style=\"display:flex;align-items:center;gap:7px;min-width:120px\">'\n    +'<div style=\"flex:1;height:6px;border-radius:3px;background:rgba(255,255,255,.1);overflow:hidden\">'\n    +'<div style=\"width:'+fill.toFixed(1)+'%;height:100%;border-radius:3px;background:'+col+'\"><\/div><\/div>'\n    +'<span style=\"font-size:11px;font-weight:600;color:'+col+';min-width:34px;text-align:right\">'+p.toFixed(1)+'%<\/span>'\n    +'<\/div>';\n}\nfunction _kpi(lbl,val,col){\n  return '<div style=\"background:#12294D;border-radius:8px;padding:11px 15px;border-left:3px solid '+(col||'#2E5FA3')+'\">'\n    +'<div style=\"font-size:10px;color:#8AA0C0;text-transform:uppercase;letter-spacing:.05em\">'+lbl+'<\/div>'\n    +'<div style=\"font-size:19px;font-weight:700;margin-top:4px\">'+val+'<\/div><\/div>';\n}\n\n/* \u2500\u2500 opacUniq: valores \u00fanicos do OPAC_1421 \u2500\u2500 */\nwindow.opacUniq = function(k){\n  var s={},o=[];\n  OPAC_1421.forEach(function(r){ if(r[k]&&!s[r[k]]){s[r[k]]=1;o.push(r[k]);} });\n  return o.sort();\n};\nwindow.detUniq = function(k){\n  var s={},o=[];\n  DET_1421.forEach(function(r){ if(r[k]&&!s[r[k]]){s[r[k]]=1;o.push(r[k]);} });\n  return o.sort();\n};\n\n/* \u2500\u2500 buildList: para filtros da Meta (chama renderMeta1421) \u2500\u2500 */\nfunction buildList(listId, allId, cntId, vals){\n  var listEl=document.getElementById(listId);\n  var allEl=document.getElementById(allId);\n  var cntEl=document.getElementById(cntId);\n  if(!listEl)return;\n  if(listEl.dataset.populated==='1')return;\n  listEl.dataset.populated='1';\n  listEl.innerHTML=vals.map(function(v){\n    return '<label class=\"f-opt\" data-val=\"'+encodeURIComponent(v)+'\">'\n      +'<input type=\"checkbox\" checked value=\"'+encodeURIComponent(v)+'\">'\n      +'<span class=\"lbl\">'+v+'<\/span><\/label>';\n  }).join('');\n  function upd(){\n    var total=listEl.querySelectorAll('input[type=checkbox]').length;\n    var chk=listEl.querySelectorAll('input:checked').length;\n    if(cntEl)cntEl.textContent=chk+'/'+total;\n    if(allEl){var ai=allEl.querySelector('input');if(ai)ai.checked=(chk===total);}\n  }\n  listEl.querySelectorAll('input').forEach(function(inp){\n    inp.addEventListener('change',function(){upd();renderMeta1421();});\n  });\n  if(allEl){\n    var ai=allEl.querySelector('input');\n    if(ai)ai.addEventListener('change',function(e){\n      listEl.querySelectorAll('input').forEach(function(i){i.checked=e.target.checked;});\n      upd();renderMeta1421();\n    });\n  }\n  upd();\n}\n\n/* \u2500\u2500 buildListOpac: para filtros do OPAC (chama renderOpac) \u2500\u2500 */\nfunction buildListOpac(listId, allId, cntId, vals){\n  var listEl=document.getElementById(listId);\n  var allEl=document.getElementById(allId);\n  var cntEl=document.getElementById(cntId);\n  if(!listEl)return;\n  if(listEl.dataset.populated==='1')return;\n  listEl.dataset.populated='1';\n  listEl.innerHTML=vals.map(function(v){\n    return '<label class=\"f-opt\" data-val=\"'+encodeURIComponent(v)+'\">'\n      +'<input type=\"checkbox\" checked value=\"'+encodeURIComponent(v)+'\">'\n      +'<span class=\"lbl\">'+v+'<\/span><\/label>';\n  }).join('');\n  function upd(){\n    var total=listEl.querySelectorAll('input[type=checkbox]').length;\n    var chk=listEl.querySelectorAll('input:checked').length;\n    if(cntEl)cntEl.textContent=chk+'/'+total;\n    if(allEl){var ai=allEl.querySelector('input');if(ai)ai.checked=(chk===total);}\n  }\n  listEl.querySelectorAll('input').forEach(function(inp){\n    inp.addEventListener('change',function(){upd();renderOpac();});\n  });\n  if(allEl){\n    var ai=allEl.querySelector('input');\n    if(ai)ai.addEventListener('change',function(e){\n      listEl.querySelectorAll('input').forEach(function(i){i.checked=e.target.checked;});\n      upd();renderOpac();\n    });\n  }\n  upd();\n}\n\n/* \u2500\u2500 _metaSel: ler sele\u00e7\u00e3o de uma lista \u2500\u2500 */\nfunction _metaSel(dim){\n  var listId='meta-list-'+dim;\n  var chks=document.querySelectorAll('#'+listId+' input[type=checkbox]:checked');\n  var total=document.querySelectorAll('#'+listId+' input[type=checkbox]');\n  if(!chks.length||chks.length===total.length)return null;\n  var s=new Set();\n  chks.forEach(function(c){s.add(decodeURIComponent(c.value));});\n  return s;\n}\n\n/* \u2500\u2500 renderMeta1421 \u2500\u2500 */\nfunction renderMeta1421(){\n  // Ler sele\u00e7\u00f5es dos checkboxes da sidebar\n  var selComps   = _metaSel('comp');\n  var todasComps = selComps === null;\n  // Sempre modo detalhe \u2014 usa DET_1421 com filtro de comp\n  var modoDetalhe = true;\n\n  // Badges de compet\u00eancia e dias (do meta_base, sempre)\n  var d = META_1421;\n  document.getElementById('metaBadgeComp').textContent = d.comp + ' \\u00b7 ' + d.tipo + ' \\u00b7 ' + d.cr;\n  document.getElementById('metaBadgeDias').textContent =\n    'Dias \\u00fateis: '+Number(d.dias_u).toFixed(2)+\n    ' \\u00b7 Trabalhados: '+Number(d.dias_t).toFixed(2)+\n    ' \\u00b7 Restantes: '+Number(d.dias_r).toFixed(0);\n\n  if(modoDetalhe){\n    // \u2500\u2500 Modo detalhe: agrupar DET_1421 por atividade com filtros \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    var rows = DET_1421.filter(function(r){\n      if(!todasComps && selComps && !selComps.has(r.comp)) return false;\n      return true;\n    });\n    // Agrupa por atividade\n    var ag = {}, ord = [];\n    rows.forEach(function(r){\n      if(!ag[r.op]){ ag[r.op] = {op:r.op, fat_real:0, prod_real:0, fat_prev:r.fat_prev, valor_unit:r.valor_unit}; ord.push(r.op); }\n      ag[r.op].fat_real  += r.fat_real;\n      ag[r.op].prod_real += r.prod_real;\n    });\n    // Calcular ader\u00eancias\n    var tFatReal=0, tFatPrev=0, tProd=0;\n    var _EXCL=['APOIO E MANUTE\u00c7\u00c3O','MANUTE\u00c7\u00c3O DE VIVEIRO','APOIO E MANUTEN\u00c7\u00c3O','MANUTEN\u00c7\u00c3O DE VIVEIRO'];\n    ord=ord.filter(function(op){return _EXCL.indexOf(op)<0;});\n    var atvs = ord.map(function(op){\n      var a = ag[op];\n      // \u00e1rea prevista vem do meta_base\n      var mb = META_1421.rows.find(function(x){ return x.atividade === op; }) || {};\n      a.area_prev  = mb.area_prev  || 0;\n      a.area_real  = a.prod_real;\n      a.fat_prev   = a.fat_prev || mb.fat_prev || 0;\n      a.valor_unit = a.valor_unit || mb.valor_unit || 0;\n      a.ader_prod  = a.area_prev > 0 ? a.area_real / a.area_prev : 0;\n      a.ader_fat   = a.fat_prev  > 0 ? a.fat_real  / a.fat_prev  : 0;\n      a.meta_ajust = mb.meta_ajust || 0;\n      tFatReal += a.fat_real; tFatPrev += a.fat_prev; tProd += a.area_real;\n      return a;\n    });\n\n    // KPIs \u2014 META_1421.total.fat_prev e fat_real s\u00e3o os valores corretos da planilha\n    var kpiFatPrev=(META_1421.total&&META_1421.total.fat_prev)?META_1421.total.fat_prev:tFatPrev;\n    var kpiFatReal=tFatReal;\n    var af=kpiFatPrev>0?kpiFatReal/kpiFatPrev:0;\n    document.getElementById('metaKpis').innerHTML=\n      _kpi('Fat. Previsto',_brl(kpiFatPrev),'#2E5FA3')+\n      _kpi('Fat. Realizado',_brl(kpiFatReal),kpiFatReal>=kpiFatPrev*0.9?'#27AE60':'#E74C3C')+\n      (function(){var dU=Number(META_1421.dias_u||0),dT=Number(META_1421.dias_t||0);var proj2=dT>0?(kpiFatReal/dT)*dU:0;var rt2=kpiFatPrev>0?proj2/kpiFatPrev:0;return _kpi('Ritmo Fat.',(rt2*100).toFixed(1)+'%',rt2>=0.9?'#27AE60':(rt2>=0.7?'#F39C12':'#E74C3C'));})()+\n      _kpi('\\u00c1rea/Prod', _num(tProd)+' ha', '#8E44AD');\n\n    // Thead com colunas de supervisor/encarregado ocultas (agrupado)\n    document.getElementById('metaThead').innerHTML = '<tr style=\"background:#001450;color:#8AA0C0;font-size:11px;font-weight:600\">'\n      +'<th style=\"padding:10px 12px;text-align:left;min-width:250px\">Atividade<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">&Aacute;rea Prev (ha)<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">Valor Unit (R$)<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">Fat. Previsto (R$)<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">&Aacute;rea Real (ha)<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">Fat. Realizado (R$)<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">Ader. Produ&ccedil;&atilde;o<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">Ritmo Fat. (%)<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">Meta Ajustada (ha)<\/th><\/tr>';\n\n    document.getElementById('metaBody').innerHTML = atvs.map(function(a,i){\n      var bg  = i%2===0 ? 'rgba(18,41,77,.4)' : 'transparent';\n      var mc  = a.meta_ajust > 0 ? '#e74c3c' : (a.meta_ajust < 0 ? '#2ecc71' : '#8AA0C0');\n      return '<tr style=\"background:'+bg+';border-bottom:1px solid rgba(46,95,163,.18)\">'\n        +'<td style=\"padding:8px 12px;font-weight:600\">'+a.op+'<\/td>'\n        +'<td style=\"padding:8px 12px;text-align:right\">'+_num(a.area_prev)+'<\/td>'\n        +'<td style=\"padding:8px 12px;text-align:right\">'+_brl(a.valor_unit)+'<\/td>'\n        +'<td style=\"padding:8px 12px;text-align:right\">'+_brl(a.fat_prev)+'<\/td>'\n        +'<td style=\"padding:8px 12px;text-align:right\">'+_num(a.area_real)+'<\/td>'\n        +'<td style=\"padding:8px 12px;text-align:right\">'+_brl(a.fat_real)+'<\/td>'\n        +'<td style=\"padding:8px 12px;text-align:right\">'+_pctTag(a.ader_prod)+'<\/td>'\n        +(function(){\n          var dU=Number(META_1421.dias_u||0), dT=Number(META_1421.dias_t||0);\n          var proj = dT>0 ? (a.fat_real/dT)*dU : 0;\n          var ritmo = a.fat_prev>0 ? proj/a.fat_prev : 0;\n          return '<td style=\"padding:8px 12px;text-align:right\">'+_pctTag(ritmo)+'<\/td>';\n        })()+\n        '<td style=\"padding:8px 12px;text-align:right;color:'+mc+';font-weight:700\">'+_num(a.meta_ajust)+' ha<\/td>'\n        +'<\/tr>';\n    }).join('');\n\n    document.getElementById('metaFoot').innerHTML =\n      '<tr style=\"background:#001450;font-weight:700\"><td style=\"padding:10px 12px\">TOTAL<\/td>'\n      +'<td><\/td><td><\/td>'\n      +'<td style=\"padding:10px 12px;text-align:right\">'+_brl(kpiFatPrev)+'<\/td>'\n      +'<td style=\"padding:10px 12px;text-align:right\">'+_num(tProd)+' ha<\/td>'\n      +'<td style=\"padding:10px 12px;text-align:right\">'+_brl(tFatReal)+'<\/td>'\n      +(function(){\n        var dU=Number(META_1421.dias_u||0), dT=Number(META_1421.dias_t||0);\n        var proj = dT>0 ? (tFatReal/dT)*dU : 0;\n        var ritmoT = kpiFatPrev>0 ? proj/kpiFatPrev : 0;\n        return '<td><\/td><td style=\"padding:10px 12px;text-align:right\">'+_pctTag(ritmoT)+'<\/td><td><\/td><\/tr>';\n      })();\n\n  } else {\n    // \u2500\u2500 Modo resumo: tabela original META_1421 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    var t = d.total || {};\n    var af2 = Number(t.ader_fat||0);\n    document.getElementById('metaKpis').innerHTML =\n      _kpi('Fat. Previsto',  _brl(t.fat_prev), '#2E5FA3')+\n      _kpi('Fat. Realizado', _brl(t.fat_real), af2>=0.9?'#27AE60':'#E74C3C')+\n      _kpi('Ader\\u00eancia Fat.', (af2*100).toFixed(1)+'%', af2>=0.9?'#27AE60':(af2>=0.7?'#F39C12':'#E74C3C'))+\n      _kpi('\\u00c1rea Realizada', _num(t.area_real)+' ha', '#8E44AD');\n\n    document.getElementById('metaThead').innerHTML = '<tr style=\"background:#001450;color:#8AA0C0;font-size:11px;font-weight:600\">'\n      +'<th style=\"padding:10px 12px;text-align:left;min-width:250px\">Atividade<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">&Aacute;rea Prev (ha)<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">Valor Unit (R$)<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">Fat. Previsto (R$)<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">&Aacute;rea Real (ha)<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">Fat. Realizado (R$)<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">Ader. Produ&ccedil;&atilde;o<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">Ritmo Fat. (%)<\/th>'\n      +'<th style=\"padding:10px 12px;text-align:right;white-space:nowrap\">Meta Ajustada (ha)<\/th><\/tr>';\n\n    document.getElementById('metaBody').innerHTML = d.rows.map(function(r,i){\n      var bg = i%2===0 ? 'rgba(18,41,77,.4)' : 'transparent';\n      var mc = r.meta_ajust>0 ? '#e74c3c' : (r.meta_ajust<0 ? '#2ecc71' : '#8AA0C0');\n      return '<tr style=\"background:'+bg+';border-bottom:1px solid rgba(46,95,163,.18)\">'\n        +'<td style=\"padding:8px 12px;font-weight:600\">'+r.atividade+'<\/td>'\n        +'<td style=\"padding:8px 12px;text-align:right\">'+_num(r.area_prev)+'<\/td>'\n        +'<td style=\"padding:8px 12px;text-align:right\">'+_brl(r.valor_unit)+'<\/td>'\n        +'<td style=\"padding:8px 12px;text-align:right\">'+_brl(r.fat_prev)+'<\/td>'\n        +'<td style=\"padding:8px 12px;text-align:right\">'+_num(r.area_real)+'<\/td>'\n        +'<td style=\"padding:8px 12px;text-align:right\">'+_brl(r.fat_real)+'<\/td>'\n        +'<td style=\"padding:8px 12px;text-align:right\">'+_pctTag(r.ader_prod)+'<\/td>'\n        +(function(){\n          var dU=Number(META_1421.dias_u||0), dT=Number(META_1421.dias_t||0);\n          var proj = dT>0 ? (r.fat_real/dT)*dU : 0;\n          var ritmo = r.fat_prev>0 ? proj/r.fat_prev : 0;\n          return '<td style=\"padding:8px 12px;text-align:right\">'+_pctTag(ritmo)+'<\/td>';\n        })()+\n        '<td style=\"padding:8px 12px;text-align:right;color:'+mc+';font-weight:700\">'+_num(r.meta_ajust)+' ha<\/td>'\n        +'<\/tr>';\n    }).join('');\n\n    document.getElementById('metaFoot').innerHTML =\n      '<tr style=\"background:#001450;font-weight:700\"><td style=\"padding:10px 12px\">TOTAL<\/td>'\n      +'<td><\/td><td><\/td>'\n      +'<td style=\"padding:10px 12px;text-align:right\">'+_brl(t.fat_prev)+'<\/td>'\n      +'<td style=\"padding:10px 12px;text-align:right\">'+_num(t.area_real)+' ha<\/td>'\n      +'<td style=\"padding:10px 12px;text-align:right\">'+_brl(t.fat_real)+'<\/td>'\n      +(function(){\n        var dU=Number(META_1421.dias_u||0), dT=Number(META_1421.dias_t||0);\n        var tFR=Number((META_1421.total||{}).fat_real||0), tFP=Number((META_1421.total||{}).fat_prev||0);\n        var proj = dT>0 ? (tFR/dT)*dU : 0;\n        var ritmoT = tFP>0 ? proj/tFP : 0;\n        return '<td><\/td><td style=\"padding:10px 12px;text-align:right\">'+_pctTag(ritmoT)+'<\/td><td><\/td><\/tr>';\n      })();\n  }\n}\n\n/* \u2500\u2500 renderOpac \u2500\u2500 */\nfunction opacInitSelects(){\n  var comps=[], sups=[], ops=[];\n  OPAC_1421.forEach(function(r){\n    if(comps.indexOf(r.comp)<0) comps.push(r.comp);\n    if(sups.indexOf(r.sup)<0) sups.push(r.sup);\n    if(ops.indexOf(r.op)<0) ops.push(r.op);\n  });\n  function fill(id, arr){\n    var sel=document.getElementById(id);\n    if(!sel||sel.options.length>1)return;\n    arr.sort().forEach(function(v){var o=document.createElement('option');o.value=v;o.textContent=v;sel.appendChild(o);});\n  }\n  fill('opac-sel-comp', comps);\n  fill('opac-sel-sup', sups);\n  fill('opac-sel-op', ops);\n}\nfunction opacReset(){\n  ['opac-sel-comp','opac-sel-sup','opac-sel-op'].forEach(function(id){\n    var s=document.getElementById(id);if(s)s.value='';\n  });\n  renderOpac();\n}\nfunction renderOpac(){\n  opacInitSelects();\n  var fComp=document.getElementById('opac-sel-comp');\n  var fSup=document.getElementById('opac-sel-sup');\n  var fOp=document.getElementById('opac-sel-op');\n  var vComp=fComp?fComp.value:'',vSup=fSup?fSup.value:'',vOp=fOp?fOp.value:'';\n  var selP=_metaSel('proj');\n  var d = OPAC_1421.filter(function(r){\n    if(vComp && r.comp!==vComp) return false;\n    if(vSup  && r.sup!==vSup)  return false;\n    if(vOp   && r.op!==vOp)   return false;\n    if(selP  && !selP.has(r.proj)) return false;\n    return true;\n  });\n\n  // Agregar por comp+op \u2014 evita duplicatas quando m\u00faltiplos supervisores marcados\n  var mapAgg={};\n  d.forEach(function(r){\n    var key=r.comp+'||'+r.op;\n    if(!mapAgg[key]){\n      mapAgg[key]={comp:r.comp,op:r.op,proj:r.proj,\n        prod:0,h_trab:0,h_imp:0,h_tot:0,vl_tot:0,\n        rend_prev:r.rend_prev,preco:r.preco};\n    }\n    var a=mapAgg[key];\n    a.prod   +=r.prod   ||0;\n    a.h_trab +=r.h_trab ||0;\n    a.h_imp  +=r.h_imp  ||0;\n    a.h_tot  +=r.h_tot  ||0;\n    a.vl_tot +=r.vl_tot ||0;\n  });\n  var agg=Object.values(mapAgg);\n  agg.forEach(function(a){\n    a.rend_ef=a.h_trab>0?Math.round(a.prod/a.h_trab*10000)/10000:0;\n  });\n\n  var sum=function(k){ return agg.reduce(function(a,r){ return a+(r[k]||0); },0); };\n  var tProd=sum('prod'), tHt=sum('h_trab'), tVl=sum('vl_tot');\n\n  document.getElementById('opacKpis').innerHTML =\n    _kpi('Produ\u00e7\u00e3o', _num(tProd), '#2E5FA3')+\n    _kpi('Horas Trabalhadas', _num(tHt)+'h', '#27AE60')+\n    _kpi('Valor Total', _brl(tVl), '#F39C12')+\n    _kpi('Fazendas', new Set(agg.map(function(x){return x.proj;})).size, '#27AE60')+\n    _kpi('Linhas', agg.length, '#8E44AD');\n\n  var tb=document.getElementById('opacBody');\n  if(!agg.length){\n    tb.innerHTML='<tr><td colspan=\"10\" style=\"text-align:center;padding:22px;color:#8AA0C0\">Nenhum registro para os filtros selecionados.<\/td><\/tr>';\n    document.getElementById('opacFoot').innerHTML=''; return;\n  }\n\n  tb.innerHTML = agg.map(function(r,i){\n    var bg=i%2===0?'rgba(18,41,77,.4)':'transparent';\n    return '<tr style=\"background:'+bg+';border-bottom:1px solid rgba(46,95,163,.15)\">'\n      +'<td style=\"padding:8px 12px;font-weight:600\">'+r.op+'<\/td>'\n      +'<td style=\"padding:8px 12px\">'+r.comp+'<\/td>'\n      +'<td style=\"padding:8px 12px;text-align:right\">'+_num(r.prod)+'<\/td>'\n      +'<td style=\"padding:8px 12px;text-align:right\">'+_num(r.h_trab)+'<\/td>'\n      +'<td style=\"padding:8px 12px;text-align:right\">'+_num(r.h_imp)+'<\/td>'\n      +'<td style=\"padding:8px 12px;text-align:right\">'+_num(r.h_tot)+'<\/td>'\n      +'<td style=\"padding:8px 12px;text-align:right\">'+_num(r.rend_prev)+'<\/td>'\n      +'<td style=\"padding:8px 12px;text-align:right\">'+_num(r.rend_ef)+'<\/td>'\n      +'<td style=\"padding:8px 12px;text-align:right\">'+_brl(r.preco)+'<\/td>'\n      +'<td style=\"padding:8px 12px;text-align:right\">'+_brl(r.vl_tot)+'<\/td>'\n      +'<\/tr>';\n  }).join('');\n\n  document.getElementById('opacFoot').innerHTML =\n    '<tr style=\"background:#001450;font-weight:700\"><td style=\"padding:10px 12px\">TOTAL<\/td><td><\/td>'\n    +'<td style=\"padding:10px 12px;text-align:right\">'+_num(tProd)+'<\/td>'\n    +'<td style=\"padding:10px 12px;text-align:right\">'+_num(tHt)+'<\/td>'\n    +'<td style=\"padding:10px 12px;text-align:right\">'+_num(sum('h_imp'))+'<\/td>'\n    +'<td style=\"padding:10px 12px;text-align:right\">'+_num(sum('h_tot'))+'<\/td>'\n    +'<td><\/td><td><\/td><td><\/td>'\n    +'<td style=\"padding:10px 12px;text-align:right\">'+_brl(tVl)+'<\/td><\/tr>';\n}\n\nfunction limparMetaFiltros(){\n  // Marcar todos os checkboxes sem recriar as listas\n  document.querySelectorAll('#meta-filters-section input[type=checkbox]').forEach(function(c){c.checked=true;});\n  // Atualizar contadores\n  ['comp','sup','enc','proj','op'].forEach(function(dim){\n    var listEl=document.getElementById('meta-list-'+dim);\n    var cntEl =document.getElementById('meta-cnt-'+dim);\n    var allEl =document.getElementById('meta-all-'+dim);\n    if(!listEl)return;\n    var total=listEl.querySelectorAll('input[type=checkbox]').length;\n    if(cntEl)cntEl.textContent=total+'/'+total;\n    if(allEl){var ai=allEl.querySelector('input');if(ai)ai.checked=true;}\n  });\n  renderOpac();renderMeta1421();\n}\n\nfunction limparOpac(){ limparMetaFiltros(); }\n\nfunction _initMetaCheckboxes(){\n  if(window._metaFiltersReady)return;\n  window._metaFiltersReady=true;\n  function uniq(k){var s={},o=[];DET_1421.forEach(function(r){if(r[k]&&!s[r[k]]){s[r[k]]=1;o.push(r[k]);}});return o.sort();}\n  // Todos os filtros usam OPAC (dados de todas as compet\u00eancias)\n  buildListOpac('meta-list-comp','meta-all-comp','meta-cnt-comp',window.opacUniq('comp'));\n  buildListOpac('meta-list-sup', 'meta-all-sup', 'meta-cnt-sup', window.opacUniq('sup'));\n  buildListOpac('meta-list-enc', 'meta-all-enc', 'meta-cnt-enc', window.detUniq('enc'));\n  buildListOpac('meta-list-proj','meta-all-proj','meta-cnt-proj',window.opacUniq('proj'));\n  buildListOpac('meta-list-op',  'meta-all-op',  'meta-cnt-op',  window.opacUniq('op'));\n}\n\n/* \u2500\u2500 override do switchDashTab \u2500\u2500 */\nvar _swOrig = window.switchDashTab;\nwindow.switchDashTab = function(id, el){\n  var mR=document.getElementById('metaRoot');\n  var oR=document.getElementById('opacRoot');\n  var app=document.querySelector('.app');\n  var fr=document.getElementById('frRoot');\n  var sb=document.getElementById('sidebar');\n  var so=document.getElementById('sidebarOverlay');\n  var dt=document.querySelector('.dash-tabs');\n  var mfs=document.getElementById('meta-filters-section');\n\n  if(mR)mR.style.display='none';\n  if(oR)oR.style.display='none';\n\n  if(id==='meta'||id==='opac'){\n    if(app)app.style.display='none';\n    // Meta: esconder sidebar (tela cheia). OPAC: manter sidebar com filtros\n    if(id==='meta'){\n      if(sb)sb.style.display='none';\n      if(so)so.style.display='none';\n    }\n    if(fr){fr.classList.remove('on');document.body.classList.remove('fr-mode');}\n    // Esconder filtros PCM, mostrar filtros meta\n    document.querySelectorAll('#sidebarBody > .f-sec, #sidebarBody > .f-dm-toggle, #sidebarBody > .sidebar-clear, .sidebar-clear').forEach(function(e){if(!e.closest('#meta-filters-section'))e.style.display='none';});\n    if(mfs)mfs.style.display='block';\n    // Se\u00e7\u00f5es contextuais\n    var secComp=document.querySelector('[data-sec=\"meta-comp\"]');\n    var secEnc =document.querySelector('[data-sec=\"meta-enc\"]');\n    var secProj=document.querySelector('[data-sec=\"meta-proj\"]');\n    var secOp  =document.querySelector('[data-sec=\"meta-op\"]');\n    if(id==='meta'){\n      if(secComp)secComp.style.display='';\n      if(secEnc) secEnc.style.display='none';   // sem encarregado na aba Meta\n      var secSup=document.querySelector('[data-sec=\"meta-sup\"]');\n      if(secSup) secSup.style.display='none';   // sem supervisor na aba Meta\n      if(secProj)secProj.style.display='none';\n      if(secOp)  secOp.style.display='none';\n      // Aba Meta: manter todas as compet\u00eancias marcadas (sem filtro for\u00e7ado)\n    }else{\n      if(secComp)secComp.style.display='';\n      if(secEnc) secEnc.style.display='none';\n      var secSup2=document.querySelector('[data-sec=\"meta-sup\"]');\n      if(secSup2)secSup2.style.display='';     // supervisor volta no opac\n      if(secProj)secProj.style.display='';\n      if(secOp)  secOp.style.display='';\n      // Aba Opac: resetar e marcar todas as compet\u00eancias\n      (function(){\n        var list=document.getElementById('meta-list-comp');\n        if(!list)return;\n        // Resetar flag para repopular com todos valores do OPAC\n        list.dataset.populated='';\n        buildListOpac('meta-list-comp','meta-all-comp','meta-cnt-comp',window.opacUniq('comp'));\n        // Garantir todas marcadas\n        list.querySelectorAll('input[type=checkbox]').forEach(function(c){c.checked=true;});\n        var total=list.querySelectorAll('input[type=checkbox]').length;\n        var cnt=document.getElementById('meta-cnt-comp');\n        if(cnt)cnt.textContent=total+'/'+total;\n        var all=document.getElementById('meta-all-comp');\n        if(all){var ai=all.querySelector('input');if(ai)ai.checked=true;}\n      })();\n    }\n    if(dt){dt.style.position='fixed';dt.style.top='0';dt.style.left='0';dt.style.right='0';dt.style.zIndex='10001';dt.style.background='#001450';dt.style.padding='4px 12px';}\n    document.querySelectorAll('.dash-tab').forEach(function(d){d.classList.remove('active');});\n    if(el)el.classList.add('active');\n    if(id==='meta'){mR.style.display='block';renderMeta1421();}\n    else{oR.style.display='block';renderOpac();}\n  }else{\n    document.querySelectorAll('#sidebarBody > .f-sec, #sidebarBody > .f-dm-toggle, #sidebarBody > .sidebar-clear, .sidebar-clear').forEach(function(e){if(!e.closest('#meta-filters-section'))e.style.display='';});\n    if(mfs)mfs.style.display='none';\n    if(sb)sb.style.display='';\n    if(so)so.style.display='';\n    if(app)app.style.display='';\n    if(dt){dt.style.position='';dt.style.top='';dt.style.left='';dt.style.right='';dt.style.zIndex='';dt.style.background='';}\n    _swOrig(id,el);\n  }\n};\n\n_initMetaCheckboxes();\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n/* \u2500\u2500 Auto-fit zoom \u2500\u2500 */\n(function(){\n  var BASE_W = 1440;   // largura de design base em px\n  var MIN_Z  = 0.6;    // zoom m\u00ednimo (60%)\n  var MAX_Z  = 1.25;   // zoom m\u00e1ximo (125%)\n\n  function applyZoom(){\n    var w = window.innerWidth;\n    // S\u00f3 aplicar quando a aba Meta ou OPAC estiver ativa\n    // (o layout PCM j\u00e1 tem seu pr\u00f3prio responsive)\n    var ratio = w / BASE_W;\n    ratio = Math.min(MAX_Z, Math.max(MIN_Z, ratio));\n\n    // Aplicar apenas nos roots de Meta e OPAC para n\u00e3o quebrar PCM\n    ['metaRoot','opacRoot'].forEach(function(id){\n      var el = document.getElementById(id);\n      if(!el) return;\n      // Ajustar font-size e escalar a tabela interna\n      // Usar CSS custom property para escala\n      el.style.fontSize = Math.round(14 * ratio) + 'px';\n    });\n  }\n\n  // Rodar ao carregar e ao redimensionar\n  if(document.readyState === 'loading'){\n    document.addEventListener('DOMContentLoaded', applyZoom);\n  } else {\n    applyZoom();\n  }\n  var resizeTimer;\n  window.addEventListener('resize', function(){\n    clearTimeout(resizeTimer);\n    resizeTimer = setTimeout(applyZoom, 150);\n  });\n})();\n\n\n\n\n\n";











function readCR1421Extras(wb){
  function num(v){var n=parseFloat(v);return isNaN(n)?0:n;}
  function txt(v){return (v==null?'':String(v)).trim();}
  function grid(ws){
    var rng=XLSX.utils.decode_range(ws['!ref']);
    rng.s.c=0; rng.s.r=0;
    return XLSX.utils.sheet_to_json(ws,{header:1,raw:true,defval:null,range:rng});
  }

  var meta=null, opac=[], det=[];

  // ── META X REALIZADO_CR1421 ──────────────────────────────────────────────
  var wm=wb.Sheets['META X REALIZADO_CR1421'];
  if(wm){
    var rm=grid(wm);
    meta={comp:txt(rm[1]&&rm[1][6]),tipo:txt(rm[1]&&rm[1][7]),cr:txt(rm[1]&&rm[1][8]),
          dias_u:num(rm[0]&&rm[0][14]),dias_t:num(rm[1]&&rm[1][14]),dias_r:num(rm[2]&&rm[2][14]),
          rows:[],total:{}};
    for(var i=3;i<rm.length;i++){
      var r=rm[i]; if(!r||!txt(r[1]))continue;
      meta.rows.push({atividade:txt(r[1]),area_prev:num(r[2]),valor_unit:num(r[3]),
        fat_prev:num(r[4]),area_real:num(r[5]),fat_real:num(r[6]),
        ader_prod:num(r[7]),ader_fat:num(r[8]),meta_ajust:num(r[9])});
    }
    // Linha de total: última linha com fat_prev preenchido e atividade vazia
    for(var k=rm.length-1;k>=3;k--){
      var t=rm[k];
      if(t&&!txt(t[1])&&t[4]!=null&&t[4]!==''){
        meta.total={fat_prev:num(t[4]),area_real:num(t[5]),fat_real:num(t[6]),ader_fat:num(t[7])};
        break;
      }
    }
  }

  // ── OPERAÇÕES ACUMULADAS CR1421 → opac[] ─────────────────────────────────
  // Nova aba dedicada com preço, rend efetivo, resultado já calculados
  var woA=wb.Sheets['OPERAÇÕES ACUMULADAS CR1421'];
  if(woA){
    var roA=grid(woA), hA={};
    (roA[2]||[]).forEach(function(hv,hi){if(hv!=null)hA[txt(hv)]=hi;});
    // Mapeamento de colunas: Competência=0, Data=1, Supervisor=2, CR=3, Operacao=4
    // Projeto=5, Talhao=6, Contagem=7, Producao=8, HoraTrab=9, HoraImp=10,
    // TotalHoras=11, RendPrev=12, RendEf=13, RendTot=14, Preco=15, ValorTotal=16, ResNeg=17
    var iComp=hA['Competência']!=null?hA['Competência']:(hA['Competencia']!=null?hA['Competencia']:0);
    var iSup =hA['Supervisor']!=null?hA['Supervisor']:2;
    var iOp  =hA['Operacao']!=null?hA['Operacao']:4;
    var iProj=hA['Projeto']!=null?hA['Projeto']:5;
    var iCont=hA['Soma de Contagem de Recurso']!=null?hA['Soma de Contagem de Recurso']:7;
    var iProd=hA['Soma de Producao']!=null?hA['Soma de Producao']:8;
    var iHt  =hA['Soma de Hora Trabalhada']!=null?hA['Soma de Hora Trabalhada']:9;
    var iHi  =hA['Soma de Hora Improdutiva']!=null?hA['Soma de Hora Improdutiva']:10;
    var iTot =hA['Soma de Total Horas']!=null?hA['Soma de Total Horas']:11;
    var iRp  =hA[' Rend. Previsto']!=null?hA[' Rend. Previsto']:12;
    var iRef =hA[' Rend. Efetivo']!=null?hA[' Rend. Efetivo']:13;
    var iPreco=hA[' Preço']!=null?hA[' Preço']:15;
    var iVT  =hA['Soma de Valor Total']!=null?hA['Soma de Valor Total']:16;

    var EXCL=['APOIO E MANUTEÇÃO','APOIO E MANUTENÇÃO','MANUTEÇÃO DE VIVEIRO','MANUTENÇÃO DE VIVEIRO'];
    var accA={};
    for(var ai=3;ai<roA.length;ai++){
      var rA=roA[ai]; if(!rA)continue;
      var compA=txt(rA[iComp]); if(!compA||compA==='Total Geral')continue;
      var opA=txt(rA[iOp]); if(!opA||EXCL.indexOf(opA)>=0)continue;
      var supA=txt(rA[iSup]);
      var projA=txt(rA[iProj]);
      var kA=compA+'\x01'+supA+'\x01'+opA+'\x01'+projA;
      if(!accA[kA])accA[kA]={comp:compA,sup:supA,op:opA,proj:projA,
        cont:0,prod:0,h_trab:0,h_imp:0,h_tot:0,vl_tot:0,preco:0,rend_prev:0,rend_ef:0};
      var aA=accA[kA];
      aA.cont   +=num(rA[iCont]);
      aA.prod   +=num(rA[iProd]);
      aA.h_trab +=num(rA[iHt]);
      aA.h_imp  +=num(rA[iHi]);
      aA.h_tot  +=num(rA[iTot]);
      aA.vl_tot +=num(rA[iVT]);
      if(num(rA[iPreco])>0) aA.preco   =num(rA[iPreco]);
      if(num(rA[iRp])>0)    aA.rend_prev=num(rA[iRp]);
      if(num(rA[iRef])>0)   aA.rend_ef  =num(rA[iRef]);
    }
    Object.keys(accA).sort().forEach(function(kA){
      var v=accA[kA];
      ['cont','prod','h_trab','h_imp','h_tot','vl_tot','preco','rend_prev','rend_ef']
        .forEach(function(f){v[f]=Math.round(v[f]*1e4)/1e4;});
      if(v.prod>0||v.vl_tot>0) opac.push(v);
    });
    addLog('  Operações Acumuladas (nova aba): '+opac.length+' linhas');
  } else {
    // fallback: ler do Boletim se a aba não existir (todos os CRs, não só GN1421)
    var wbpO=wb.Sheets['REND-Boletim de Produção'];
    if(wbpO){
      var roO=grid(wbpO), hO={};
      (roO[4]||[]).forEach(function(hv,hi){if(hv!=null)hO[txt(hv)]=hi;});
      var EXCL2=['APOIO E MANUTEÇÃO','APOIO E MANUTENÇÃO','MANUTEÇÃO DE VIVEIRO','MANUTENÇÃO DE VIVEIRO'];
      var accO={};
      var iCompO=hO['Competência']!=null?hO['Competência']:(hO['Competencia']!=null?hO['Competencia']:hO['Comp/Semana']);
      for(var oi=5;oi<roO.length;oi++){
        var rO=roO[oi]; if(!rO)continue;
        var crO=txt(rO[hO['CR']]); if(!/^GN\d{4}$/.test(crO))continue;
        if(txt(rO[hO['Tipo Recurso']])!=='Principal')continue;
        var opO=txt(rO[hO['Operacao']]); if(EXCL2.indexOf(opO)>=0)continue;
        var cO=txt(rO[iCompO]),sO=txt(rO[hO['Supervisor']]),pO=txt(rO[hO['Projeto']||5]);
        var kO=cO+'\x01'+sO+'\x01'+opO+'\x01'+pO;
        if(!accO[kO])accO[kO]={comp:cO,sup:sO,op:opO,proj:pO,cont:0,prod:0,h_trab:0,h_imp:0,h_tot:0,vl_tot:0,preco:0,rend_prev:0,rend_ef:0};
        var aO=accO[kO];
        aO.cont  +=hO['Contagem de Recurso']!=null?num(rO[hO['Contagem de Recurso']]):1;
        aO.prod  +=num(rO[hO['Producao']]);
        aO.h_trab+=num(rO[hO['Hora Trabalhada']]);
        aO.h_tot +=num(rO[hO['Total Horas']]);
        aO.vl_tot+=num(rO[hO['Valor Total']]);
        if(num(rO[hO['Preço']]))aO.preco=num(rO[hO['Preço']]);
        if(num(rO[hO['Rendimento Previsto']]))aO.rend_prev=num(rO[hO['Rendimento Previsto']]);
      }
      Object.keys(accO).sort().forEach(function(kO){
        var v=accO[kO];
        v.h_imp=Math.round((v.h_tot-v.h_trab)*1e4)/1e4;
        v.rend_ef=v.h_trab>0?Math.round(v.prod/v.h_trab*1e4)/1e4:0;
        if(v.vl_tot>0) opac.push(v);
      });
      addLog('  Operações Acumuladas (Boletim): '+opac.length+' linhas');
    }
  }

  // ── DETALHE por comp/sup/enc/op para aba Meta (do Boletim) ───────────────
  var wbp=wb.Sheets['REND-Boletim de Produção'];
  if(wbp){
    var rbp=grid(wbp), hbp={};
    (rbp[4]||[]).forEach(function(hv,hi){if(hv!=null)hbp[txt(hv)]=hi;});
    var iCompB=hbp['Competência']!=null?hbp['Competência']:(hbp['Competencia']!=null?hbp['Competencia']:hbp['Comp/Semana']);
    var EXCL3=['APOIO E MANUTEÇÃO','APOIO E MANUTENÇÃO','MANUTEÇÃO DE VIVEIRO','MANUTENÇÃO DE VIVEIRO'];
    var metaMapD={};
    if(meta) meta.rows.forEach(function(mr){metaMapD[mr.atividade]=mr;});
    var accD={};
    for(var bpi=5;bpi<rbp.length;bpi++){
      var rb=rbp[bpi]; if(!rb)continue;
      if(txt(rb[hbp['CR']||0])!=='GN1421')continue;
      if(txt(rb[hbp['Tipo Recurso']])!=='Principal')continue;
      var opD=txt(rb[hbp['Operacao']]); if(EXCL3.indexOf(opD)>=0)continue;
      var cmpD=txt(rb[iCompB]);
      var supD=txt(rb[hbp['Supervisor']]);
      var encD=txt(rb[hbp['Encarregado']]);
      var kD=cmpD+'\x01'+supD+'\x01'+encD+'\x01'+opD;
      if(!accD[kD])accD[kD]={comp:cmpD,sup:supD,enc:encD,op:opD,fat:0,prod:0};
      accD[kD].fat +=num(rb[hbp['Valor Total']]);
      accD[kD].prod+=num(rb[hbp['Producao']]);
    }
    Object.keys(accD).sort().forEach(function(kD){
      var a=accD[kD],mb=metaMapD[a.op]||{};
      var fp=mb.fat_prev||0,ap=mb.area_prev||0;
      det.push({comp:a.comp,sup:a.sup,enc:a.enc,op:a.op,
        prod_real:Math.round(a.prod*1e4)/1e4,
        fat_real: Math.round(a.fat*100)/100,
        fat_prev: Math.round(fp*100)/100,
        valor_unit:Math.round((mb.valor_unit||0)*100)/100,
        ader_prod:ap>0?Math.round(a.prod/ap*1e4)/1e4:0,
        ader_fat: fp>0?Math.round(a.fat/fp*1e4)/1e4:0});
    });
    addLog('  Detalhe Meta: '+det.length+' linhas ('+[...new Set(det.map(function(r){return r.comp;}))].join(', ')+')');
  }
  return {meta:meta,opac:opac,det:det};
}

function removerMetaOpac(html){
  // Função auxiliar: remove <div id="ID"...> ... </div> contando profundidade de tags <div>
  // Funciona apenas se o div tem fechamento estático no HTML
  function removerDivById(h, id) {
    var marker = '<div id="' + id + '"';
    var i = h.indexOf(marker);
    if(i < 0) return h;
    var d = 0, k = i, end = -1;
    while(k < h.length) {
      if(h.slice(k,k+4) === '<div') { d++; k+=4; }
      else if(h.slice(k,k+6) === '</div>') { d--; if(d===0){end=k+6;break;} k+=6; }
      else k++;
    }
    return end > 0 ? h.slice(0,i) + h.slice(end) : h;
  }

  // 1. Remove abas meta e opac da dash-tabs
  html = html.replace(/<div class="dash-tab"[^>]*onclick="switchDashTab\('meta'[^"]*"[^>]*>[^<]*<\/div>/g, '');
  html = html.replace(/<div class="dash-tab"[^>]*onclick="switchDashTab\('opac'[^"]*"[^>]*>[^<]*<\/div>/g, '');

  // 2. Remove meta-filters-section (tem fechamento estático — está na sidebar antes das dash-tabs)
  html = removerDivById(html, 'meta-filters-section');

  // 3. Remove metaRoot + opacRoot + script injetados pelo aplicarExtras1421.
  // Esses divs são injetados antes de </body> e seus </div> estão dentro de strings JS,
  // então o contador não funciona. Estratégia: cortar do início de metaRoot até </body>
  // e reinserir </body></html>.
  var iMeta = html.indexOf('<div id="metaRoot"');
  if(iMeta < 0) iMeta = html.indexOf('<div id="opacRoot"'); // fallback
  if(iMeta >= 0) {
    // Também remover qualquer <script> de DET_1421 que veio antes dos divs
    var iScript = html.indexOf('<script>', iMeta - 2000); // olhar até 2kb antes
    while(iScript >= 0 && iScript < iMeta) {
      var snippetAfter = html.slice(iScript, iScript + 300);
      if(snippetAfter.indexOf('DET_1421') >= 0 || snippetAfter.indexOf('META_1421') >= 0) {
        iMeta = iScript; break;
      }
      var nextScript = html.indexOf('<script>', iScript+1);
      if(nextScript < 0 || nextScript >= iMeta) break;
      iScript = nextScript;
    }
    // Cortar tudo de iMeta até </body> inclusive
    var iBody = html.lastIndexOf('</body>');
    if(iBody > iMeta) {
      html = html.slice(0, iMeta) + '</body>' + html.slice(iBody + 7);
    }
  }

  return html;
}


function aplicarExtras1421(html,meta,opac,det){
  if(!meta||!opac||!CR1421_EXTRAS_TPL)return html;

  // Injetar apenas dados JS (abas já existem no base)
  var full=CR1421_EXTRAS_TPL
    .replace('__DET_JSON__', JSON.stringify(det))
    .replace('__META_JSON__',JSON.stringify(meta))
    .replace('__OPAC_JSON__',JSON.stringify(opac));

  // Separar: parte da sidebar vai dentro da sidebar; painéis+JS vão antes de </body>
  var SEP='<!--===SPLIT-SIDEBAR-PANELS===-->';
  var partes=full.split(SEP);
  var sbPart   = partes.length>1 ? partes[0] : '';
  var bodyPart = partes.length>1 ? partes[1] : full;

  // Injetar filtros na sidebar, logo antes da seção CR
  if(sbPart && html.indexOf('meta-filters-section')<0){
    var ANCHOR='    <div class="f-sec" data-sec="cr">';
    if(html.indexOf(ANCHOR)>=0){
      html=html.replace(ANCHOR, sbPart+'\n\n'+ANCHOR);
    }
  }


  var compactCss='<style>#meta-filters-section .f-sec{margin-bottom:2px}#meta-filters-section .f-sec-head{padding:7px 4px}#meta-filters-section .f-scroll-list{max-height:120px}#meta-filters-section .fclear{padding:6px 14px;font-size:11px;width:100%;background:#F39C12;color:#000;border:none;border-radius:6px;cursor:pointer}</style>';
  var autoFitStyle=compactCss+'<style>'+
    '#metaRoot,#opacRoot{overflow-x:auto}'+
    '#metaRoot table,#opacRoot table{min-width:900px;width:100%}'+
    '@media(max-width:1280px){#metaRoot,#opacRoot{font-size:12px}#metaRoot th,#opacRoot th,#metaRoot td,#opacRoot td{padding:7px 8px}}'+
    '@media(max-width:1100px){#metaRoot,#opacRoot{font-size:11px}#metaRoot th,#opacRoot th,#metaRoot td,#opacRoot td{padding:6px 6px}}'+
    '@media(min-width:1920px){#metaRoot,#opacRoot{font-size:15px}}'+
  '</style>';
  var autoFitScript='<script>(function(){var B=1440,MIN=0.6,MAX=1.25;function z(){var r=Math.min(MAX,Math.max(MIN,window.innerWidth/B));["metaRoot","opacRoot"].forEach(function(id){var e=document.getElementById(id);if(e)e.style.fontSize=Math.round(14*r)+"px";});}if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",z);}else{z();}var t;window.addEventListener("resize",function(){clearTimeout(t);t=setTimeout(z,150);});})();<\/script>';
  bodyPart = autoFitStyle + '<script>' + bodyPart + '<\/script>' + autoFitScript;
  // Remover injeção anterior (OPAC_1421, DET_1421, META_1421 + opacRoot + metaRoot)
  // para evitar duplicação quando o base já traz dados da última geração
  var CT='</'+'body>';
  var iBody=html.lastIndexOf(CT);
  if(iBody>0){
    var searchFor=['var DET_1421 =','var META_1421 =','var OPAC_1421 =','<div id="opacRoot"','<div id="metaRoot"'];
    var cutAt=iBody;
    for(var si=0;si<searchFor.length;si++){
      var p=html.indexOf(searchFor[si]);
      if(p>=0 && p<cutAt) cutAt=p;
    }
    if(cutAt<iBody) html=html.slice(0,cutAt)+CT+html.slice(iBody+CT.length);
    iBody=html.lastIndexOf(CT);
  }
  var result = iBody<0 ? html+bodyPart : html.slice(0,iBody)+bodyPart+'\n'+CT+html.slice(iBody+CT.length);

  // Remover aba OPAC (Produção Acumulada) do resultado final
  result = result.replace(/<div class="dash-tab"[^>]*onclick="switchDashTab\('opac'[^"]*"[^>]*>[^<]*<\/div>/g, '');
  // Remover painel opacRoot
  var iOpac = result.indexOf('<div id="opacRoot"');
  if(iOpac >= 0){
    var depth=1, p=iOpac+1;
    while(p < result.length && depth>0){
      var o=result.indexOf('<div',p), c=result.indexOf('</div>',p);
      if(o<0) o=result.length;
      if(c<0) c=result.length;
      if(o<c){ depth++; p=o+4; }
      else { depth--; p=c+6; }
    }
    if(depth<=0) result=result.slice(0,iOpac)+result.slice(p);
  }

  return result;
}

/* ============================== GERAR ============================== */
function readBuf(file){
  return new Promise(function(res,rej){
    var r=new FileReader();
    r.onload=function(e){res(e.target.result);};
    r.onerror=function(){rej(new Error('Erro ao ler '+file.name));};
    r.readAsArrayBuffer(file);
  });
}

async function gerar(){
  // Verificar libs
  if(typeof XLSX==='undefined'){showMsg('\u2717 Lib XLSX não carregou. Reabra o arquivo no navegador.',false);return;}
  if(typeof JSZip==='undefined'){showMsg('\u2717 Lib JSZip não carregou. Reabra o arquivo no navegador.',false);return;}

  var f1=document.getElementById('f1').files[0],
      f2=document.getElementById('f2').files[0],
      f3=document.getElementById('f3').files[0];
  if(!f1||!f2||!f3){showMsg('\u2717 Selecione os 3 arquivos antes de gerar.',false);return;}

  var logEl=document.getElementById('log');
  logEl.textContent='';logEl.style.display='none';
  document.getElementById('msg').style.display='none';
  document.getElementById('btn-dl').style.display='none';
  document.getElementById('var-grid').style.display='none';
  var btn=document.getElementById('btn-gerar');
  btn.disabled=true;btn.textContent='\u23f3 Processando...';

  try{
    addLog('Lendo index.html...');
    var htmlBase=new TextDecoder('utf-8').decode(await readBuf(f1));
    addLog('  index.html: '+Math.round(htmlBase.length/1024)+' KB');
    if(htmlBase.indexOf('window.__DASH_DATA__')<0)
      throw new Error('O arquivo não é o index.html correto (falta window.__DASH_DATA__)');

    addLog('Lendo dados.xlsb...');
    var wb1=XLSX.read(new Uint8Array(await readBuf(f2)),{type:'array'});
    var pcmR=processPCM(wb1);

    addLog('Lendo Base_Fat_Rend_Gn_Ms.xlsx...');
    var wb2=XLSX.read(new Uint8Array(await readBuf(f3)),{type:'array'});
    var fr4R=processFR4(wb2);
    var ex1421=readCR1421Extras(wb2);
    if(ex1421.meta) addLog('  Meta x Realizado: '+ex1421.meta.rows.length+' atividades');
    if(ex1421.opac) addLog('  Opera\u00e7\u00f5es Acumuladas: '+ex1421.opac.length+' linhas');

    addLog('');
    addLog('Gerando as 4 variantes...');
    var zip=new JSZip(),stats=[];
    for(var vi=0;vi<VARIANTES.length;vi++){
      var v=VARIANTES[vi];
      var pcmU=v.crs?filterPCM(pcmR.payload,v.crs):pcmR.payload;
      var fr4U=v.crs?filterFR4(fr4R.fr4,v.crs):fr4R.fr4;
      var hisU=v.crs?filterHist(fr4R.histMeta,v.crs):fr4R.histMeta;

      var html=inject(htmlBase,pcmU,fr4U,hisU);
      if(v.crs)html=fixROWS(html,v.crs);
      if(!v.fat)html=removeFat(html);
      if(v.pasta==='cr1421'||v.pasta==='gn-ms'){
        html=aplicarExtras1421(html,ex1421.meta,ex1421.opac,ex1421.det);
      } else {
        // lacan-arauco e pcm-lacan: remover abas Meta/OPAC do HTML
        html=removerMetaOpac(html);
      }
      // Injetar patch de Paradas APÓS aplicarExtras1421 para evitar que o corte do opacRoot remova o patch
      html=injetarPatchParadas(html);
      html=html.replace(/<title>[\s\S]*?<\/title>/,'<title>'+v.titulo+'</title>');

      var mb=Math.round(html.length/1048576*100)/100;
      addLog('  \u2713 '+v.pasta+' \u2014 '+mb+' MB');
      stats.push({pasta:v.pasta,mb:mb});
      zip.folder(v.pasta).file('index.html',html);
    }

    addLog('');
    addLog('Compactando ZIP...');
    var blob=await zip.generateAsync({type:'blob',compression:'DEFLATE',compressionOptions:{level:6}});
    var dl=document.getElementById('btn-dl');
    dl.href=URL.createObjectURL(blob);
    dl.style.display='block';

    var grid=document.getElementById('var-grid');
    grid.innerHTML=stats.map(function(s){
      return '<div class="vc"><div class="vp">'+s.pasta+'</div><div class="vs">'+s.mb+
             ' MB</div><div class="vd">'+(DESCS[s.pasta]||'')+'</div></div>';
    }).join('');
    grid.style.display='grid';

    showMsg('\u2713 ZIP pronto com os 4 dashboards. Clique em Baixar.',true);
    addLog('');
    addLog('\u2705 Conclu\u00eddo \u00b7 PCM at\u00e9 '+pcmR.dtMax+' \u00b7 Faturamento at\u00e9 '+fr4R.dtMax);
  }catch(e){
    addLog('');
    addLog('\u274c ERRO: '+e.message);
    if(e.stack)addLog(e.stack.split('\n').slice(0,4).join('\n'));
    showMsg('\u2717 '+e.message,false);
    console.error(e);
  }finally{
    btn.disabled=false;btn.textContent='\u26a1 Gerar 4 dashboards';
  }
}













