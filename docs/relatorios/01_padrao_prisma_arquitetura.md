# 🏗️ PADRÃO PRISMA: Arquitetura de Armazenamento e Saída de Dados
**Data Lake Local e Schemas Universais Versão 1.0 | Março 2026 | Documento de Engenharia PRISMA**

## 📂 1. A Estrutura do Data Lake Local (Onde guardamos o ouro)
Para que múltiplos agentes rodem sem sobrescrever ou perder dados, a pasta `saida/` do extrator não é apenas um diretório, é um **Data Lake estruturado em camadas (Medallion Architecture)**.

### A Hierarquia Obrigatória (`n888n/data/saida/`):
```text
📦 saida
 ┣ 📂 bronze (Arquivos RAW / Brutos)
 ┃ ┣ 📜 alba_verbas_raw_20260321.json (Como veio do HTML)
 ┃ ┗ 📜 sefaz_emendas_raw_20260321.csv (Como veio do portal)
 ┣ 📂 prata (Dados Limpos e Tipados)
 ┃ ┣ 📜 alba_verbas_clean_20260321.json (Com Schema Universal)
 ┃ ┗ 📜 sefaz_emendas_clean_20260321.json (Com Schema Universal)
 ┣ 📂 ouro (Enriquecidos com Groq/Receita Federal)
 ┃ ┣ 📜 alba_verbas_enriched_20260321.json (Com IA e Risco)
 ┣ 📂 quarentena (Erro de Validação)
 ┃ ┗ 📜 relatorio_falha_cnpj_2026.json (CNPJs inválidos)
 ┗ 📂 sys_logs (Logs de Execução dos Agentes)
```

## 🧩 2. O Modelo Universal de Saída (Camada Prata)
Para que a ALBA comunique perfeitamente com a Câmara Federal e o TCM, todos os robôs devem converter o dado da Camada Bronze em um Schema Universal.

**Padrão Ouro de Objeto JSON de Extração:**
```json
{
    "id_origem": "12345/2026",
    "hash_unico": "md5(id_origem)",
    "politico_nome": "FULANO TAL",
    "politico_id_tse": "99999",
    "fornecedor_nome": "NOME DA EMPRESA LTDA",
    "fornecedor_cnpj": "00000000000100",
    "valor_bruto": 50000.00,
    "valor_liquido": 45000.00,
    "data_emissao": "2026-03-21",
    "competencia": "03/2026",
    "categoria_origem": "Divulgação de Atividade Parlamentar", 
    "link_documento": "https://al.ba.gov.br/.../nota.pdf",
    "link_portal": "https://...",
    "extrator_nome": "agente_alba_delta_v2",
    "extrator_data": "2026-03-21T10:00:00Z"
}
```

## ⚖️ 3. Regras de "Tratamento de Choque" (Gateway Bronze -> Prata)
1.  **Limpeza de Moeda:** `"R$ 1.500,00"` ➔ `1500.00` (float obrigatório).
2.  **Limpeza de CNPJ:** Extração apenas de dígitos numéricos, completado com zeros à esquerda (14 dígitos).
3.  **Maiúsculas/Minúsculas:** `.upper().strip()` para nomes e fornecedores.
4.  **Codificação Safegaurd:** `ensure_ascii=False, encoding='utf-8'`.

## 🤖 4. A Camada Ouro (Pós-Orquestração IA)
Adição de metadados críticos pós-Groq/CrewAI:
```json
{
    "ia_area_tematica": "Comunicação e Marketing",
    "ia_risco_nivel": "ALTO",
    "ia_flags": ["empresa_aberta_recentemente", "gasto_alto_fora_do_padrao"],
    "rf_capital_social": 1000.00,
    "rf_data_abertura": "2026-01-15"
}
```
*Gênesis da Padronização - N888N Elite*
