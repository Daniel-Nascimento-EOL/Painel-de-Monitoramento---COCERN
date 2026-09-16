# Mapeamento completo de features — Painel COCERN (Constrained-off RN)

> Levantamento exaustivo de todas as páginas, filtros, métricas, gráficos,
> dados exibidos e decisões de design do painel, feito para servir de
> checklist de inspiração na construção de outro painel. Gerado em
> 2026-09-13 por leitura direta do código-fonte (não do `CLAUDE.md`, que
> estava desatualizado em vários pontos — ver nota abaixo).

## Divergências encontradas em relação ao `CLAUDE.md` do repositório

- Existe uma **tela de apresentação/capa** (`ui/apresentacao.py`) não documentada no CLAUDE.md.
- Existe um **alternador de tema claro/escuro** (`core/tema.py`) que repinta toda a interface e o mapa — não documentado.
- A página **"Dados do mapa"** (`ui/dados.py`) foi **removida da navegação**; sobrevive só para alimentar `scripts/gerar_geojson_auditoria.py`.
- O mapa usa **`st_folium`** com clique real capturado (não mais `components.v1.html` one-way); a ficha de detalhe virou **card HTML na coluna lateral do Streamlit**, não popup do Leaflet.
- Existe uma **Metodologia [6]** de energia frustrada (`val_geracaonaorealizadaapurada`, direto do ONS, só a partir de 2024).
- Documentos do MPO/ONS agora vêm de um **CSV espelhado** (`data/documentos_ons.csv`), não mais sondagem web em tempo real.
- Navegação final: só 3 páginas — **Mapa · Energia Frustrada · Preço Horário (PLD)**.

---

## 1. Estrutura geral (`app.py`)

- `page_title="COCERN — Constrained-off dos Conjuntos Eólicos do RN"`, ícone 🌬️, `layout="wide"`, sidebar expandida por padrão.
- CSS global: esconde menu/rodapé do Streamlit; headers em serif (Georgia/Times New Roman); métricas maiores; responsivo em `max-width:640px`.
- **Tela de apresentação bloqueante**: se ainda não vista na sessão, mostra a capa e chama `st.stop()` — nada do painel renderiza até o usuário confirmar entrada.
- Sidebar: título, botão "Tela inicial" (volta à capa), navegação por `st.sidebar.radio` (3 opções), **toggle de tema escuro**.
- Roteamento simples por `if/elif` para as 3 páginas.

### Tela de apresentação (`ui/apresentacao.py`)

- Fundo de imagem gerada (`data/icons/capa_rn.png`) com gradiente escuro sobreposto.
- Sigla grande em serif + régua decorativa colorida + título por extenso.
- **6 métricas de resumo institucional** calculadas ao vivo dos dados cadastrais:
  1. Capacidade instalada total (MW)
  2. Total de usinas
  3. Total de aerogeradores
  4. Municípios atendidos (contagem única)
  5. Agentes proprietários únicos
  6. Agentes operadores únicos
- Botão "Entrar no painel" grava flag de sessão e avança.
- CSS escopado (não vaza para as páginas internas, que ficam sempre no tema claro por padrão).
- Responsivo (grid de métricas cai para 2 colunas no mobile).

**Ideia reaproveitável**: uma landing/capa institucional com números-chave do domínio antes de entrar no dashboard operacional é um padrão forte para pautar a escala do problema logo de cara.

### Alternador de tema claro/escuro (`core/tema.py`)

- Paleta completa dupla (claro/escuro) cobrindo cada elemento visual do mapa: tiles do basemap, cor de conjuntos/usinas/subestações, contorno, cidades, linhas de conexão, máscara, texto e fundo da ficha, legenda.
- Ajuste específico de contraste (cor de 138 kV muda de preto para cinza claro no escuro, senão some).
- Função utilitária que adapta qualquer gráfico Plotly ao tema ativo (fundo transparente, cor de fonte/grade).
- CSS que repinta manualmente componentes nativos do Streamlit (sidebar, inputs, botões, dataframes) — necessário porque o Streamlit não tem alternância de tema dinâmica nativa via `config.toml`.

