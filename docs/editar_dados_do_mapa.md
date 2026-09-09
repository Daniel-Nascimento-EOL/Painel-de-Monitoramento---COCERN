# Como editar e inserir dados do mapa

O painel **não baixa nada em tempo de execução** e **não edita nada**. Tudo
o que o mapa desenha sai de arquivos versionados em `data/`; a edição é
sempre manual, no arquivo, seguida de `commit`. Este documento descreve cada
arquivo, o que cada coluna significa e como alterá-lo à mão ou (para as
tabelas de rede) pelo script de atualização. A página "Dados do mapa" no
painel serve só para conferir o que está em vigor e exportar.

## Visão geral

| Arquivo | Conteúdo | Como atualizar |
|---|---|---|
| `data/localizacao_conjuntos_ons_aneel.xlsx` | conjuntos eólicos e usinas individuais | à mão (Excel) |
| `data/bays.xlsx` | subestações do RN/PB e cidades de referência | à mão (Excel) |
| `data/rn_estado.geojson` | contorno do estado (máscara branca) | raramente muda — IBGE |
| `data/rede/subestacoes_rn.csv` | SE de transmissão do RN + nível de tensão (kV) | `scripts/atualizar_dados_mapa.py --ses` |
| `data/rede/linhas_transmissao_rn.csv` | linhas da Rede de Operação que tocam o RN | `scripts/atualizar_dados_mapa.py --linhas` |
| `data/rede/siga_potencias_eol_rn.csv` | potência por CEG das eólicas do RN | `scripts/atualizar_dados_mapa.py --siga` |
| `data/cache_coff/coff_AAAA_MM.parquet` | energia frustrada + impacto financeiro por conjunto/mês | `scripts/atualizar_cache_coff.py` |
| `data/historico_pld_ne.csv` | PLD horário NE (série histórica) | `scripts/atualizar_pld_local.py` |

Regra de ouro: **depois de editar, confira com `git diff` e faça um commit**
com mensagem no formato `tipo: descrição curta`. O site publicado é o do
GitHub — alteração sem `push` não muda o painel público.

---

## 1. Conjuntos eólicos — `localizacao_conjuntos_ons_aneel.xlsx`, aba `Localizacao`

Uma linha por conjunto (54 hoje). É a fonte do marcador de turbina no mapa,
da ficha de detalhe e dos filtros.

| Coluna | Formato | Observação |
|---|---|---|
| `Conjunto` | texto | ex.: `Conjunto Eólico Acauã`. Usado como rótulo e na junção com a aba `Detalhamento` (a junção tolera `CONJ. ACAUÃ`). |
| `id_ons` | texto | chave de junção com o constrained-off do ONS. **Não inventar** — tem de bater com o dataset do ONS. |
| `Localização (lat, long)` | `"-6.08, -36.65"` | latitude e longitude separadas por vírgula, ponto decimal. É daqui que sai a posição no mapa. |
| `Município(s)` | texto | vários municípios separados por `;`. |
| `Capacidade instalada` | `"109,20 MW"` | vírgula decimal, sufixo ` MW`. O parser tolera espaços soltos (`63 ,00MW`). |
| `Qtd. usinas` | inteiro | |
| `Qtde. aerogeradores` | inteiro | |
| `Ponto de conexão` | `"SE Açu II"` | tem de casar com a coluna `Subestação` de `bays.xlsx` (o prefixo `SE ` é ignorado na junção). É o que liga a linha de conexão conjunto→SE. |
| `Agente Proprietário` / `Agente Operador` | texto | co-propriedade separada por ` / ` (ex.: `Voltalia / Copel / Toda`). Cada nome puxa a logomarca de `data/icons/agentes/` (ver `core/agentes.py`). |
| `Ajustamento Operativo` | `AO-CE.NE.2LE` | vira link para o PDF do MPO do ONS. |
| `Logo - Agente *` | — | **colunas mortas.** Não são mais lidas. Ignorar. |

### Inserir um conjunto novo

