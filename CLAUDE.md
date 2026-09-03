# Painel de Monitoramento de Constrained-off — Conjuntos Eólicos do RN

> Trabalho acadêmico de mestrado. Guia de referência do projeto para o Claude Code.
> Última atualização: 2026-09-02.

---

## 0. Visão Geral

Painel web (Streamlit) de monitoramento de **constrained-off** (corte de
geração por restrição operativa) dos conjuntos eólicos do Rio Grande do
Norte. Três entregas concluídas: (1) mapa de localização interativo, com
subestações/cidades fixas, linhas de conexão e ficha de detalhe por
conjunto; (2) motor de **Energia Frustrada** com download automático dos
dados abertos do ONS (constrained-off) e da CCEE (PLD horário) e cálculo
das 5 metodologias definidas pelo usuário; (3) **Painel de Preço Horário
(PLD)** do submercado Nordeste, no estilo do painel da própria CCEE.
Próximas fases (ficha de detalhe de subestação com documentos vinculados,
linhas de transmissão coloridas por tensão) dependem de dados de nível de
tensão (kV) por subestação, ainda não recebidos.

- **Stack:** Python 3.13 / Streamlit / Folium (mapa) / Plotly (gráficos) /
  Pandas / NumPy / Shapely / Pillow (ícones) / httpx + Requests (downloads)
- **Repositório:** https://github.com/Daniel-Nascimento-EOL/Painel-de-Monitoramento---COCERN
  (privado, branch `main`)
- **Comando de execução:** `streamlit run app.py` (venv em `.venv/`, Python 3.13)

---

## 1. Arquitetura

```
streamlit run app.py
        ↓
app.py                        ── page_config, CSS global, roteador (radio na sidebar: Mapa | Energia Frustrada | Preço Horário)
  ├── ui/mapa.py               ── página do mapa: filtros, métricas, render do mapa, botão "baixar PNG do mapa"
  │     ├── core/data_loader.py    ── carrega/normaliza Excel (@st.cache_data)
  │     ├── viz/map_charts.py      ── constrói o folium.Map (ícones, máscara, bounds, linhas)
  │     └── viz/mapa_estatico.py   ── mesmo mapa como PNG (staticmap) — download e mini-mapa do PDF
  ├── ui/energia_frustrada.py  ── página de energia frustrada: filtros (mês, conjunto, metodologia), export PDF
  │     ├── core/ons_coff.py       ── download ONS (COFF eólico, RN) + 5 metodologias
  │     ├── core/coff_cache.py     ── cache Parquet do COFF agregado por conjunto/mês
  │     ├── core/ccee_pld.py       ── download CCEE (PLD horário NE) com cascata de fallback
  │     ├── core/relatorio_dados.py ── compila o "dossiê" por conjunto (cadastro + SE/linhas + COFF do mês)
  │     └── viz/pdf_relatorio.py    ── relatório PDF consolidado (ReportLab + matplotlib): capa, resumo RN, seção/conjunto
  └── ui/painel_pld.py         ── painel de preço horário: PLD da hora, curva do dia (Ontem/Hoje/Amanhã), evolução recente

core/
  ├── agentes.py                ── cadastro dos agentes + logomarcas locais
  └── documentos_ons.py         ── resolve o ajustamento operativo no PDF do MPO

scripts/
  ├── baixar_logos_agentes.py   ── baixa as logomarcas para data/icons/agentes/
  └── atualizar_cache_coff.py   ── pré-aquece data/cache_coff/

data/
  ├── localizacao_conjuntos_ons_aneel.xlsx   ── conjuntos: ONS/ANEEL + id_ons, capacidade, ponto de
  │                                              conexão, agentes proprietário/operador (+ logos)
  ├── bays.xlsx                                ── subestações do RN/PB (agente operador, lat/long) e
  │                                              cidades de referência
  ├── rn_estado.geojson                        ── contorno do RN (IBGE, baixado uma vez)
  ├── historico_pld_ne.csv                     ── PLD horário NE desde 01/01/2021 (fallback offline da
  │                                              CCEE — é o que o deploy usa; ver §2.4 e §6)
  ├── cache_coff/                              ── Parquet do COFF agregado por conjunto/mês
  │                                              (~9 KB/mês, versionado — ver §4.4)
  └── icons/
        ├── logo_aero.jpg                      ── ícone de turbina (marcador de conjunto)
        ├── logo_se.jpeg                        ── ícone de subestação (marcador de bay)
        └── agentes/                            ── 30 logomarcas oficiais (ver §2.5)

docs/
  └── fontes_dados_abertos.md   ── levantamento de datasets ONS/ANEEL/COSERN
```

