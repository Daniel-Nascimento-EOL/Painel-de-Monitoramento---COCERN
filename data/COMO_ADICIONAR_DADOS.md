# Como adicionar dados ao painel

> Guia prático para atualizar as planilhas desta pasta e refletir as
> mudanças no painel. Última atualização: 2026-08-27.

---

## 1. Panorama

O painel consome dados de **duas origens independentes**:

| Origem | O que é | Onde mora | Como atualiza |
|---|---|---|---|
| Planilhas Excel locais | Conjuntos, usinas, subestações, cidades de referência | `data/*.xlsx` (esta pasta) | Você edita o `.xlsx` à mão |
| Download ao vivo | Constrained-off do ONS e PLD da CCEE | S3 público do ONS / API da CCEE | Automático, a cada carga da página |

Este guia trata principalmente da **primeira origem** (as planilhas). A
segunda é descrita de forma resumida na seção 6.

### Fluxo de carga das planilhas

```
data/*.xlsx
    │  pandas.read_excel
    ▼
core/data_loader.py        ── lê a aba, renomeia colunas (dicionários _COLUNAS_*),
    │                          normaliza tipos e cria as chaves de junção
    │  @st.cache_data (sem TTL)
    ▼
ui/mapa.py                 ── filtros, métricas, tabela
viz/map_charts.py          ── marcadores, popups, linhas de conexão
```

---

## 2. Arquivos e abas

### `data/localizacao_conjuntos_ons_aneel.xlsx`

| Aba | Conteúdo | Linhas atuais | Lida por |
|---|---|---|---|
| `Localizacao` | Um registro por **conjunto eólico** | 54 | `load_conjuntos()` |
| `Detalhamento` | Um registro por **usina individual** | 309 | `load_usinas()` |
| `Fontes e metodologia` | Proveniência dos dados (texto) | 13 | *(não é lida pelo código)* |

### `data/bays.xlsx`

| Aba | Conteúdo | Linhas atuais | Lida por |
|---|---|---|---|
| `Bays` | Um registro por **subestação / ponto de conexão** | 15 | `load_bays()` |
| `Cidades_RN` | Cidades de referência (só rótulo fixo no mapa) | 21 | `load_cidades()` |

### Demais arquivos da pasta

- `rn_estado.geojson` — contorno do estado (IBGE). Não precisa mexer.
- `icons/logo_aero.jpg` — ícone do marcador de conjunto.
- `icons/logo_se.jpeg` — ícone do marcador de subestação.

Para trocar um ícone, basta substituir o arquivo mantendo o mesmo nome. O
ícone deve ser um traço escuro sobre fundo claro/branco: a função
`viz/map_charts.py::_tingir_icone_array()` deixa o fundo transparente e
pinta o traço na cor da paleta.

---

## 3. Colunas esperadas em cada aba

O `core/data_loader.py` **só enxerga as colunas mapeadas** nos dicionários
`_COLUNAS_*`. Colunas extras na planilha não quebram a carga, mas também
não aparecem no painel enquanto não forem mapeadas (ver seção 5).

### Aba `Localizacao` (`_COLUNAS_CONJUNTOS`)

| Coluna na planilha | Nome interno | Formato / observação |
|---|---|---|
| `Conjunto` | `conjunto` | Texto. Ex.: `Conjunto Eólico Acauã` |
| `id_ons` | `id_ons` | Texto. **Chave de junção com o dataset de constrained-off do ONS.** Ex.: `CJU_RNACA` |
| `Localização (lat, long)` | `localizacao` | String única `"lat, long"`. Ex.: `-6.088372, -36.654662` (vírgula separa os dois números) |
| `Município(s)` | `municipios` | Texto. Vários municípios separados por `;`. Ex.: `Macau - RN; Afonso Bezerra - RN` |
| `Capacidade instalada` | `capacidade_mw` | Texto `"NNN,NN MW"`. Ex.: `109,20 MW`. O parser tolera espaços soltos (`63 ,00MW`) |
| `Qtd. usinas` | `qtd_usinas` | Inteiro. **Não pode ficar vazio** (a conversão para `int` quebra com célula em branco) |
| `Qtde. aerogeradores` | `qtd_aerogeradores` | Inteiro |
| `Ponto de conexão` | `ponto_conexao` | Texto. Ex.: `SE Açu II`. **Chave de junção com a aba `Bays`** (o prefixo `SE ` é removido na normalização) |
| `Agente Proprietário` | `agente_proprietario` | Texto |
| `Agente Operador` | `agente_operador` | Texto |
| `Ajustamento Operativo` | `ajustamento_operativo` | Texto. Ex.: `AO-CE.NE.2LE` |
| `Logo - Agente Proprietário` | `logo_proprietario` | URL de imagem (externa; não é baixada). Pode ficar vazia |
| `Logo - Agente Operador` | `logo_operador` | URL de imagem. Pode ficar vazia |

