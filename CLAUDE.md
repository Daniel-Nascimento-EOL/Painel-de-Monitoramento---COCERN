# Painel de Monitoramento de Constrained-off — Conjuntos Eólicos do RN

> Trabalho acadêmico de mestrado. Guia de referência do projeto para o Claude Code.
> Última atualização: 2026-08-22.

---

## 0. Visão Geral

Painel web (Streamlit) de monitoramento de **constrained-off** (corte de
geração por restrição operativa) dos conjuntos eólicos do Rio Grande do
Norte. Primeira entrega (concluída): mapa de localização interativo. Próximas
fases dependem de dados que um colega de trabalho do usuário (Daniel
Nascimento) ainda vai enviar.

- **Stack:** Python 3.x / Streamlit / Folium (mapa) / Plotly (gráficos
  futuros) / Pandas / Shapely
- **Repositório:** https://github.com/Daniel-Nascimento-EOL/Painel-de-Monitoramento---COCERN
  (privado, branch `main`)
- **Comando de execução:** `streamlit run app.py` (venv em `.venv/`)

---

## 1. Arquitetura

```
streamlit run app.py
        ↓
app.py              ── page_config, CSS global (tema minimalista), monta sidebar
  └── ui/mapa.py     ── página do mapa: filtros (sidebar), métricas, render do mapa
        ├── core/data_loader.py   ── carrega/normaliza abas do Excel (@st.cache_data)
        └── viz/map_charts.py     ── constrói o folium.Map (ícones, máscara, bounds)

data/
  ├── localizacao_conjuntos_ons_aneel.xlsx   ── fonte: planilha ONS/ANEEL (54 conjuntos, 309 usinas)
  └── rn_estado.geojson                       ── contorno do RN (IBGE, baixado uma vez)

docs/
  └── fontes_dados_abertos.md   ── levantamento de datasets ONS/ANEEL/COSERN úteis pra próximas fases
```

---

## 2. Dados

Planilha `data/localizacao_conjuntos_ons_aneel.xlsx`, 3 abas:
- **Localizacao** (54 linhas): conjunto, lat/long, município(s), qtd. usinas.
- **Detalhamento** (309 linhas): usina individual, **CEG** (chave ANEEL —
  útil pra cruzar com potência/geração no futuro), lat/long, município.
- **Fontes e metodologia**: proveniência (ONS SINMAPS, ONS conjunto↔usina,
  ANEEL SIGA).

**Gotcha de join**: os nomes de conjunto NÃO batem direto entre as duas
abas — `"Conjunto Eólico Acauã"` (Localizacao) vs `"CONJ. ACAUÃ"`
(Detalhamento). `core/data_loader.py::_chave_conjunto()` normaliza (strip de
prefixo + uppercase) pra juntar. Validado: 54/54 batem sem sobra.

---

## 3. Mapa (Folium) — decisões e gotchas técnicos

Trocado de Plotly pra **Folium/Leaflet** porque o usuário pediu ícone
customizado de aerogerador nos marcadores — Plotly `Scattermapbox` só
suporta símbolos customizados com estilo Mapbox GL pago/tokenizado (sem
ícone de turbina pronto no set deles). Folium usa `DivIcon` com SVG inline,
sem token.

- **Ícone**: `viz/map_charts.py::_icone_turbina()` — SVG inline (torre +
  rotor de 3 pás), cor por tipo de marcador.
- **Mapa mostra só o RN**: polígono do mundo inteiro com um "furo" no
  formato do RN (`_mascara_fora_rn()`), pintado branco por cima do basemap
  — não é só limitar zoom/pan, é recorte visual mesmo.
- **Gotcha do buffer**: a máscara encostando exatamente na fronteira cortava
  rótulos de município do basemap perto da linha (ex.: "Maxaranguape"
  virava "Maxaran"). Fix: `shapely.buffer(0.06)` no polígono do RN antes de
  usar como furo — dá ~6km de folga. O contorno exato (sem buffer) continua
  desenhado por cima como linha fina.