---

## 2. Dados

### 2.1 Conjuntos (`data/localizacao_conjuntos_ons_aneel.xlsx`)

3 abas:
- **Localizacao** (54 linhas): conjunto, `id_ons` (chave de junção com o
  dataset de constrained-off do ONS), `Localização (lat, long)` (string
  combinada `"lat, long"`, parseada em `core/data_loader.py`), município(s),
  capacidade instalada (`"109,20 MW"` — parser tolera espaços soltos tipo
  `"63 ,00MW"`), qtd. usinas/aerogeradores, ponto de conexão, agente
  proprietário/operador (+ URLs de logo), ajustamento operativo.
- **Detalhamento** (309 linhas): usina individual, **CEG**, lat/long,
  município (colunas separadas, ao contrário de Localizacao).
- **Fontes e metodologia**: proveniência (ONS SINMAPS, ONS conjunto↔usina,
  ANEEL SIGA).

**Gotcha de join conjunto↔usina**: os nomes NÃO batem direto —
`"Conjunto Eólico Acauã"` (Localizacao) vs `"CONJ. ACAUÃ"` (Detalhamento).
`core/data_loader.py::_chave_conjunto()` normaliza (strip de prefixo +
uppercase). Validado: 54/54 sem sobra.

### 2.2 Subestações e cidades (`data/bays.xlsx`)

- **Bays** (15 linhas, RN + PB): agente operador, subestação, lat/long.
  Junta com `Localizacao["Ponto de conexão"]` (ex.: `"SE Açu II"`) via
  `core/data_loader.py::_chave_subestacao()` (remove prefixo `SE `,
  uppercase). Validado: 15/15 sem sobra.
- **Cidades_RN** (21 linhas): cidades de referência pra ficarem fixas no
  mapa (sem interação, só rótulo).

### 2.3 Dataset ONS de constrained-off (ao vivo)

`core/ons_coff.py::baixar_mes_rn()` baixa direto do S3 público do ONS:
`https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/restricao_coff_eolica_tm/RESTRICAO_COFF_EOLICA_{ano}_{mes:02d}.csv`
(CSV `;`-delimitado, um arquivo por mês, desde 2021-01, atualizado 2x/dia
pelo ONS às 12h e 19h). Filtra `id_estado == "RN"` logo após o download
(arquivo original cobre o Brasil todo). Cache `@st.cache_data(ttl=6h)`.

`id_ons` no CSV do ONS é por "usina" (mas cada conjunto do RN é reportado
como uma usina agregada — 54 usinas únicas no dataset = 54 conjuntos),
e bate 1:1 com `Localizacao["id_ons"]`.

### 2.4 Preço horário — PLD da CCEE (ao vivo, com cascata de fallback)

`core/ccee_pld.py::baixar_pld_nordeste(ano)` baixa o **PLD horário** do
submercado Nordeste dos dados abertos da CCEE (dataset `pld_horario`, um
CSV por ano em `pda-download.ccee.org.br/{recurso}/content`; colunas
`MES_REFERENCIA`, `SUBMERCADO`, `PERIODO_COMERCIALIZACAO`, `DIA`, `HORA`,
`PLD_HORA`). Cache `@st.cache_data(ttl=6h)`.

**A web é sempre a fonte principal** — o objetivo é que anos novos entrem
sozinhos conforme a CCEE publica. Duas cascatas, cada uma com fallbacks:

*Descoberta da URL do ano* (`_urls_por_ano()`, cache 6 h):
1. API CKAN `package_show?id=pld_horario` → JSON com `pld_horario_{ano}` → URL
2. HTML de `dadosabertos.ccee.org.br/dataset/pld_horario` (regex nos links)
3. `_RECURSOS_CONHECIDOS` — ids fixos no código (2021–2026), último recurso

*Download do CSV*: httpx → curl (subprocesso) → requests → `data/historico_pld_ne.csv`.

Cada nível foi testado forçando a falha do anterior. `anos_disponiveis()`
devolve os anos publicados (mais recente primeiro).

