const {carregar,gerar,XLSX}=require('./harness');
const fs=require('fs');
function wbDaBase(g){ const wb=XLSX.utils.book_new(); for(const k in g){ XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet(g[k]),k);} return wb;}
const g=JSON.parse(fs.readFileSync(__dirname+'/base_grids.json','utf8'));
const wb=wbDaBase(g);
const ctx=carregar();
const html=fs.readFileSync('index_base.html','utf8');
const r=gerar(ctx,html,wb,wb);
fs.mkdirSync('out_base',{recursive:true});
for(const k in r.out) fs.writeFileSync('out_base/'+k+'.html',r.out[k]);
console.log(r.log.join('\n'));