1. Acrescente uma linha na aba `Localizacao` preenchendo ao menos
   `Conjunto`, `id_ons`, `Localização (lat, long)`, `Município(s)`,
   `Capacidade instalada`, `Qtd. usinas`, `Qtde. aerogeradores`,
   `Ponto de conexão`, `Agente Proprietário`, `Agente Operador`.
2. Se o ponto de conexão for uma subestação ainda não listada, adicione-a
   também em `bays.xlsx` (seção 3).
3. Opcional: acrescente as usinas do conjunto na aba `Detalhamento`.
4. Se um agente novo entrar, rode `python scripts/baixar_logos_agentes.py`
   e confira a logomarca (ver o "gotcha do domínio" no `CLAUDE.md`).
5. `git diff`, depois `git add` e commit.

### Conferir depois de editar

Abra a página "Dados do mapa" no painel (localmente, `streamlit run app.py`)
e confira a tabela "Conjuntos eólicos": linhas com coordenada fora do RN são
destacadas em um aviso no topo do bloco. Baixe também
`pontos_mapa.geojson` para checar a posição contra satélite (seção 7).

---

## 2. Usinas individuais — aba `Detalhamento`

Uma linha por usina (309 hoje). Alimenta a camada opcional "Usinas
individuais" e o anexo do relatório PDF.

| Coluna | Observação |
|---|---|
| `Conjunto` | ex.: `CONJ. ACAUÃ`. Junta com a aba `Localizacao`. |
| `Usina integrante` | nome da usina. |
| `CEG` | ex.: `EOL.CV.RN.028444-0.1`. Chave de junção com o SIGA (potência). |
| `Latitude` / `Longitude` | colunas separadas (ao contrário da aba `Localizacao`). |
| `Município(s)` | |
| `Fonte coordenada` | proveniência da coordenada — preencher ao inserir. |
| `Observação` | livre. |

Editar na planilha (a página "Dados do mapa" só exibe).

---

## 3. Subestações e cidades — `bays.xlsx`

### Aba `Bays` (15 linhas, RN + PB)

Marcador de subestação e ponta das linhas de conexão.

| Coluna | Observação |
|---|---|
| `id_estado` | `RN` ou `PB`. O filtro do mapa por `id_estado == "RN"` não pega as da PB — elas entram por estarem aqui. |
| `Agente Operador` | texto. |
| `Subestação` | ex.: `Açu II`. Casa com `Ponto de conexão` dos conjuntos (o prefixo `SE ` é ignorado na junção; numeral romano ⇄ arábico é normalizado). |
| `latitude` / `longitude` | ponto decimal. |

As colunas de tensão que aparecem na página vêm de
`data/rede/subestacoes_rn.csv` (seção 5), não desta planilha.

### Aba `Cidades_RN` (21 linhas)

Rótulos fixos no mapa, sem interação.

| Coluna | Observação |
|---|---|
| `Cidade` | texto exibido. |
| `Latitude` / `Longitude` | ponto decimal. |

Editar nas abas da planilha; a página "Dados do mapa" só exibe e sinaliza
coordenada fora do RN.

---

## 4. Contorno do estado — `rn_estado.geojson`

Polígono do RN (IBGE), usado para recortar o mapa (máscara branca fora do
estado). Praticamente nunca muda. Se precisar trocar, baixe o novo contorno
do IBGE e substitua o arquivo mantendo o mesmo nome; o formato esperado é um
`FeatureCollection` com uma única `Feature` de geometria `Polygon` ou
`MultiPolygon`.

---

## 5. Tabelas de rede — `data/rede/*.csv`

Geradas a partir dos cadastros abertos do ONS e da ANEEL pelo script
`scripts/atualizar_dados_mapa.py`. São texto simples (CSV, UTF-8 com BOM) e
podem ser abertas no Excel ou num editor de texto.

### `subestacoes_rn.csv`

Uma linha por SE de transmissão do RN (17 hoje).

