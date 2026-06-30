"""
models/output_models.py

Estruturas de saída do Motor NSI.
Espelha exatamente o Contrato Oficial do Motor NSI v3.1, Seção 8
(Estrutura JSON Final — Contrato Dashboard / PDF).

Cada dataclass corresponde a um bloco do JSON de exemplo do contrato.
Nenhum campo do contrato fica de fora; nenhum campo extra é inventado aqui.

Nenhuma lógica de cálculo vive aqui — apenas tipos.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


# ---------------------------------------------------------------------------
# Camada Matemática — Contrato Seção 2
# ---------------------------------------------------------------------------

@dataclass
class DistribuicaoTempoResposta:
    ate_1h: float
    ate_24h: float
    ate_3_dias: float
    acima_3_dias: float


@dataclass
class ResultadoMatematico:
    taxa_resposta: float
    taxa_silencio: float
    taxa_visualizado_sem_resposta: float
    taxa_nao_entrega: float
    tempo_medio_resposta_minutos: float
    tempo_mediano_resposta_minutos: float
    distribuicao_tempo_resposta: DistribuicaoTempoResposta
    tamanho_medio_resposta_caracteres: int
    participacao_valida: float
    qualidade_participacao_media: float


# ---------------------------------------------------------------------------
# Camada Linguística — Contrato Seção 3
# ---------------------------------------------------------------------------

@dataclass
class IroniaDetectada:
    presente: bool
    confianca: float


@dataclass
class MarcadoresDetectados:
    emojis: list[dict] = field(default_factory=list)
    girias_regionalismos: list[dict] = field(default_factory=list)
    abreviacoes: list[dict] = field(default_factory=list)
    pontuacao_intensificada: bool = False
    caixa_alta: bool = False
    repeticao_enfase: bool = False


@dataclass
class ResultadoLinguistico:
    """Saída da Camada Linguística para uma resposta individual."""
    intensidade_emocional: float
    polaridade_linguistica: float
    engajamento_linguistico: float
    formalidade: float
    marca_regional: float
    ironia_detectada: IroniaDetectada
    marcadores_detectados: MarcadoresDetectados


@dataclass
class ResultadoLinguisticoAgregado:
    """Saída da Camada Linguística agregada no nível do lote."""
    intensidade_emocional_media: float
    polaridade_linguistica_media: float
    engajamento_linguistico_medio: float
    formalidade_media: float
    marca_regional_media: float


# ---------------------------------------------------------------------------
# Camada Semântica — Contrato Seção 4
# ---------------------------------------------------------------------------

TipoCategoriaDetectada = Literal["forca", "dor"]


@dataclass
class CategoriaDetectada:
    """
    Uma classificação semântica individual dentro de uma resposta.
    Máximo 5 por resposta (Contrato Seção 4.3).
    """
    tipo: TipoCategoriaDetectada
    codigo_catalogo: str
    familia: str
    subcategoria: str
    nicho: Optional[str]
    area_responsavel: str
    confianca: float
    intensidade_semantica: float


@dataclass
class Evidencia:
    cliente_id: str
    trecho: str
    confianca: float
    intensidade_semantica: float


@dataclass
class CategoriaAgregada:
    """Uma família/subcategoria agregada no nível do lote (dor ou força)."""
    codigo_catalogo: str
    familia: str
    subcategoria: str
    nicho: Optional[str]
    incidencia_percentual: float
    confianca_media: float
    intensidade_semantica_media: float
    ocorrencias: int
    evidencias: list[Evidencia] = field(default_factory=list)


@dataclass
class ResultadoSemantico:
    """Saída da Camada Semântica agregada no nível do lote."""
    dores_identificadas: list[CategoriaAgregada] = field(default_factory=list)
    forcas_identificadas: list[CategoriaAgregada] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Camada de Experiência Humana — Contrato Seção 5
# ---------------------------------------------------------------------------

@dataclass
class ResultadoExperienciaHumana:
    """Saída da Camada de Experiência Humana para uma resposta individual."""
    entusiasmo: float
    confianca_cliente: float
    frustracao: float
    envolvimento: float
    empolgacao: float
    seguranca: float
    indiferenca: float
    lealdade: float
    gratidao: float
    desgaste: float


@dataclass
class ResultadoExperienciaHumanaAgregado:
    """Saída da Camada de Experiência Humana agregada no nível do lote."""
    entusiasmo_medio: float
    confianca_cliente_media: float
    frustracao_media: float
    envolvimento_medio: float
    empolgacao_media: float
    seguranca_media: float
    indiferenca_media: float
    lealdade_media: float
    gratidao_media: float
    desgaste_medio: float


# ---------------------------------------------------------------------------
# Camada de Evolução Temporal — Contrato Seção 6
# ---------------------------------------------------------------------------

Comparabilidade = Literal["total", "parcial"]


@dataclass
class VariacaoFamilia:
    familia: str
    percentual_anterior: float
    percentual_atual: float
    variacao: float
    tendencia: Literal["subindo", "estavel", "caindo"]


@dataclass
class VariacaoMatematica:
    indicador: str
    anterior: float
    atual: float
    variacao: float


@dataclass
class ResultadoEvolucaoTemporal:
    """
    Saída da Camada de Evolução Temporal.
    Ausente por completo (não None dentro do objeto raiz) quando não há
    lote anterior comparável — Contrato Seção 6.2.
    """
    lote_comparado_id: str
    comparabilidade: Comparabilidade
    variacoes_familia: list[VariacaoFamilia] = field(default_factory=list)
    variacoes_matematica: list[VariacaoMatematica] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Camada Executiva — Contrato Seção 7
# ---------------------------------------------------------------------------

@dataclass
class ItemRanking:
    posicao: int
    categoria: str
    percentual: float


@dataclass
class ItemPrioridade:
    posicao: int
    categoria: str
    criterio: str
    valor: float


@dataclass
class AreaAgregada:
    area: str
    percentual_oportunidades: float


@dataclass
class BaseadoEm:
    ocorrencias: int
    confianca_media: float
    tendencia: Optional[Literal["subindo", "estavel", "caindo"]] = None


@dataclass
class AcaoRecomendada:
    """
    Contrato Seção 7.4 / 9.8 — gerada pela Camada Executiva a partir do
    contexto real do lote. Nunca uma regra fixa do catálogo.
    """
    posicao: int
    categoria: str
    codigo_catalogo: str
    area_responsavel: str
    recomendacao: str
    baseado_em: BaseadoEm


@dataclass
class ResultadoExecutivo:
    """Saída completa da Camada Executiva — Contrato Seção 7."""
    status_ice: str
    ice_nsi: float
    ice_versao: str
    motivo: str = None
    top_forcas: list[ItemRanking] = field(default_factory=list)
    top_oportunidades: list[ItemRanking] = field(default_factory=list)
    top_prioridades: list[ItemPrioridade] = field(default_factory=list)
    areas_responsaveis_agregado: list[AreaAgregada] = field(default_factory=list)
    acoes_recomendadas: list[AcaoRecomendada] = field(default_factory=list)
    resumo_executivo: str = ""
    resumo_comercial: str = ""
    resumo_operacional: str = ""
    resumo_atendimento: str = ""
    resumo_produto: str = ""
    resumo_experiencia: str = ""
    resumo_evolutivo: Optional[str] = None
    resumo_nicho: Optional[str] = None


# ---------------------------------------------------------------------------
# Rastreabilidade do modelo de IA — Contrato Seção 1.1
# ---------------------------------------------------------------------------

@dataclass
class ModeloClassificacao:
    """
    Uso interno — não exibido ao cliente final (Contrato Seção 1.1).
    """
    provider: str
    modelo: str
    versao_prompt: str


# ---------------------------------------------------------------------------
# Resposta individual completa — bloco respostas_individuais (Contrato Seção 8)
# ---------------------------------------------------------------------------

@dataclass
class RespostaIndividualCompleta:
    cliente_id: str
    telefone: str
    resposta: str
    qualidade_participacao: float
    linguistica: ResultadoLinguistico
    experiencia_humana: ResultadoExperienciaHumana
    categorias_detectadas: list[CategoriaDetectada] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Objeto raiz — Contrato Seção 8
# ---------------------------------------------------------------------------

StatusSemantico = Literal["concluido", "pendente"]


@dataclass
class SaidaMotorCompleta:
    """
    Objeto JSON final único entregue pelo Motor NSI.
    Contrato v3.1, Seção 8.

    `semantica`, `experiencia_humana_agregada`, `evolucao_temporal` e `executiva`
    são Optional porque ficam ausentes quando `status_semantico == "pendente"`
    (fallback sem IA, Contrato Seção 1.2) ou — no caso de `evolucao_temporal` —
    quando não há lote anterior comparável (Contrato Seção 6.2).
    """
    empresa: str
    segmento: str
    lote_id: str
    data_processamento: datetime
    versao_motor: str
    versao_catalogo: str
    status_semantico: StatusSemantico
    evidencias_semanticas_validas: int
    modelo_classificacao: ModeloClassificacao
    matematica: ResultadoMatematico
    linguistica_agregada: ResultadoLinguisticoAgregado
    semantica: Optional[ResultadoSemantico] = None
    experiencia_humana_agregada: Optional[ResultadoExperienciaHumanaAgregado] = None
    evolucao_temporal: Optional[ResultadoEvolucaoTemporal] = None
    executiva: Optional[ResultadoExecutivo] = None
    respostas_individuais: list[RespostaIndividualCompleta] = field(default_factory=list)
