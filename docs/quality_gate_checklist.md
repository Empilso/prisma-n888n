# 🛡️ Quality Gate: Pronto para Download

Mestre, antes de apertarmos o botão de "EXECUTE", precisamos validar se estes 4 axiomas estão verdes:

## 1. Integridade de Schema (Architect)
- [ ] Tabela `alba.verbas_indenizatorias` criada no Supabase?
- [ ] Tabela `transp_ba.emendas_2026` criada no Supabase?
- [ ] Índices de performance aplicados nos campos de CNPJ e Município?

## 2. Lógica ETL (Dev)
- [ ] Script de normalização de CNPJ (14 bits) validado logicamente?
- [ ] Gerador de `raw_hash` configurado para evitar duplicidade?
- [ ] Conexão com Supabase enviando para as pastas `data/processed/`?

## 3. Sourcing (Analyst)
- [ ] URLs da ALBA confirmadas e ativas?
- [ ] Endpoints da TranspBA mapeados (CSV ou JSON)?

## 4. Segurança & Performance (Master)
- [ ] Estratégia de batch size definida (ex: 5000 registros/carga)?
- [ ] Logs de erro configurados para exportar para `data/quarantine/`?

---
**Atenção**: Só marque estes itens quando o design estiver refletindo 100% a sua visão de negócio.
