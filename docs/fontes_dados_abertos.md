# Fontes de Dados Abertos — Painel COCERN

Levantamento de fontes abertas úteis para evoluir o painel além do mapa de
localização (base: planilha `localizacao_conjuntos_ons_aneel.xlsx`). Pesquisa
feita via web em 2026-08-22.

## ONS — Dados Abertos (dados.ons.org.br)

### Restrição de operação por constrained-off — usinas eólicas
- **Conjunto**: https://dados.ons.org.br/dataset/restricao_coff_eolica_usi
- **Detalhamento por usina**: https://dados.ons.org.br/dataset/restricao_coff_eolica_detail
- **Grupo**: usinas eólicas Tipo I, Tipo II-B e Tipo II-C.
- **Granularidade**: recurso mensal (XLSX/CSV), dados horários por usina/conjunto.
- **Unidade**: MWh de energia cortada.
- **Motivo do corte** (campo presente): `REL` (indisponibilidade externa),
  `CNF` (confiabilidade elétrica), `ENE` (motivo energético) — conforme
  Módulo 5 / Submódulo 5.13 do Manual de Procedimentos da Operação (ONS).
- **Uso no painel**: é a fonte primária pra série histórica de constrained-off
  por conjunto — o dado que falta hoje na planilha de localização.
- Existe equivalente para usinas fotovoltaicas
  (`restricao_coff_fotovoltaica` / `..._detail`), caso o escopo do painel
  se amplie no futuro.

### Outros datasets ONS relevantes
- **ONS SINMAPS** (https://sig.ons.org.br/app/sinmaps/) — já citado na
  planilha original, mapas georreferenciados do SIN (linhas, subestações).
- Módulo 5 / Submódulo 5.13 (procedimentos de apuração de dados de restrição):
  https://www.ons.org.br//MPO/Documento%20Normativo/4.%20Rotinas%20Operacionais%20-%20SM%205.13/4.3.%20Rotinas%20P%C3%B3s-Opera%C3%A7%C3%A3o/4.3.2.%20Apura%C3%A7%C3%A3o%20de%20Dados/RO-AO.BR.13_Rev.08.pdf
  — define oficialmente os motivos e a metodologia de apuração do corte.

## ANEEL — Dados Abertos (dadosabertos.aneel.gov.br)

### SIGA — Sistema de Informações de Geração
- Dataset: https://dadosabertos.aneel.gov.br/dataset/siga-sistema-de-informacoes-de-geracao-da-aneel
- CSV direto (empreendimentos de geração, diário):
  https://dadosabertos.aneel.gov.br/dataset/6d90b77c-c5f5-4d81-bdec-7bc619494bb9/resource/2f65a1b0-19b8-4360-8238-b34ab4693d55/download/siga-empreendimentos-geracao-diario.csv
- **Campos relevantes**: nome do empreendimento, `CEG` (chave de join com a
  aba Detalhamento já existente no projeto), UF, fase da usina, potência
  outorgada, potência fiscalizada, data de entrada em operação, município,
  latitude/longitude.
- **Uso no painel**: enriquecer cada usina com potência (MW) — hoje só há
  contagem de usinas por conjunto, não capacidade instalada.

### Agentes de Geração de Energia Elétrica
- https://dadosabertos.aneel.gov.br/dataset/agentes-de-geracao-de-energia-eletrica
- **Uso**: identificar proprietário/agente de cada usina (não está na planilha atual).

## COSERN / Neoenergia RN (distribuidora local)

- Não foi encontrado portal de dados abertos dedicado (geodados de rede,
  pontos de conexão) — Neoenergia Cosern expõe principalmente normas técnicas
  e portal de geração distribuída institucionais:
  https://www.neoenergia.com/web/rn/normas-tecnicas
  https://www.neoenergia.com/web/rn/w/neoenergia-cosern-crea-portal-gd
- **Observação**: como os conjuntos eólicos do RN se conectam majoritariamente
  na rede básica (ONS), não na rede de distribuição da Cosern, é provável que
  o SINMAPS (ONS) seja a fonte melhor pra ponto de conexão/subestação, não a
  Cosern. Pesquisar de novo se o escopo do painel incluir geração distribuída.

## Outras fontes candidatas (não aprofundadas ainda)

- **CCEE** (Câmara de Comercialização de Energia Elétrica) — dados de
  contabilização, pode cruzar com energia não gerada por restrição.
- **EPE** — estudos de expansão da transmissão no RN (contexto de por que
  ocorre o congestionamento que gera constrained-off).
- **IBGE** — malha municipal (shapefile/geojson) do RN, útil se o mapa evoluir
  pra choropleth por município em vez de só pontos.

## Próximo passo sugerido

Cruzar `restricao_coff_eolica_detail` (ONS) com a aba `Detalhamento` do
projeto via `CEG` (chave já normalizada em `core/data_loader.py`) pra ligar
cada usina cortada ao seu conjunto e coordenada.