**Gotcha do bloqueio da CCEE — não "consertar" removendo os headers**: o
perímetro da CCEE responde 403 "acesso bloqueado" a requisições que não
pareçam de navegador, em **duas camadas independentes**:

1. **Cabeçalhos**: só `User-Agent` não basta. Precisa do conjunto
   `Sec-Fetch-*` / `Sec-Ch-Ua` / `Upgrade-Insecure-Requests` que um Chrome
   envia numa navegação (`_CABECALHOS`).
2. **Impressão digital TLS**: mesmo com os cabeçalhos certos, `requests`
   (urllib3) leva 403 — o handshake não parece de navegador. `httpx` e o
   binário `curl` passam.

Por isso a cascata de transportes acima. Se nada funcionar,
`baixar_pld_nordeste` retorna `None` e a UI mostra a energia frustrada em
MWh sem o impacto financeiro, com aviso.

**O bloqueio não é por IP** — medido: do IP residencial brasileiro e de um
runner do GitHub na Azure/EUA (`20.168.159.169`), `httpx` e `curl` (com os
cabeçalhos completos) passam, e `requests` é barrado nos dois. O que a CCEE
rejeita é a combinação cabeçalhos + impressão digital TLS.

Por isso a atualização do fallback é automática: o workflow
`.github/workflows/atualizar-pld.yml` roda `scripts/atualizar_pld_local.py`
toda segunda-feira e commita o CSV se houver dados novos. Ele começa por um
diagnóstico que testa os três transportes e falha com orientação explícita
se algum dia todos forem bloqueados, em vez de commitar uma série velha em
silêncio.

O script também pode ser rodado à mão (`python scripts/atualizar_pld_local.py`)
antes de um deploy urgente. Ele confere as horas em comum com a versão
anterior e aborta se divergirem.

**Por que PLD e não CMO** (a decisão anterior era o inverso — ver histórico
do commit `491a5a6`): o **CMO** do ONS é o custo marginal de operação, sem
piso nem teto, e **zera com frequência no Nordeste** quando sobra geração
renovável — em vários meses de 2024 a mediana ficou abaixo de R$ 2/MWh,
fazendo o painel reportar perdas de poucos reais. O **PLD** é o preço de
liquidação: parte do CMO mas aplica o piso/teto da ANEEL e o processamento
da CCEE. Constrained-off é energia que a usina deixou de **liquidar**, logo
vale o PLD. Exemplo: Baixa do Feijão, jan/2024, 151,37 MWh → R$ 3 pelo CMO
(R$ 0,02/MWh) vs. **R$ 9.244 pelo PLD** (R$ 61,07/MWh, piso do ano).

A avaliação anterior concluiu que o portal da CCEE estava "fora do ar"; na
verdade era o bloqueio de automação descrito acima.

**Validação**: 32.640 horas conferidas contra a série de PLD do estudo de
referência do cliente, **zero divergências**. Pisos anuais batem com os
Despachos da ANEEL (49,77 em 2021 · 55,70 em 2022 · 69,04 em 2023 · 61,07
em 2024 · 58,60 em 2025 · 57,31 em 2026). Cobertura 01/01/2021–hoje, sem
lacunas.

---

### 2.5 Logomarcas dos agentes (`core/agentes.py` + `data/icons/agentes/`)

As colunas `Logo - Agente Proprietário` / `Logo - Agente Operador` da
planilha apontavam para miniaturas do **cache de imagens do Google**
(`encrypted-tbn0.gstatic.com`). Esses endereços expiram e vinham com a
marca errada: a **Simm Soluções** aparecia com a logomarca da New Energy
Options em alguns conjuntos e a da V2i Energia em outros. A coluna do
operador vinha vazia em boa parte das linhas.

Agora as 30 logomarcas são baixadas da **fonte oficial de cada agente** e
versionadas em `data/icons/agentes/`, resolvidas por
`core/agentes.py::logo_agente()`. As colunas de logo da planilha **não são
mais usadas** — não voltar a lê-las.

- Fonte preferida, nesta ordem: arquivo publicado no site do agente →
  `logo.dev` pelo domínio institucional → `apple-touch-icon` do site
  oficial (usado na Echoenergia, cuja logomarca do cabeçalho é SVG
  embutido no HTML, sem URL própria).