**Ideia reaproveitável**: dark mode completo, incluindo o mapa (basemap dedicado) e os gráficos, não só o CSS da shell.

---

## 2. Página Mapa

### Filtros (sidebar)

1. Município (multiselect)
2. Agente Proprietário (multiselect, com suporte a co-propriedade "A / B / C")
3. Agente Operador (multiselect)
4. Busca textual por nome do conjunto
5. **Camadas do mapa** — 6 checkboxes independentes:
   - Conjuntos eólicos (ligado)
   - Usinas individuais (desligado)
   - Subestações (ligado)
   - Linhas de transmissão (ligado)
   - Linhas de conexão conjunto→SE (ligado)
   - Cidades de referência (ligado)

### Métricas de resumo (sidebar)

4 cards: Conjuntos (contagem filtrada), Usinas (soma), Municípios (contagem única), Capacidade (soma em MW).

### Mapa interativo (Folium/Leaflet via `st_folium`)

- Layout em 2 colunas: mapa (larga) + ficha de detalhe (estreita), largura de página ampliada só nesta página.
- Clique num marcador de conjunto atualiza a ficha lateral (captura real de clique, não popup).
- Basemap Esri "World Light/Dark Gray Base" (sem API key), conforme tema ativo.
- **Camada de satélite opcional** (Esri "World Imagery") ativável por `LayerControl`.
- **Máscara "só o estado"**: polígono do mundo com um "furo" no formato do estado, escondendo tudo fora dele.
- Contorno do estado desenhado por cima.
- `max_bounds` trava o pan à região de interesse; zoom mínimo travado.
- Ícones escalam com o nível de zoom (script customizado, não nativo do Leaflet).
- **Halo branco** nos ícones e rótulos quando a camada de satélite está ligada (senão somem no fundo de imagem de satélite).

### Camadas desenhadas

- Cidades de referência (marcador + rótulo sempre visível, fora dos filtros).
- Subestações (ícone customizado tingido na cor do tema).
- Conjuntos eólicos (ícone de turbina, tooltip com nome, sem popup — clique abre ficha lateral).
- Usinas individuais (opcional): ícone + popup com nome, conjunto-pai, potência, código de registro, município.
- Linhas de transmissão: coloridas por nível de tensão, popup com ficha da linha.
- Linhas de conexão conjunto→subestação: tracejadas, coloridas pela tensão de conexão do conjunto (cinza neutro se não cadastrada).
- **Legenda de tensão fixa** no canto: cores por nível de kV + diferenciação visual entre linha de transmissão (contínua) e linha de conexão (tracejada).

### Paleta de cor por tensão

Um valor de cor fixo por faixa de tensão (ex.: 69/138/230/500 kV cada um com sua cor), mais cinza neutro para "sem dado" — usado tanto nas linhas do mapa quanto na legenda.

### Ficha de detalhe do conjunto (card HTML na lateral)

Ordem de exibição definida propositalmente:
1. Nome
2. Município(s)
3. Agente(s) Proprietário(s) — com logomarca de cada um
4. Agente(s) Operador(es) — com logomarca de cada um
5. Capacidade instalada
6. Quantidade de aerogeradores
7. Ponto de conexão (nome da subestação)
8. Tensão de conexão (se cadastrada)
9. **Energia frustrada acumulada no ano** — metodologia de referência em destaque + demais recolhidas
10. **Impacto financeiro acumulado no ano** — mesma lógica
11. **Documentos associados** (links para PDFs oficiais, ou busca se não resolvido)

**Ideia reaproveitável**: ficha de detalhe por entidade que combina cadastro estático + métricas operacionais acumuladas + logomarcas dos responsáveis + documentos vinculados, tudo num só painel lateral acionado por clique no mapa.

### Tabela de apoio

