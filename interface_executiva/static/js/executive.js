// ===== CONTROLE DE ABAS =====
document.querySelectorAll('.aba').forEach(function(btn) {
  btn.addEventListener('click', function() {
    // Oculta todos os painéis
    document.querySelectorAll('.painel').forEach(function(p) {
      p.classList.add('oculto');
    });
    // Remove destaque de todas as abas
    document.querySelectorAll('.aba').forEach(function(b) {
      b.classList.remove('ativa');
    });
    // Mostra o painel correto
    var alvo = this.getAttribute('data-aba');
    document.getElementById(alvo).classList.remove('oculto');
    this.classList.add('ativa');
  });
});

// ===== TROCA DE RELATÓRIO =====
function carregarRelatorio(relatorioId) {
  fetch('/api/relatorio/' + relatorioId)
    .then(function(res) { return res.json(); })
    .then(function(dados) {
      // Atualiza header
      document.getElementById('header-data').textContent = dados.data;
      document.getElementById('header-lote').textContent = dados.lote;
      // Dispara evento para os painéis atualizarem
      document.dispatchEvent(new CustomEvent('relatorio:carregado', { detail: dados }));
    });
}

// ===== INICIALIZAÇÃO =====
document.addEventListener('DOMContentLoaded', function() {
  // Ativa a primeira aba por padrão
  var primeiraAba = document.querySelector('.aba');
  if (primeiraAba) primeiraAba.click();
});