- **Gotcha do domínio**: `logo.dev` devolve um **monograma genérico** (uma
  letra) para domínio inexistente, com HTTP 200 — não dá erro. Conferir
  visualmente ao acrescentar um agente. Foi o que pegou Ibitu
  (`ibituenergia.com`, não `.com.br`) e V2i (`v2ienergia.com`, não
  `.com.br`).
- **New Energy Options** é subsidiária integral da **Multiner** e não tem
  marca nem domínio próprios ativos — usa a logomarca da Multiner.
- `LOGOS_FUNDO_ESCURO` lista as marcas brancas (Serveng), gravadas sobre
  fundo escuro para não sumirem na ficha.
- Atualizar com `python scripts/baixar_logos_agentes.py`.
- **Múltiplos agentes**: o campo da planilha admite co-propriedade separada
  por barra (`Voltalia / Copel / Toda`); `separar_agentes()` divide e a
  ficha lista todos, cada um com sua logomarca.
- **Gotcha do peso no HTML**: embutir a `data:` URI em cada uma das 54
  fichas multiplicava o mesmo base64 (HTML de 660 KB para 4,1 MB).
  `classe_css_logos()` declara cada logomarca **uma vez** como classe CSS;
  as fichas referenciam pela classe. Além disso a logomarca é reduzida a
  64 px antes de codificar (renderiza a ~30 px). HTML final: 951 KB.

---

## 3. Mapa (Folium) — decisões e gotchas técnicos

Trocado de Plotly pra **Folium/Leaflet** porque o usuário pediu ícone
customizado de aerogerador nos marcadores — Plotly `Scattermapbox` só
suporta símbolos customizados com estilo Mapbox GL pago/tokenizado.

- **Ícones tingidos**: `viz/map_charts.py::_tingir_icone_array()` — os
  ícones enviados pelo usuário (`data/icons/logo_aero.jpg`,
  `logo_se.jpeg`) vêm como linha preta sobre fundo quase branco. A função
  usa Pillow/NumPy pra tornar o fundo transparente (rampa de alpha por
  luminosidade) e tingir os traços na paleta do projeto, cacheado com
  `@st.cache_resource`. Os PNGs de origem são 512×512 mas renderizam a
  ~24 px — `_tingir_icone_array` reduz para `_RESOLUCAO_ICONE` (64 px)
  antes de codificar.
- **Perf do mapa** (era o maior gargalo): `folium.CustomIcon` recomprimia
  o PNG com `zlib.compress` a cada um dos ~69 marcadores (54 conjuntos +
  15 subestações) — 84% do tempo de build. Corrigido em duas frentes:
  (1) `_icone_data_uri()` codifica o PNG **uma vez por (arquivo, cor)**
  como `data:` URI, cacheado (`@st.cache_resource`); só há 2 ícones
  distintos; (2) o downscale para 64 px derruba o PNG embutido de ~51 KB
  para ~5 KB por marcador. Build caiu de ~3,6 s para ~250 ms; HTML de
  ~2 MB para ~660 KB. Além disso `build_map_html()` (`@st.cache_data`)
  recebe os DataFrames serializados como JSON (via `df_para_key()`) e
  devolve o HTML já renderizado — alternar uma camada com os mesmos dados
  reaproveita o cache (~1 ms) em vez de reconstruir. Render via
  `streamlit.components.v1.html` (one-way, leve), não `st_folium`
  (round-trip bidirecional que não era usado — `returned_objects=[]`).
- **Subestações e cidades ficam sempre visíveis** (não passam pelos
  filtros da sidebar) — pedido explícito do usuário via áudio, pra dar
  noção da escassez de subestações de transmissão no RN.
- **Só entram subestações de transmissão.** O cadastro do ONS mistura as SE
  da rede de transmissão com as **coletoras dos próprios conjuntos**
  (agente principal = SPE da usina: SE JERUSALÉM/Statkraft, SE RIO DO
  VENTO/CVER, SE ALEGRIA/New Energy, CUTIA, GAMELEIRA...), que duplicavam o
  marcador do conjunto. `core/ons_rede.py::_e_transmissora()` filtra pelo
  agente principal (prefixo, sem acento, caixa alta) contra
  `_TRANSMISSORAS`. Restam 17 SE no RN.
  - **Gotcha**: a SE Currais Novos II é de transmissão mas o ONS registra o
    agente como "LAGOA NOVA" (nome de SPE) — está em `_TRANSMISSORAS`.
    Santa Luzia II é da PB, não entra no filtro por `id_estado == "RN"`;
    vem de `bays.xlsx`. `_CHAVES_SEMPRE_MANTIDAS` cobre as SE curadas pelo
    cliente cujo agente não bate.
