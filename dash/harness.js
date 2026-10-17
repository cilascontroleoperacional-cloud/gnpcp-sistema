// Executa a lógica do Atualizador_v2 (idêntica) em Node.
const fs=require('fs'), vm=require('vm'), XLSX=require('xlsx');
function carregar(){
  const ctx={XLSX, console, TextDecoder, JSON, Math, Date, Object, String, Number, Array, RegExp, parseFloat, isNaN};
  ctx.addLog=(t)=>{ if(process.env.VERBOSE) console.log(t); ctx._log.push(t); }; ctx._log=[];
  vm.createContext(ctx);
  let code=fs.readFileSync(__dirname+'/atu_logic.js','utf8');
  code=code.replace(/\/\* =+ GERAR =+ \*\/[\s\S]*$/,'');   // sem a parte de interface (gerar/readBuf)
  vm.runInContext(code,ctx);
  vm.runInContext(fs.readFileSync(__dirname+'/variantes.js','utf8'),ctx);
  return ctx;
}
function gerar(ctx, htmlBase, wb1, wb2, grids){
  const pcmR=ctx.processPCM(wb1), fr4R=ctx.processFR4(wb2), ex=ctx.readCR1421Extras(wb2);
  const out={};
  const fup=grids&&grids['CAD_TALHOES']?require('./followup_dash').montarDados(grids):null;
  for(const v of ctx.VARIANTES){
    const pcmU=v.crs?ctx.filterPCM(pcmR.payload,v.crs):pcmR.payload;
    const fr4U=v.crs?ctx.filterFR4(fr4R.fr4,v.crs):fr4R.fr4;
    const hisU=v.crs?ctx.filterHist(fr4R.histMeta,v.crs):fr4R.histMeta;
    let html=ctx.inject(htmlBase,pcmU,fr4U,hisU);
    if(v.crs) html=ctx.fixROWS(html,v.crs);
    if(!v.fat) html=ctx.removeFat(html);
    if(v.pasta==='cr1421'||v.pasta==='gn-ms') html=ctx.aplicarExtras1421(html,ex.meta,ex.opac,ex.det);
    else html=ctx.removerMetaOpac(html);
    html=ctx.injetarPatchParadas(html);
    if(fup&&v.fat) html=require('./followup_dash').injetarFollowup(html,fup,v.crs);
    html=html.replace(/<title>[\s\S]*?<\/title>/,'<title>'+v.titulo+'</title>');
    out[v.pasta]=html;
  }
  return {out, pcmR, fr4R, ex, log:ctx._log};
}
module.exports={carregar,gerar,XLSX};
