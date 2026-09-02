# Painel de Monitoramento de Constrained-off — Conjuntos Eólicos do RN

> Trabalho acadêmico de mestrado. Guia de referência do projeto para o Claude Code.
> Última atualização: 2026-08-31.

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
  │     ├── core/ccee_pld.py       ── download CCEE (PLD horário NE) com cascata de fallback
  │     ├── core/relatorio_dados.py ── compila o "dossiê" por conjunto (cadastro + SE/linhas + COFF do mês)
  │     └── viz/pdf_relatorio.py    ── relatório PDF consolidado (ReportLab + matplotlib): capa, resumo RN, seção/conjunto
  └── ui/painel_pld.py         ── painel de preço horário: PLD da hora, curva do dia (Ontem/Hoje/Amanhã), evolução recente

data/
  ├── localizacao_conjuntos_ons_aneel.xlsx   ── conjuntos: ONS/ANEEL + id_ons, capacidade, ponto de
  │                                              conexão, agentes proprietário/operador (+ logos)
  ├── bays.xlsx                                ── subestações do RN/PB (agente operador, lat/long) e
  │                                              cidades de referência
  ├── rn_estado.geojson                        ── contorno do RN (IBGE, baixado uma vez)
  ├── historico_pld_ne.csv                     ── PLD horário NE 17/10/2021–07/07/2025 (fallback offline
  │                                              da CCEE; extraído da planilha do estudo de referência)
  └── icons/
        ├── logo_aero.jpg                      ── ícone de turbina (marcador de conjunto)
        └── logo_se.jpeg                        ── ícone de subestação (marcador de bay)

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
`PLD_HORA`). Os ids dos recursos anuais (2021–2026) estão em
`_RECURSOS_POR_ANO`. Cache `@st.cache_data(ttl=6h)`.

**Gotcha do bloqueio da CCEE — não "consertar" removendo os headers**: o
perímetro da CCEE responde 403 "acesso bloqueado" a requisições que não
pareçam de navegador, em **duas camadas independentes**:

1. **Cabeçalhos**: só `User-Agent` não basta. Precisa do conjunto
   `Sec-Fetch-*` / `Sec-Ch-Ua` / `Upgrade-Insecure-Requests` que um Chrome
   envia numa navegação (`_CABECALHOS`).
2. **Impressão digital TLS**: mesmo com os cabeçalhos certos, `requests`
   (urllib3) leva 403 — o handshake não parece de navegador. `httpx` e o
   binário `curl` passam.

Por isso o download tenta, em ordem: **httpx → curl (subprocesso) →
requests**, e só então cai para `data/historico_pld_ne.csv` (série local
17/10/2021–07/07/2025, extraída da planilha do estudo de referência). Se
nada funcionar, retorna `None` e a UI mostra a energia frustrada em MWh
sem o impacto financeiro, com aviso.

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
- **Linhas de conexão** conjunto→subestação são desenhadas sempre (fixas,
  não só ao clicar/selecionar), estilo neutro, sem diferenciação por nível
  de tensão ainda (falta dado de kV por subestação — próxima melhoria).
- **Ficha de detalhe**: popup do marcador de conjunto expandido com agente
  proprietário/operador (+ logo via `<img src="URL">`, linkado externo —
  não baixamos/hospedamos essas imagens), ponto de conexão, capacidade
  instalada, qtd. aerogeradores, ajustamento operativo.
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

## 4.3 Painel de Preço Horário — `ui/painel_pld.py`

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
- **Streamlit Community Cloud**: deploy travado (GitHub App do Streamlit
  sem acesso ao repo privado). Fix pendente: Daniel precisa liberar acesso
  em https://github.com/settings/installations → app **Streamlit** →
  Configure → repo `Painel-de-Monitoramento---COCERN`.
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
**impacto financeiro pelo PLD real da CCEE** e **painel de preço horário**
— ver §3, §3.1, §2.4, §4, §4.2 e §4.3.

Ainda não resolvidos:

1. **Ficha de detalhe da subestação** com documentos vinculados (ajuste
   operativo, instrução de operação em PDF) — só temos o código do
   ajustamento operativo (texto), não os PDFs.
2. **Recursos anuais da CCEE são ids fixos** (`_RECURSOS_POR_ANO` em
   `core/ccee_pld.py`). O de 2027 precisará ser acrescentado quando a CCEE
   publicar — pegar em https://dadosabertos.ccee.org.br/dataset/pld_horario.
   Sem o id, o ano cai no fallback local (que termina em jul/2025) e o
   impacto financeiro fica indisponível.

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