Tabela completa dos itens do mapa (nome, município, quantidade, capacidade, ponto de conexão, agentes) num expander no rodapé — permite ver tudo sem precisar clicar item a item.

### Exportação de imagem do mapa

Botão que gera e disponibiliza download de uma versão **PNG estática** do mapa (mesmos filtros/camadas), sem depender de JavaScript/navegador — útil para relatórios e apresentações offline.

### Mapa estático (motor próprio, sem navegador)

- Sempre na paleta clara (mesmo com dark mode ativo — decisão deliberada para impressão).
- Desenha as mesmas camadas do mapa interativo (contorno, linhas, cidades, usinas, subestações, conjuntos) usando uma biblioteca de tiles estáticos.
- Legenda desenhada diretamente na imagem.
- Suporta zoom/centro customizados — usado para gerar mini-mapas recortados por item individual dentro de um PDF.

---

## 3. Página de Energia Frustrada (métrica operacional principal)

### Filtros

1. Mês de referência (seletor com apenas os meses realmente publicados pela fonte).
2. Conjunto (multiselect, vazio = todos).
3. **Metodologia de cálculo** (seletor com 6 opções, uma marcada como "referência" por padrão) + texto explicativo abaixo do seletor.

### As 6 metodologias de cálculo (todas em MWh)

1. Metodologia de referência/padrão.
2. Metodologia alternativa 2.
3. Metodologia alternativa 3.
4. Metodologia alternativa 4.
5. Metodologia alternativa 5.
6. Direto do valor de "geração não realizada apurada" publicado pela fonte de dados oficial (só disponível a partir de certo ano).

**Ideia reaproveitável**: expor múltiplas metodologias de cálculo lado a lado (com uma marcada como "oficial"/referência) em vez de esconder a lógica — permite comparação metodológica e auditoria, importante em contexto acadêmico/regulatório.

### Métricas principais

- Energia frustrada total no período (MWh), conforme metodologia escolhida.
- Impacto financeiro no período (R$) = energia × preço horário de mercado; mostra aviso se o preço não puder ser obtido, em vez de omitir silenciosamente.

### Gráficos

1. Ranking (barra horizontal) — top 20 por energia frustrada.
2. Série temporal diária (linha).
3. Classificação por razão da restrição (barra + tabela com contagem de amostras, horas e percentual do total).

### Exportação — Relatório PDF completo

- Seleção de quais itens incluir (padrão = filtro atual).
- Opção de incluir mini-mapa recortado por item (mais lento, opcional).
- Botão gera PDF e disponibiliza download nomeado com mês/metodologia.

### Estrutura do relatório PDF gerado

1. **Capa**: título, mês de referência, quantidade de itens, metodologia usada + descrição, data de geração, fontes de dados, avisos relevantes.
2. **Sumário executivo agregado**: tabela de indicadores gerais (itens com corte/total, capacidade total, geração verificada, energia frustrada, % de geração potencial perdida, impacto financeiro), tabela comparativa das 5 primeiras metodologias, gráfico de ranking.
3. **Uma seção detalhada por item** (quebra de página): ficha cadastral + mini-mapa, tabela de conexão à rede (subestação, tensão, linhas que a tocam), tabela de indicadores do mês (horas com corte, geração verificada/referência/limitada, fator de capacidade, % frustrada, preço médio), tabela comparativa das metodologias, 3 gráficos (comparativo de metodologias, série diária com eixo duplo, curva de duração do corte ordenada decrescente), tabela de corte por razão, anexo de subitens (usinas individuais).
4. Rodapé com nome do painel, data de geração e número de página em todas as páginas.

**Ideia reaproveitável**: relatório PDF "dossiê" por entidade dentro de um relatório maior — cadastro + mapa + métricas + gráficos + anexo, tudo compilado automaticamente, não montado à mão.

---

## 4. Painel de Preço Horário (mercado/referência externa)

### Seletores

