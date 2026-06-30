// ===== VARIÁVEIS GLOBAIS =====
var loteAtual = null;

// ===== CRIAR LOTE =====
function criarLote() {
  var empresa = document.getElementById('empresa').value.trim();
  var nome = document.getElementById('nome-lote').value.trim();
  var dataInicio = document.getElementById('data-inicio').value;
  var dataFim = document.getElementById('data-fim').value;
  var arquivo = document.getElementById('arquivo-csv').files[0];

  if (!empresa || !nome || !arquivo) {
    exibirErro('Preencha empresa, nome do lote e selecione o arquivo CSV.');
    return;
  }

  var formData = new FormData();
  formData.append('file', arquivo);
  formData.append('empresa', empresa);
  formData.append('nome', nome);
  formData.append('data_inicio', dataInicio);
  formData.append('data_fim', dataFim);

  exibirErro('');
  document.getElementById('btn-criar').disabled = true;
  document.getElementById('btn-criar').textContent = 'Criando...';

  fetch('/upload', { method: 'POST', body: formData })
    .then(function(res) { return res.json(); })
    .then(function(dados) {
      if (dados.erro) {
        exibirErro('Erro: ' + dados.erro);
        document.getElementById('btn-criar').disabled = false;
        document.getElementById('btn-criar').textContent = 'Criar Lote';
        return;
      }
      loteAtual = dados.lote_id;
      document.getElementById('btn-criar').textContent = 'Criar Lote';
      document.getElementById('btn-criar').disabled = false;
      document.getElementById('btn-processar').disabled = false;
      exibirCardLote(dados, empresa, nome);
      mostrarPipeline();
    })
    .catch(function(err) {
      exibirErro('Erro de conexão: ' + err);
      document.getElementById('btn-criar').disabled = false;
      document.getElementById('btn-criar').textContent = 'Criar Lote';
    });
}

// ===== EXIBIR CARD DO LOTE =====
function exibirCardLote(dados, empresa, nome) {
  var card = document.getElementById('card-lote');
  card.classList.remove('oculto');
  document.getElementById('card-empresa').textContent = empresa;
  document.getElementById('card-nome').textContent = nome;
  document.getElementById('card-id').textContent = dados.lote_id;
  document.getElementById('card-total').textContent = dados.total_clientes;
}

// ===== PIPELINE =====
function mostrarPipeline() {
  document.getElementById('secao-pipeline').classList.remove('oculto');
  concluirStep('step-upload');
  concluirStep('step-lote');
  ativarStep('step-d8');
  if (loteAtual) iniciarMonitorD8(loteAtual);
}

function concluirStep(stepId) {
  var el = document.getElementById(stepId);
  if (el) el.className = 'concluido';
}

function ativarStep(stepId) {
  var el = document.getElementById(stepId);
  if (el) el.className = 'ativo';
}

// ===== PROCESSAR LOTE =====
function processarLote() {
  if (!loteAtual) return;
  document.getElementById('btn-processar').disabled = true;
  fetch('/lote/' + loteAtual + '/analisar', { method: 'POST' })
    .then(function(res) { return res.json(); })
    .then(function() {
      concluirStep('step-d8');
      ativarStep('step-disparo');
    });
}

// ===== UTILITÁRIOS =====
function exibirErro(msg) {
  var el = document.getElementById('msg-erro');
  if (el) el.textContent = msg;
}
// ===== D+8 EM TEMPO REAL =====
function consultarD8(loteId) {
  fetch('/api/lote/' + loteId + '/d8')
    .then(function(res) { return res.json(); })
    .then(function(d8) {
      var el = document.getElementById('step-d8');
      if (!el) return;
      if (d8.pronto) {
        concluirStep('step-d8');
        ativarStep('step-disparo');
      } else {
        el.textContent = 'Aguardando D+8 — ' + d8.dias_restantes + ' dias restantes (' + d8.percentual + '%)';
      }
    });
}

function iniciarMonitorD8(loteId) {
  consultarD8(loteId);
  setInterval(function() { consultarD8(loteId); }, 60000);
}