- **Nome da SE sem nível de tensão**: `nome_exibicao_subestacao()` converte
  a grafia do ONS (caixa alta e abreviada: `J. CAMARA III`, `CURR NOVOS
  II`, `CARAUBAS II`) em `SE João Câmara III`, via `_NOME_EXIBICAO_SE`. A
  tensão saiu do nome e aparece só na ficha.
- **Linhas de conexão** conjunto→subestação são desenhadas sempre (fixas,
  não só ao clicar/selecionar), estilo neutro, sem diferenciação por nível
  de tensão ainda (falta dado de kV por subestação — próxima melhoria).
- **Ficha de detalhe do conjunto** (ordem definida pelo usuário): nome ·
  municípios · Agente(s) Proprietário(s) e Operador(es), **todos** com
  logomarca (§2.5) · capacidade instalada · qtd. aerogeradores · ponto de
  conexão (`SE <nome>`) · **energia frustrada acumulada** nas 5
  metodologias (MWh) · **impacto financeiro acumulado** nas 5 (R$) ·
  **documentos associados** com link (§4.5). Os acumulados vêm de
  `core/coff_cache.py` restritos aos meses consolidados — ver §4.4.
- **Mapa mostra só o RN**: polígono do mundo com um "furo" no formato do RN
  (`_mascara_fora_rn()`), pintado branco por cima do basemap.
- **Gotcha do buffer**: `shapely.buffer(0.06)` no polígono do RN antes de
  usar como furo — ~6km de folga pra não cortar rótulos de município do
  basemap perto da fronteira.
- **Gotcha do `max_bounds`**: precisa passar `min_lat/max_lat/min_lon/max_lon`
  explícitos — sozinho não trava o pan. Bounds em `_BOUNDS_RN`.
- **Basemap: Esri "World Light Gray Base"** — URL/attr em constantes
  `ESRI_TILES_URL` / `ESRI_TILES_ATTR` (`viz/map_charts.py`), compartilhadas
  com o mapa estático. Estilo claro/minimalista equivalente ao antigo
  `CartoDB positron` — trocado porque o positron da Carto passou a exigir
  API key e a estampar "API KEY REQUIRED" nos tiles. Os tiles da Esri são
  servidos sem key e sem marca d'água.
- **Ícones escalam com o zoom**: os marcadores de SE e conjunto são
  `folium.DivIcon` (fundo PNG numa `div.marcador-escala`), não `CustomIcon`.
  `_script_escala_icones()` injeta um `<script>` que acha o objeto do mapa
  (`window` → `map_*` instanceof `L.Map`), escuta `zoomend` e aplica
  `transform: scale()` (teto 2,6×) na div interna — sem colidir com o
  `translate3d` de posicionamento do Leaflet. `z_index_offset=1000` nos
  marcadores + `.leaflet-marker-pane{z-index:640}` mantêm o ícone acima das
  linhas. Marcador de conjunto tem tamanho fixo (`_TAMANHO_ICONE_CONJUNTO`),
  sem proporcionalidade à qtd. de usinas.
- **Prefixo `SE `**: `_nome_subestacao()` garante `SE <nome>` no tooltip e
  popup das subestações (idempotente).

### 3.1 Mapa estático (PNG) — `viz/mapa_estatico.py`

`gerar_png_mapa(...)` reproduz um subconjunto das camadas do mapa
interativo com `staticmap` (baixa os mesmos tiles Esri, desenha
linhas/marcadores em PIL, sem navegador). Legenda de tensão e crédito dos
tiles desenhados via `ImageDraw`. `gerar_png_mapa_cache(...)` é a versão
`@st.cache_data` (DataFrames como JSON, igual a `build_map_html`). Usos:
botão "baixar imagem do mapa" (`ui/mapa.py`, sob demanda — só no clique) e
mini-mapa recortado por conjunto no relatório PDF (`zoom`/`centro`
explícitos). Ícones tingidos escritos em PNG temporário (staticmap
`IconMarker` exige caminho em disco), cache por (arquivo, cor, tamanho).

---

## 4. Energia Frustrada — metodologias