- Dia: Ontem / Hoje / Amanhã (só aparecem os dias que existem de fato na série; fallback para o último dia publicado).
- Janela de evolução histórica: 30 / 90 / 180 / 365 dias.

### Métricas em destaque

1. Preço da hora atual (ou média do dia, se não for hoje) — card com **animação visual de alta/baixa** comparando com a atualização anterior.
2. Máxima do dia + hora do pico.
3. Mínima do dia + hora do vale.
4. Média do dia.

### "Ticker tape" (faixa de cotações rolante)

Faixa horizontal animada em loop contínuo mostrando o preço hora a hora do dia selecionado — visual inspirado em painéis de bolsa/mercado.

### Gráficos

1. Curva do dia (linha suavizada com preenchimento até zero, linha de média pontilhada, marcador na hora atual).
2. Evolução recente (média diária + faixa sombreada entre mínima e máxima da janela escolhida).

**Ideia reaproveitável**: painel de série de preço "estilo bolsa" com ticker animado e curva do dia + evolução multi-mês é reaproveitável para qualquer série temporal de preço/indicador externo que alimente cálculo financeiro do dashboard principal.

---

## 5. Dados de suporte / cadastro (usados internamente, aparecem via UI)

- **Cadastro de agentes com logomarca oficial**: cada agente (proprietário/operador) tem uma logomarca própria versionada localmente (não depende de link externo instável); agentes com marca de fundo claro recebem tratamento visual diferenciado (fundo escuro) para não sumirem.
- **Resolução de documentos oficiais por item**: cada item do cadastro pode ter um ou mais documentos associados (código → PDF), com fallback para busca se o link direto não puder ser resolvido.
- **Normalização de nomes de rede**: nomes de subestações/linhas vindos de fontes oficiais em formato abreviado/caixa alta são convertidos para nome de exibição legível.
- **Filtro semântico de subestações relevantes**: cadastro oficial mistura subestações de transmissão de fato com subestações "coletoras" de cada usina (que duplicariam marcadores) — filtradas por lista curada de agentes de transmissão.
- **Mesclagem de potência por código de registro**: dados de potência oficial (outorgada/fiscalizada) juntados ao cadastro de usinas individuais.

---

## 6. Estrutura de dados (fontes e formatos)

| Tipo de dado | Formato | Observação |
|---|---|---|
| Cadastro de itens principais (conjuntos/usinas) | Planilha Excel, múltiplas abas | Uma aba por nível de granularidade (agregado vs. individual) + aba de proveniência/metodologia |
| Cadastro de subestações e cidades de referência | Planilha Excel, múltiplas abas | Curadoria manual |
| Rede (subestações, linhas, potências) | CSV espelhado localmente | Gerado por script externo, promovido manualmente após validação — **painel não baixa nada de rede em tempo de execução** |
| Documentos oficiais | CSV espelhado localmente | Idem |
| Série de preço histórica | CSV, uma linha por hora, anos completos | Fallback offline quando a fonte ao vivo falha |
| Métrica operacional mensal agregada | Cache em formato colunar (Parquet), um arquivo por mês | Meses fechados e consolidados viram arquivo estático; mês corrente é recalculado ao vivo |
| Contorno geográfico do estado | GeoJSON | Baixado uma vez, versionado |
| Ícones/logomarcas | Imagens PNG/JPG locais | Tingidas dinamicamente na cor do tema em vez de manter várias variantes de cor salvas |
| Arte da capa | PNG gerado por script | Script separado de geração de arte, não editado à mão |

**Ideia reaproveitável central**: separar claramente "dados que mudam o tempo todo e precisam de download ao vivo com fallback" (preço de mercado, métrica operacional do mês corrente) de "dados de cadastro/rede que mudam raramente" (espelhados localmente, atualizados por script + aprovação manual, nunca baixados em tempo de execução pelo usuário final). Isso dá velocidade e resiliência ao painel público.

---

## 7. Sistema de design

### Paleta