| Coluna | Observação |
|---|---|
| `chave_subestacao` | nome normalizado (sem acento, romano→arábico) — junta com `bays.xlsx`. |
| `nom_subestacao` | grafia do ONS. |
| `agente_principal` | usado para separar transmissão de coletora de usina. |
| `latitude` / `longitude` | |
| `tensao_max_kv` | maior nível de tensão da SE. |
| `tensoes_kv` | lista dos níveis, separada por `;` (ex.: `138;230`). |
| `nome_exibicao` | como o painel escreve o nome (ex.: `SE João Câmara III`). |

### `linhas_transmissao_rn.csv`

Linhas da Rede de Operação que tocam o RN (63 hoje). Sem geometria.

| Coluna | Observação |
|---|---|
| `subestacao_de` / `subestacao_para` | terminais. |
| `chave_de` / `chave_para` | normalizados, para casar com as SE. |
| `tensao_kv` | nível de tensão. |
| `tipo_rede` | ex.: `Básica`. |
| `comprimento_km` | |
| `agente` | proprietário da linha. |

### `siga_potencias_eol_rn.csv`

Potência por CEG das eólicas do RN (375 linhas hoje).

| Coluna | Observação |
|---|---|
| `ceg` | chave de junção com a aba `Detalhamento`. |
| `potencia_outorgada_mw` / `potencia_fiscalizada_mw` | em MW. |
| `fase_usina` | ex.: `Operação`. |
| `proprietario` | |

### Regenerar

```
python scripts/atualizar_dados_mapa.py            # as três
python scripts/atualizar_dados_mapa.py --ses      # só as subestações
python scripts/atualizar_dados_mapa.py --linhas
python scripts/atualizar_dados_mapa.py --siga
```

O script valida cada tabela (contagem mínima, coordenada dentro do RN,
colunas-chave presentes) e **só grava se passar**. Se uma fonte estiver
fora do ar, as outras ainda são atualizadas e o arquivo da que falhou fica
intacto. Ao final, confira `git diff data/rede/` e faça o commit.

### Correção pontual

Para corrigir uma linha específica (uma coordenada errada, um nome), edite
o CSV direto num editor de texto ou no Excel e commite. **Atenção:** a
próxima execução do script sobrescreve o arquivo inteiro. Correções que
precisam sobreviver a isso têm de ser levadas à fonte (ONS/ANEEL) ou
tratadas no código de `core/fontes_online.py`.

---

## 6. Energia frustrada e PLD

Fora do escopo do mapa, mas alimentam a ficha do conjunto e as outras
páginas:

- `data/cache_coff/coff_AAAA_MM.parquet` — agregado mensal de energia
  frustrada e impacto financeiro por conjunto. Um mês só é gravado 15 dias
  após encerrar (o ONS revisa medições). Regenerar:
  `python scripts/atualizar_cache_coff.py [ano]`. Ao mudar as fórmulas em
  `core/ons_coff.py`, incrementar `VERSAO_AGREGADO` em `core/coff_cache.py`.
- `data/historico_pld_ne.csv` — série do PLD horário NE. Mantida por
  `scripts/atualizar_pld_local.py` e pelo workflow semanal
  `.github/workflows/atualizar-pld.yml`.

---

## 7. Conferir as posições contra satélite

1. Na página "Dados do mapa", baixe `pontos_mapa.geojson` (ou use o
   versionado em `docs/pontos_mapa.geojson`).
2. Abra no **Google Earth Pro** (grátis) ou no **QGIS**.
3. Sobrevoe cada ponto: um parque eólico e o pátio de uma subestação são
   identificáveis na imagem de satélite.
4. Alternativa rápida dentro do painel: no mapa, ligue a camada
   **"Satélite"** no seletor do canto — os marcadores ganham halo branco
   para leitura sobre a imagem.
5. Achou um ponto fora do lugar? Corrija a coordenada na planilha/CSV
   correspondente (seções 1, 3 ou 5) e regenere o GeoJSON com
   `python scripts/gerar_geojson_auditoria.py`.