As 5 fórmulas (+ 2 gerações de referência calculadas auxiliares) foram
extraídas diretamente das fórmulas Excel de uma planilha de referência do
usuário (`openpyxl`, coluna a coluna) e reimplementadas vetorizado em
`core/ons_coff.py::calcular_metodologias()`. **Validado linha a linha**
contra os valores calculados em cache da planilha original (80.352 linhas,
RN, julho/2026): 99,99% de correspondência exata; a fração residual
(~0,01–0,02% das linhas) são empates de ponto flutuante bem em cima da
fronteira da tolerância de 5 MW/5%, onde o motor de fórmulas do Excel não
é perfeitamente reprodutível em IEEE754 puro — ver comentário no código.

**Bug de tradução já corrigido**: a Metodologia 5 (`energia_frustrada_5`)
**não tem** a guarda "zera se G_Ref_Final Calculada < geração" que a
Metodologia 4 tem — são assimétricas na planilha original. Não "arrumar"
isso achando que é inconsistência; é assim mesmo.

Colunas resultantes: `energia_frustrada_1..5`, `g_ref_calculada_1/2`.
Impacto financeiro = `energia_frustrada_N * pld_horario`, onde
`pld_horario` é o PLD horário NE da CCEE (ver §2.4); se o PLD não estiver
disponível para o período, o impacto financeiro é omitido.

### 4.1 Metodologia [1] é a de referência

`METODOLOGIA_PADRAO = 1` em `core/ons_coff.py`, pré-selecionada no seletor
e rotulada "(referência)". Ela reproduz **exatamente** os totais do estudo
de referência do cliente (conferido junto a uma empresa especializada) —
validado mês a mês, Baixa do Feijão em 2024: 151,37 / 569,89 / 345,58 /
16,41 / 629,49 / 1017,10 / 756,33 / 622,01 / 1623,23 / 2025,81 / 859,03 /
721,20 MWh. As outras 4 seguem no seletor para comparação metodológica.

**Não implementar a fórmula da planilha `Perdas_PLD-*.xlsx` do cliente**
(`=(IF(G<E,0,G-E))/2`, isto é `val_geracaoreferenciafinal −
val_geracaolimitada`): ela está **quebrada**. `val_geracaoreferenciafinal`
vem vazia em ~98% das linhas do ONS (1.937 de 83.520 em set/2024), o Excel
trata vazio como 0, e o resultado é zero em quase tudo — conferido, dá
0,00 MWh onde o BI mostra 16,41. O `Valor_Corte` que alimenta o Power BI
do cliente **não** vem dessa coluna; equivale à Metodologia [1].

**Gotcha de unidade** (`core/relatorio_dados.py`): as colunas
`energia_frustrada_*` já saem em **MWh** (o fator 0,5 h está embutido na
fórmula `0.5·(ref−lim)`). Mas `val_geracao`/`val_geracaoreferencia`/
`val_geracaolimitada` são **MW médios** por amostra — para virar MWh,
multiplicar pelo intervalo real da amostra (`_intervalo_horas()` → 0,5 h
no passo semi-horário do ONS). Sem isso, geração e fator de capacidade
saem ~2× inflados.

### 4.2 Relatório PDF — `core/relatorio_dados.py` + `viz/pdf_relatorio.py`

`montar_relatorio(conjuntos, ano, mes, metodologia_ref)` (`@st.cache_data`)
compila um `Relatorio`: um `DossieConjunto` por conjunto (cadastro, usinas
membras via SIGA, SE de conexão com tensão/agente, linhas de transmissão
que tocam a(s) SE, `coff_mensal` já com as 5 metodologias + PLD, agregados
— geração verificada/referência/limitada, fator de capacidade, % da
geração potencial frustrada, quebra por `cod_razaorestricao` — e série
diária) + `resumo_rn` (agregado do estado, ranking dos conjuntos por
corte). `conjuntos` vazio = todos.

`gerar_pdf(rel, mapas_por_conjunto)` monta o PDF (ReportLab; gráficos em
matplotlib `Agg` na paleta do painel): capa, sumário executivo do RN, uma
seção por conjunto (cadastro + mini-mapa recortado, conexão à rede,
tabela/gráficos de constrained-off, curva de duração do corte, anexo de
usinas). `mapas_por_conjunto` (`conjunto → PNG`) vem de
`viz.mapa_estatico.gerar_png_mapa` com `zoom`/`centro` do conjunto; opcional.