### Aba `Detalhamento` (`_COLUNAS_USINAS`)

| Coluna na planilha | Nome interno | Formato / observação |
|---|---|---|
| `Conjunto` | `conjunto` | Texto. Ex.: `CONJ. ACAUÃ` ou `ACAUÃ`. Ver "chave de junção" abaixo |
| `Usina integrante` | `usina` | Texto |
| `CEG` | `ceg` | Código da usina na ANEEL. Ex.: `EOL.CV.RN.028444-0.1` |
| `Latitude` | `latitude` | Número decimal (colunas separadas, ao contrário de `Localizacao`) |
| `Longitude` | `longitude` | Número decimal |
| `Município(s)` | `municipios` | Texto |
| `Fonte coordenada` | `fonte_coordenada` | URL / texto |
| `Observação` | `observacao` | Texto. Pode ficar vazia |

### Aba `Bays` (`_COLUNAS_BAYS`)

| Coluna na planilha | Nome interno | Formato / observação |
|---|---|---|
| `Agente Operador` | `agente_operador` | Texto |
| `Subestação` | `subestacao` | Texto **sem** o prefixo `SE `. Ex.: `Açu II`. O painel adiciona `SE ` na exibição |
| `latitude` | `latitude` | Número decimal (minúsculo na planilha) |
| `longitude` | `longitude` | Número decimal (minúsculo na planilha) |

> A coluna `id_estado` existe na planilha mas não é mapeada. Pode ser
> mantida para referência.

### Aba `Cidades_RN` (`_COLUNAS_CIDADES`)

| Coluna na planilha | Nome interno | Formato / observação |
|---|---|---|
| `Cidade` | `cidade` | Texto |
| `Latitude` | `latitude` | Número decimal (**maiúsculo** nesta aba) |
| `Longitude` | `longitude` | Número decimal (**maiúsculo** nesta aba) |

---

## 4. Adicionar novas LINHAS (mais conjuntos, usinas, subestações, cidades)

Funciona automaticamente — basta acrescentar a linha na aba correta,
preenchendo todas as colunas mapeadas conforme a seção 3. Pontos de
atenção:

### Chaves de junção — precisam bater

1. **Conjunto ↔ usina** (`Localizacao` ↔ `Detalhamento`)
   Os nomes não batem direto: `Conjunto Eólico Acauã` vs `CONJ. ACAUÃ`. A
   função `core/data_loader.py::_chave_conjunto()` normaliza removendo os
   prefixos `Conjunto Eólico ` / `CONJ. ` e passando para caixa alta. Ao
   cadastrar uma usina nova, garanta que o nome do conjunto na aba
   `Detalhamento`, depois de tirar o prefixo e subir a caixa, seja
   **idêntico** ao da aba `Localizacao` com o mesmo tratamento. Se sobrar
   diferença (acento, espaço, algarismo romano), a usina não vincula ao
   conjunto e some do toggle "Mostrar usinas individuais".

2. **Conjunto ↔ subestação** (`Localizacao["Ponto de conexão"]` ↔ `Bays["Subestação"]`)
   `core/data_loader.py::_chave_subestacao()` remove o prefixo `SE ` e
   sobe a caixa. `SE Açu II` (conjunto) casa com `Açu II` (bay). Se o
   ponto de conexão de um conjunto novo não existir na aba `Bays`, a
   **linha de conexão não é desenhada** no mapa (o marcador do conjunto
   ainda aparece).