- Cor principal: tom slate (azul-acinzentado escuro) — usada no elemento "principal" do domínio (ex. conjuntos/usinas).
- Cor de destaque: terracota — usada em elementos secundários e detalhes decorativos (régua da capa, ícone de usina individual).
- Cor neutra adicional para uma terceira categoria de elemento (subestações), evitando colisão visual com as duas cores principais.
- Verde/vermelho reservados exclusivamente para indicar alta/baixa no ticker de preço (não usados em mais nada, para não confundir com "bom/ruim" em outros contextos).
- Paleta fixa de cores por faixa de tensão/categoria técnica, com uma cor neutra dedicada para "sem dado".

### Tipografia

- Serif (Georgia/Times New Roman) para todos os headers e títulos — dá ar de relatório acadêmico/institucional, deliberadamente **não** o visual "genérico de dashboard".
- Sans-serif padrão do sistema para corpo de texto e dados.

### Tema

- Tema claro/escuro completo e alternável em tempo real, cobrindo também o mapa (basemap dedicado por tema) e os gráficos (função utilitária que adapta qualquer gráfico Plotly).
- Menu e rodapé nativos do framework escondidos — visual limpo, sem marca do framework aparente.
- Responsivo: grade de métricas cai para menos colunas em telas estreitas; fonte das métricas reduzida no mobile.

---

## 8. Lista consolidada de "features" para checklist de novo painel

- [ ] Tela de apresentação/capa com métricas-resumo do domínio antes do dashboard
- [ ] Toggle de tema claro/escuro cobrindo shell + mapa + gráficos
- [ ] Navegação simples por radio/sidebar entre poucas páginas focadas
- [ ] Mapa interativo com: filtros combináveis, camadas ligáveis independentes, legenda fixa, camada de satélite opcional, máscara de região de interesse, contorno geográfico, limite de pan/zoom, ícones customizados escaláveis por zoom
- [ ] Ficha de detalhe por entidade acionada por clique (cadastro + métricas acumuladas + logos + documentos)
- [ ] Export de imagem estática do mapa (PNG, sem depender de navegador/JS)
- [ ] Múltiplas metodologias de cálculo expostas lado a lado, com uma marcada como referência/oficial
- [ ] Relatório PDF completo gerado sob demanda (capa + sumário agregado + seção detalhada por entidade com mini-mapa + gráficos + anexo)
- [ ] Painel de série de preço/indicador externo estilo "bolsa" com ticker animado + curva do dia + histórico multi-janela
- [ ] Separação clara entre dados "ao vivo com fallback em cascata" vs. dados de cadastro "espelhados localmente e atualizados por script + aprovação manual"
- [ ] Cache de agregados mensais em formato colunar para meses fechados, recálculo ao vivo só do período corrente
- [ ] Cadastro de logomarcas/ícones oficiais versionado localmente (não depender de links externos instáveis)
- [ ] Paleta de cor consistente por categoria técnica (ex. nível de tensão) usada tanto no mapa quanto na legenda quanto nos gráficos
- [ ] Tipografia serif nos headers para tom institucional/acadêmico, diferenciando do visual padrão de dashboard genérico
- [ ] Responsividade básica (mobile) nas métricas e grids

---

## Arquivos-fonte de referência (neste repositório)

`app.py`, `ui/apresentacao.py`, `ui/mapa.py`, `ui/energia_frustrada.py`,
`ui/painel_pld.py`, `ui/dados.py` (órfão), `viz/map_charts.py`,
`viz/mapa_estatico.py`, `viz/pdf_relatorio.py`, `core/tema.py`,
`core/ons_coff.py`, `core/coff_cache.py`, `core/ccee_pld.py`,
`core/relatorio_dados.py`, `core/agentes.py`, `core/documentos_ons.py`,
`core/ons_rede.py`, `core/aneel_siga.py`, `core/data_loader.py`,
`core/formatos.py`, `.streamlit/config.toml`.