UI: bloco "Exportar relatório PDF" em `ui/energia_frustrada.py` — geração
sob demanda (botão), resultado em `st.session_state` para o
`st.download_button`.

---

### 4.3 Painel de Preço Horário — `ui/painel_pld.py`

Página inspirada no Painel de Preços da CCEE
(https://www.ccee.org.br/precos/painel-precos): PLD da hora corrente em
destaque (com delta vs. hora anterior), curva Plotly das 24 h do dia,
métricas de máxima/mínima/média com a hora de cada extremo, e evolução
recente (média diária + faixa mín–máx) em janelas de 30 a 365 dias.

- Seletor **Ontem / Hoje / Amanhã** — o PLD é publicado com um dia de
  antecedência, então "Amanhã" costuma existir; só entram no seletor os
  dias efetivamente presentes na série.
- Reaproveita `core/ccee_pld.baixar_pld_nordeste`, então o preço exibido é
  o mesmo usado no impacto financeiro da Energia Frustrada.
- Conferido contra o painel da CCEE (02/09/2026, NE): máxima 1.292,46,
  mínima 57,31, média 212,81 R$/MWh.

---

### 4.4 Cache em disco do COFF agregado — `core/coff_cache.py`

Compor o acumulado de um ano exigia baixar um CSV do ONS por mês (o arquivo
cobre o Brasil inteiro, dezenas de MB) — minutos no primeiro acesso, custo
que o `@st.cache_data` não evita entre reinícios (frequentes no Streamlit
Community Cloud).

Como o CSV de um mês fechado é imutável, o **agregado por conjunto** daquele
mês também é. Fica persistido em `data/cache_coff/coff_{ano}_{mes:02d}.parquet`
(54 linhas/mês, ~9 KB, versionado no repositório). Não são persistidos os
dados semi-horários brutos nem os meses ainda em revisão.

- **`_DIAS_ATE_CONSOLIDAR = 15`**: um mês só vai para o disco 15 dias após
  encerrar — o ONS revisa medições e a CCEE reprocessa o PLD nesse intervalo.
  Antes disso é recalculado ao vivo (cache de sessão), sem gravar.
- **`somente_consolidados=True`** (usado pela ficha do mapa) restringe a soma
  ao que está em disco: **0,8 s** contra **65 s** quando o mês corrente e o
  recém-encerrado entram ao vivo. A página Energia Frustrada segue mostrando
  o mês corrente ao vivo.
- **Por que gravar o impacto financeiro junto, e não só os MWh**: o impacto
  tem de ser somado hora a hora (`energia × PLD daquela hora`). A energia
  frustrada se concentra nas horas de PLD baixo, então recompor depois pelo
  PLD médio superestimaria — o produto das médias não é a média dos produtos.
- **`VERSAO_AGREGADO`**: gravada no metadata de cada Parquet. **Ao mudar as
  fórmulas de `calcular_metodologias()` ou a aplicação do PLD, incrementar** —
  os arquivos de versão anterior passam a ser ignorados e recalculados, em
  vez de servir número desatualizado indefinidamente.
- O cache se preenche sozinho conforme o painel é usado;
  `python scripts/atualizar_cache_coff.py [ano]` apenas pré-aquece antes de
  um deploy.
- **`attrs` não sobrevive ao `@st.cache_data`** — por isso os meses efetivamente
  somados voltam como segundo elemento da tupla, não em `DataFrame.attrs`.
- **Validação**: jan/2026 dá 831.132,72 MWh tanto pelo cache quanto pelo
  caminho da página Energia Frustrada (diferença de 2e-10); Baixa do Feijão
  2024 reproduz mês a mês a série de referência do §4.1.

### 4.5 Documentos do ONS por conjunto — `core/documentos_ons.py`

O `Ajustamento Operativo` da planilha (`AO-CE.NE.2LE`, 50 conjuntos;
`AO-CE.NE.2NO`, 4) vira link para o PDF no MPO do ONS.

**Gotcha da revisão no nome do arquivo**: o ONS publica com a revisão
embutida (`AO-CE.NE.2LE_Rev.32.pdf`) e **remove a anterior** ao publicar uma
nova — URL fixa devolve 404 em poucos meses (foi o que aconteceu com a
Rev.17 do 2NO, hoje na Rev.20). A revisão vigente é descoberta por sondagem
`HEAD`, tentando primeiro a `revisao_conhecida` e depois as posteriores
(cache de 24 h). Se nenhuma responder, o link cai na página de busca do MPO,
que nunca quebra. Convém atualizar `revisao_conhecida` de tempos em tempos
para a sondagem seguir barata (~0,3 s).

---

## 5. Design

Painel é pra **trabalho de mestrado** — usuário rejeitou o visual padrão
"genérico" do Streamlit e pediu algo sério/minimalista:
- Tema neutro em `.streamlit/config.toml` (paleta slate `#3b5166` +
  terracota `#c17a4f`, sem cores vivas de dashboard). Subestação usa um
  terceiro tom neutro (`#5b6b74`) pra não colidir com usinas individuais.
- Tipografia serif (Georgia) nos headers, injetada via CSS em `app.py`.
- `#MainMenu`/`footer` do Streamlit escondidos.
- CSS responsivo básico pras métricas da sidebar não espremerem no mobile.

---

## 6. Git / Deploy

- Identidade git é **local a este repo**: `user.name "Daniel Nascimento"` /
  `user.email marcos.danielns@outlook.com`.
- Push feito via `gh` CLI logado como conta **Kevinael** (colaborador
  adicionado pelo Daniel, dono do repo).
- **Streamlit Community Cloud**: deploy ativo, atualiza sozinho a cada push
  na `main`. **O site publicado é o GitHub, não a máquina local** — commit
  sem push não muda nada no painel público (já custou uma sessão inteira
  investigando um valor "errado" que era só código não enviado).
- **Série de PLD**: mantida em dia sozinha pelo workflow semanal
  `.github/workflows/atualizar-pld.yml` (§2.4). Rodar
  `python scripts/atualizar_pld_local.py` à mão só antes de um deploy
  urgente com dados recém-publicados.
- **`gh` CLI**: instalado via `winget install GitHub.cli`, em
  `C:\Program Files\GitHub CLI\gh.exe`. Autenticado como
  **Daniel-Nascimento-EOL**. Terminal aberto antes da instalação não vê o
  binário no PATH — usar o caminho completo ou reabrir o terminal.
- **Ambiente local Windows**: o Python 3.12 usado originalmente pro `.venv`
  foi desinstalado da máquina em algum momento (venv órfão, "No Python at
  ..."). Recriado com `py -3.13 -m venv .venv`. Se o `.venv` quebrar de
  novo com erro parecido, checar `py -0p` pras versões disponíveis antes
  de tentar consertar o venv antigo.

---

## 7. Roadmap — pendências

Já implementados: ficha de detalhe de conjunto, energia frustrada, linhas
fixas conjunto↔subestação, **linhas coloridas por nível de tensão** (kV do
cadastro ONS de subestações/linhas), **download PNG do mapa**,
**relatório PDF consolidado de constrained-off por conjunto**,
**impacto financeiro pelo PLD real da CCEE**, **painel de preço horário**,
**logomarcas oficiais dos agentes**, **filtro de subestações de transmissão**,
**acumulados de energia frustrada e impacto financeiro na ficha** e
**link para os documentos do MPO** — ver §3, §3.1, §2.4, §2.5, §4, §4.2,
§4.3, §4.4 e §4.5.

Ainda não resolvidos:

1. **Ficha de detalhe da subestação** com documentos vinculados — o popup da
   SE já traz nome, níveis de tensão e agente; falta a ficha completa com os
   PDFs de instrução de operação (não recebidos).
2. **Domínio próprio e host definitivo**: o Streamlit Community Cloud não
   aceita domínio custom. Para publicar com URL própria, migrar para Render
   (domínio grátis, US$ 7/mês sem hibernação) ou Fly.io (região `gru`, IP
   brasileiro). Registrar o domínio em Registro.br ou Cloudflare.

Fontes de dados abertos levantadas (ONS constrained-off, ANEEL SIGA,
COSERN) em `docs/fontes_dados_abertos.md`.

---

## 8. Convenções

- Idioma: português técnico formal (mensagens, commits, documentação).
- Commits: sem `Co-Authored-By`, formato `tipo: descrição curta`, **um
  commit por etapa** (dados/loader → mapa/UI → motor de cálculo →
  navegação), não um commit gigante no final.
- Ambiente isolado em `.venv/` (gitignored, Python 3.13), `requirements.txt`
  versionado.
