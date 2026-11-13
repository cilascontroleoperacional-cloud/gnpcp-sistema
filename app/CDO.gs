// ============================================================================
// CDO.gs — aba "Conferir CDOs" do app GN PCP (arquivo NOVO no mesmo projeto do Codigo.gs)
// Fala com o servidor do Render: /cdo/detectar, /cdo/status e /cdo/aplicar.
// Usa as funções que já existem no Codigo.gs: verificarToken_, chamarRender_,
// acordarRender_ e registrarLog_.
//
// NO Codigo.gs, dentro do doPost, acrescentar na lista de funções permitidas
// (logo abaixo de "statusAtualizacao: statusAtualizacao,"):
//       cdoDetectar: cdoDetectar,
//       cdoStatus: cdoStatus,
//       cdoAplicar: cdoAplicar,
// ============================================================================

const CDO_SESSAO_ = 'Sessao expirada. Faca login novamente.';

function cdoErroHttp_(code, texto) {
  let detalhe = '';
  try { detalhe = (JSON.parse(texto) || {}).erro || ''; } catch (_) {}
  if (code === 401) return 'Servidor recusou a chave (API_KEY do app diferente da do Render).';
  if (code === 404) return 'O servidor ainda nao tem a conferencia de CDO. Faca o Manual Deploy no Render.';
  return detalhe || ('Servidor respondeu HTTP ' + code + '.');
}

// data: "DD/MM/AAAA" (vazio = ontem). contrato: nome exato ou vazio = todos.
function cdoDetectar(token, data, contrato) {
  const usuario = verificarToken_(token);
  if (!usuario) return { ok: false, msg: CDO_SESSAO_ };
  if (data && !/^\d{2}\/\d{2}\/\d{4}$/.test(String(data))) return { ok: false, msg: 'Data invalida.' };
  try {
    if (!acordarRender_()) return { ok: false, msg: 'O servidor do Render nao respondeu. Tente de novo em 1 minuto.' };
    const corpo = {};
    if (data) corpo.data = String(data);
    if (contrato) corpo.contratos = [String(contrato)];
    const r = chamarRender_('post', '/cdo/detectar', corpo);
    const code = r.getResponseCode();
    if (code === 200) { registrarLog_(usuario, 'CDO CONFERIR ' + (data || 'ontem'), 1); return { ok: true }; }
    if (code === 409) return { ok: true, jaRodando: true };
    return { ok: false, msg: cdoErroHttp_(code, r.getContentText()) };
  } catch (e) {
    return { ok: false, msg: 'Erro ao chamar o servidor: ' + e.message };
  }
}

function cdoStatus(token) {
  if (!verificarToken_(token)) return { ok: false, msg: CDO_SESSAO_ };
  try {
    const r = chamarRender_('get', '/cdo/status');
    const code = r.getResponseCode();
    if (code !== 200) return { ok: false, msg: cdoErroHttp_(code, r.getContentText()) };
    const s = JSON.parse(r.getContentText());
    // a tela nao precisa do corpo do PUT nem das linhas de detalhe: resposta mais leve
    ((s.deteccao || {}).cdos || []).forEach(function (c) {
      (c.achados || []).forEach(function (a) {
        delete a.corpo; delete a.rota; delete a.metodo; delete a.linhas;
        delete a.presentes; delete a.ausentes; delete a.colaboradores; delete a.equipamentos; delete a.itens;
      });
    });
    return {
      ok: true, rodando: !!s.rodando, etapa: s.etapa, erro: s.erro,
      progresso: (s.progresso || []).slice(-40),
      iniciado_em: s.iniciado_em, finalizado_em: s.finalizado_em,
      deteccao: s.deteccao, aplicacao: s.aplicacao
    };
  } catch (e) {
    return { ok: false, msg: 'Erro ao consultar o servidor: ' + e.message };
  }
}

// ids: lista de ids de correcoes "prontas" marcadas na tela (vindos da ultima conferencia).
function cdoAplicar(token, ids) {
  const usuario = verificarToken_(token);
  if (!usuario) return { ok: false, msg: CDO_SESSAO_ };
  if (!Array.isArray(ids) || !ids.length || ids.length > 500 ||
      !ids.every(function (i) { return typeof i === 'string' && /^[0-9a-f]{12}$/.test(i); })) {
    return { ok: false, msg: 'Nenhuma correcao valida selecionada.' };
  }
  try {
    const r = chamarRender_('post', '/cdo/aplicar', { ids: ids });
    const code = r.getResponseCode();
    if (code === 200) { registrarLog_(usuario, 'CDO APLICAR', ids.length); return { ok: true }; }
    if (code === 409) return { ok: false, msg: cdoErroHttp_(code, r.getContentText()) ||
                                               'Servidor ocupado ou sem conferencia. Clique em Conferir CDOs de novo.' };
    return { ok: false, msg: cdoErroHttp_(code, r.getContentText()) };
  } catch (e) {
    return { ok: false, msg: 'Erro ao chamar o servidor: ' + e.message };
  }
}