- **Gotcha do `max_bounds`**: `folium.Map(max_bounds=True)` **sozinho não
  faz nada** — sem passar `min_lat/max_lat/min_lon/max_lon` explícitos, o
  Folium usa o default (bounds do mundo inteiro), e o mapa fica livre pra
  arrastar mesmo com a flag True. Bounds do RN estão em `_BOUNDS_RN` em
  `viz/map_charts.py`.
- Basemap: `CartoDB positron` (sem token, cinza claro, minimalista).
- Render em `ui/mapa.py` via `streamlit_folium.st_folium`.

---

## 4. Design

Painel é pra **trabalho de mestrado** — usuário rejeitou o visual padrão
"genérico" do Streamlit e pediu algo sério/minimalista:
- Tema neutro em `.streamlit/config.toml` (paleta slate `#3b5166` +
  terracota `#c17a4f`, sem cores vivas de dashboard).
- Tipografia serif (Georgia) nos headers, injetada via CSS em `app.py`.
- `#MainMenu`/`footer` do Streamlit escondidos.
- Sidebar colapsável é nativa do Streamlit (não precisa implementar) —
  filtros agrupados em container com borda, resumo compacto.
- CSS responsivo básico pras métricas da sidebar não espremerem no mobile
  (`@media max-width: 640px` em `app.py`).

---

## 5. Git / Deploy

- Identidade git é **local a este repo** (não a global do usuário):
  `user.name "Daniel Nascimento"` / `user.email marcos.danielns@outlook.com`.
- Push feito via `gh` CLI logado como conta **Kevinael** (colaborador
  adicionado pelo Daniel, dono do repo).
- **Streamlit Community Cloud**: deploy travado (botão "Deploy" fica
  desabilitado sem erro visível) porque o GitHub App do Streamlit não tem
  acesso liberado ao repo privado. Fix pendente: Daniel precisa ir em
  https://github.com/settings/installations (logado como
  `Daniel-Nascimento-EOL`) → app **Streamlit** → Configure → liberar acesso
  ao repo `Painel-de-Monitoramento---COCERN`. Alternativa rápida: tornar o
  repo público temporariamente.

---

## 6. Roadmap — Fase 2 (aguardando planilha do Daniel)

Levantado via 3 áudios do WhatsApp transcritos em 2026-08-22 (faster-whisper
local, modelo `small`). **Nada disso foi implementado ainda** — decisão do
usuário foi esperar a planilha que o Daniel manda numa segunda-feira antes
de começar.

1. **Interação no mapa**: clique no marcador abre ficha de detalhe (não só
   hover/tooltip). Alternativa: dropdown de instalação com zoom automático.
2. **Ficha de detalhe por conjunto**: logo do agente proprietário + logo do
   agente operador (podem ser empresas diferentes), documentos vinculados
   (ajuste operativo, instrução de operação — PDFs), capacidade instalada,
   qtd. aerogeradores.
3. **Energia frustrada**: Daniel já implementou 4 metodologias de cálculo (a
   atual dos relatórios + 3 alternativas). Vem numa planilha preenchida
   junto com agente proprietário/operador e links de logo.
4. **Ponto de conexão / rede de transmissão**: cada conjunto conecta numa
   subestação via linha — desenhar linha conjunto↔subestação no mapa,
   colorida por nível de tensão (138kV preto, 230kV verde, 500kV vermelho).
   Subestação também clicável (agente dono, nível de tensão). Exemplos RN
   citados: João Câmara, Açu II, Açu III, SE Paraíso, SE Touros (nomes
   podem ter erro de transcrição do áudio).

Fontes de dados abertos já levantadas pra essas fases (ONS constrained-off,
ANEEL SIGA/potência, COSERN) estão documentadas em
`docs/fontes_dados_abertos.md`.

**Quando a planilha do Daniel chegar**: reler este roadmap, cruzar com o
arquivo novo, propor plano de implementação (provável ordem: ficha de
detalhe + energia frustrada primeiro, rede de transmissão depois por
precisar de mais dados de subestação).

---

## 7. Convenções

- Idioma: português técnico formal (mensagens, commits, documentação).
- Commits: sem `Co-Authored-By`, formato `tipo: descrição curta`.
- Ambiente isolado em `.venv/` (gitignored), `requirements.txt` versionado.