3. **Conjunto ↔ constrained-off do ONS** (`Localizacao["id_ons"]` ↔ CSV do ONS)
   O `id_ons` precisa ser o mesmo usado pelo ONS no dataset
   `restricao_coff_eolica_tm`. Se estiver errado ou vazio, o conjunto não
   entra no cálculo de energia frustrada.

### Formatos que quebram a carga se vierem errados

- `Localização (lat, long)` sem a vírgula, ou com vírgula decimal em vez
  de ponto (`-6,08; -36,65`) → o `split(",")` produz colunas erradas.
- `Qtd. usinas` vazio ou com texto → `astype(int)` levanta exceção e a
  página não carrega.
- `Capacidade instalada` sem número reconhecível → `float(...)` falha.

### Validação rápida (opcional)

Com o `.venv` ativo, na raiz do projeto:

```bash
python -c "from core.data_loader import load_conjuntos, load_usinas, load_bays, load_cidades; \
c=load_conjuntos(); u=load_usinas(); b=load_bays(); \
print('sem match conjunto->usina:', (~c['chave'].isin(u['chave'])).sum()); \
print('ponto de conexao sem bay:', sorted(set(c['chave_subestacao']) - set(b['chave'])))"
```

O ideal é `0` e `[]`. Qualquer valor diferente indica chave que não
casou.

---

## 5. Adicionar novas COLUNAS (novos campos)

Acrescentar uma coluna na planilha **não quebra** a carga, mas o campo só
aparece no painel depois de dois passos:

### Passo 1 — mapear a coluna em `core/data_loader.py`

No dicionário `_COLUNAS_*` da aba correspondente, adicione a entrada
`"Nome exato na planilha": "nome_interno"`. Exemplo, para um campo novo
`Tensão de conexão (kV)` na aba `Localizacao`:

```python
_COLUNAS_CONJUNTOS = {
    # ... entradas existentes ...
    "Tensão de conexão (kV)": "tensao_kv",
}
```

Se a coluna precisar de conversão de tipo (número, data), faça em
`load_conjuntos()` logo após o `rename`, como já é feito com
`qtd_usinas`, `capacidade_mw` e `latitude/longitude`.

### Passo 2 — usar o campo na interface

- **Popup / tooltip do mapa:** `viz/map_charts.py`, dentro do laço
  `for _, row in df_conjuntos.iterrows()` (monta `popup_html`).
- **Tabela / filtros da página:** `ui/mapa.py` — lista de colunas do
  `st.dataframe` (por volta da linha 67) e, se for filtro, a seção de
  `st.sidebar`.

Enquanto o passo 2 não é feito, o dado fica carregado no DataFrame mas
invisível para o usuário.

---

## 6. Dados ao vivo (ONS e CCEE) — resumo

Não exigem edição de planilha; são baixados a cada carga da página de
**Energia Frustrada**.

- **ONS — constrained-off:** `core/ons_coff.py::baixar_mes_rn(ano, mes)`
  baixa um CSV por mês direto do S3 público do ONS
  (`restricao_coff_eolica_tm`), filtra `id_estado == "RN"` e aplica as 5
  metodologias em `calcular_metodologias()`. Cache de 6 h. Funciona sem
  configuração.
- **CCEE — PLD horário:** `core/ccee_pld.py::baixar_pld_nordeste(ano)`
  tenta a API de dados abertos da CCEE. O WAF da CCEE costuma bloquear
  requisições de ambiente de desenvolvimento (HTTP 403); nesse caso o
  painel exibe a energia frustrada em MWh normalmente e apenas omite as
  colunas de impacto financeiro em R$, com aviso ao usuário.

Detalhes e riscos conhecidos: ver `CLAUDE.md`, seções 2.3, 2.4 e 4.

---

## 7. Depois de editar uma planilha: limpar o cache

Os loaders usam `@st.cache_data` **sem TTL**. Uma planilha editada com o
painel aberto **não** é relida sozinha. Faça um dos dois:

1. No painel: menu `⋮` (canto superior direito) → **Clear cache** →
   **Rerun**; ou
2. Reinicie o servidor: pare o `streamlit run app.py` e rode de novo.

Se a mudança "não apareceu", quase sempre é cache antigo.
