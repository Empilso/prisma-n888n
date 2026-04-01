// crewDefs.ts — Todas as 10 Crews do N888N Enterprise Orchestrator
// Descrições técnicas, detalhadas e acessíveis para leigos

export interface AgentDef {
    id: string;
    name: string;
    role: string;
    tech: 'python' | 'llm' | 'hybrid';
    description: string;
    howItWorks?: string[];
    libs?: string[];
    warning?: string;
    color?: string;
    defaultPos: { x: number; y: number };
}

export interface CrewDef {
    id: string;
    name: string;
    icon: string;
    color: string;
    sourceUrl: string;
    agents: AgentDef[];
    notes?: string;
}

// ─── AGENTES UNIVERSAIS (2, 3, 4) PARA NOVAS CREWS ─────────────────────────────
const UNIVERSAL_AGENTS: AgentDef[] = [
    {
        id: '2',
        name: 'Xylos-Bebeto: O Purificador de Plasma',
        role: 'Mestre da Purificação',
        tech: 'python',
        description: 'Motor determinístico v2 que aplica 12 diretrizes para transformar dados Bronze em Camada Prata com 32 campos auditados. Valida CNPJs matematicamente, extrai CPFs ocultos de nomes de fornecedores, decompõe competências em ano/mês/date, normaliza valores monetários BR e gera PrismaID único por registro — tudo sem dependência de IA.',
        howItWorks: [
            'Diretrizes 1-3: Limpeza de strings vazias → None, extração de CPF embutido no nome do fornecedor, normalização Title Case com stopwords (de, da, dos).',
            'Diretrizes 4-5: Validação de URL do PDF (link_pdf_nf → url_pdf_nf + link_pdf_valido bool), normalização de NF com classificação de tipo (curta/normal/longa/barra).',
            'Diretrizes 6-8: Mapeamento de categorias para slugs padronizados, decomposição de competência "MM/YYYY" em 3 campos tipados, auditoria matemática de CNPJ com dígitos verificadores (cnpj_valido bool).',
            'Diretrizes 9-12: PrismaID (hash MD5 de 5 campos-chave), Score de Qualidade (6 campos obrigatórios), normalização monetária R$ BR, preservação de valor_glosado/valor_detalhe/tipo_documento/link_detalhe/romario_coletado_em.',
        ],
        libs: ['json', 'hashlib', 're', 'datetime', 'argparse'],
        defaultPos: { x: 420, y: 80 },
    },
    {
        id: '3',
        name: 'Kael-Ronaldo: O Padronizador de Atributos',
        role: 'Validador de Identidade',
        tech: 'python',
        description: 'Responsável pela arquitetura de atributos técnicos. Ele garante que identificadores como CPF e CNPJ sejam válidos e formatados, e que valores monetários complexos sejam convertidos em números reais para somatórias e gráficos de precisão.',
        howItWorks: [
            'Verificação de CPF/CNPJ: Checa se os números de identificação são reais e válidos conforme o algoritmo oficial.',
            'Cálculo Financeiro: Transforma textos como "R$ 1.500,00" em números que o computador consegue somar.',
            'Garantia de Preenchimento: Certifica-se de que nenhuma informação essencial ficou faltando no documento.',
        ],
        libs: ['pydantic', 'pandas', 'numpy'],
        defaultPos: { x: 760, y: 80 },
    },
    {
        id: '4',
        name: 'Vorx-Garrincha: O Engenheiro de Integração',
        role: 'Conector de Banco de Dados',
        tech: 'python',
        description: 'O elo final da cadeia de dados. Ele gerencia a conexão segura com o cofre de dados (Supabase), realizando a carga das informações processadas de forma inteligente para que o painel de controle esteja sempre atualizado.',
        howItWorks: [
            'Organização em Gavetas: Coloca cada informação processada na "gaveta" correta dentro do banco de dados.',
            'Atualização Inteligente: Se um dado já existe, ele apenas atualiza; se é novo, ele adiciona — sem criar bagunça.',
            'Relatório de Carga: Avisa ao sistema quantos registros foram salvos com sucesso no servidor final.',
        ],
        libs: ['supabase-py', 'json', 'logging'],
        defaultPos: { x: 420, y: 360 },
    },
];

// ─── AS 10 CREWS ───────────────────────────────────────────────────────────────
export const crewDefs: CrewDef[] = [
    // ───────────────────── CREW 00 — Zidane: Biografias Parlamentares ─────────────
    {
        id: '0',
        name: 'Zidane (Biografia)',
        icon: '👤',
        color: '#ffd60a',
        sourceUrl: 'https://www.al.ba.gov.br/deputados',
        notes: 'Pipeline independente que alimenta a tabela parlamentares — entidade central do sistema.',
        agents: [
            {
                id: 'zidane_a',
                name: 'Zidane-A: O Coletor de IDs',
                role: 'Identificador de Parlamentares',
                tech: 'python',
                description: 'Fase 1 do Zidane. Monitora o portal NoPaperCloud via API estruturada (fallback Selenium) para capturar novos IDs de parlamentares e perfis ativos.',
                howItWorks: [
                    'API NoPaperCloud: Consumo direto da API oficial de Dados Abertos para máxima velocidade.',
                    'Fallback Selenium: Resgate automático via scraper visual se a API falhar ou der timeout.',
                    'Checkpoint Automático: Salva progresso em json para evitar reexecução de anos já coletados.',
                ],
                libs: ['requests', 'beautifulsoup4', 'lxml', 'json'],
                defaultPos: { x: 80, y: 150 },
            },
            {
                id: 'zidane_b',
                name: 'Zidane-B: O Scraper de Perfis',
                role: 'Minerador de Biografias',
                tech: 'hybrid',
                description: 'Fase 2 do Zidane. Para cada ID coletado, baixa o dataset completo de proposições e dados biográficos via API estruturada.',
                howItWorks: [
                    'Identificação Elite: Dados civis, profissão, email e telefones via JSON estruturado.',
                    'Trajetória Política: Histórico completo de mandatos e atividade parlamentar.',
                    'Proposições 5X: Aba de proposições legislativas e frequência em sessões.',
                ],
                libs: ['requests', 'beautifulsoup4', 'selenium', 'webdriver-manager', 'json'],
                defaultPos: { x: 480, y: 150 },
            },
            {
                id: 'zidane_c',
                name: 'Zidane-C',
                role: 'Normalizador de Dados',
                tech: 'python',
                color: '#bf5af2',
                description: 'Fase 3 do Zidane. Normaliza e consolida os 63 perfis extraídos pelo Zidane-B em um Hub unificado pronto para o banco.',
                howItWorks: [
                    'Nascimento Estruturado: Extração de Data, Município e UF de strings biográficas brutas.',
                    'Promoção de Atributos: Sobe Nome Civil, Profissão, Sexo e Estado Civil para a raiz do registro.',
                    'Filiação Partidária: Separação estruturada do histórico de partidos do array de mandatos.',
                    'Consolidação de Hub: Gera o arquivo parlamentares_hub_normalized.json com 63 Golden Records.',
                ],
                libs: ['json', 're', 'argparse', 'glob'],
                defaultPos: { x: 880, y: 150 },
            },
            {
                id: 'zidane_d',
                name: 'Zidane-D',
                role: 'Loader Supabase',
                tech: 'python',
                color: '#bf5af2',
                description: 'Lê o parlamentares_hub_normalized.json validado pelo Zidane-C e executa o Upsert definitivo na tabela parlamentares no Supabase. Processamento local Python, sem uso de LLM.',
                howItWorks: [
                    'Sincronização de Banco: Ingestão de dados JSON diretamente para colunas SQL e JSONB.',
                    'Deduplicação Inteligente: Uso do prisma_id como chave de resolução de conflitos (Merge-Duplicates).',
                    'Log Nativo de Inserção: Retorno HTTP Rest imediato para acompanhamento de sucesso/falha em tempo real.',
                ],
                libs: ['requests', 'python-dotenv', 'json'],
                defaultPos: { x: 1280, y: 150 },
            },
        ],
    },

    // ───────────────────── CREW 1 — Verbas ALBA (RESTAURADA) ─────────────────────
    {
        id: '1',
        name: 'Verbas Gabinete Alba',
        icon: '🏛️',
        color: '#bf5af2',
        sourceUrl: 'https://transparencia.alba.ba.gov.br',
        agents: [
            {
                id: '1',
                name: 'Zorg-Romário: O Especialista em Scraping',
                role: 'Coletor de Dados Web',
                tech: 'python',
                description: 'Especialista em "raspar" dados do Portal da Transparência da Assembleia Legislativa (ALBA). Ele entra no site oficial como se fosse uma pessoa, navega pelas tabelas difíceis e copia cada gasto parlamentar para dentro do nosso sistema.',
                howItWorks: [
                    'Navegação Automática: O robô "clica" em cada página de deputado e ano para não esquecer nada.',
                    'Leitura de Tabelas: Localiza exatamente onde estão os valores e as descrições dos gastos no site.',
                    'Varredura de Páginas: Avança página por página até que a última despesa seja capturada.',
                    'Persistência: Se o site cair, ele espera um pouco e tenta de novo automaticamente.',
                ],
                libs: ['requests', 'beautifulsoup4', 'lxml', 'pathlib'],
                defaultPos: { x: 80, y: 80 },
            },
            {
                id: '2',
                name: 'Xylos-Bebeto: O Purificador de Plasma',
                role: 'Mestre da Purificação',
                tech: 'python',
                description: 'Motor determinístico bebeto_v2 que aplica 12 diretrizes para transformar dados Bronze em Camada Prata com 32 campos auditados. Valida CNPJs matematicamente (cnpj_valido bool), extrai CPFs ocultos, normaliza NFs com tipo (curta/longa/barra), classifica URLs de PDF (link_pdf_valido), preserva valor_glosado e tipo_documento — tudo sem IA.',
                howItWorks: [
                    'Diretrizes 1-3: String vazia → None, CPF extraído do final do nome do fornecedor, Title Case inteligente com stopwords brasileiras.',
                    'Diretrizes 4-5: link_pdf_nf → url_pdf_nf + link_pdf_valido (bool), NF normalizada + nf_tipo (curta/normal/longa/barra) + num_nf_normalizado.',
                    'Diretrizes 6-8: Categorias → slugs (divulgacao, locomocao...), competência "MM/YYYY" → date + ano + mes, CNPJ sem pontuação + cnpj_valido (validação matemática).',
                    'Diretrizes 9-12: PrismaID (MD5 de processo|nf|cnpj|valor|data), qualidade_score (6 campos obrigatórios), R$ BR → float, preserva valor_glosado/valor_detalhe/tipo_documento/link_detalhe/romario_coletado_em/numero_nf_recibo_raw.',
                ],
                libs: ['json', 'hashlib', 're', 'datetime', 'argparse'],
                defaultPos: { x: 420, y: 80 },
            },
            {
                id: '3',
                name: 'Kaká v3.0: O Arquivista Forense Híbrido',
                role: 'Caçador de Notas Fiscais',
                tech: 'hybrid',
                description: 'Motor de auditoria de elite (v3.0). O Kaká agora opera em modo Híbrido de alto desempenho: utiliza invoice2data para extração gratuita (80%), motor nativo Unstructured (15%) e escala para Gemini 1.5 Flash Multimodal para casos complexos (5%). Baixa PDFs fisicamente, detecta divergências de valores entre o portal e a nota real, garantindo 99% de acurácia com economia de 95% de tokens.',
                howItWorks: [
                    'Estratégia Tri-Motor: 1. invoice2data (Grátis), 2. Unstructured (Local), 3. Gemini 1.5 Flash (Forense de Baixo Custo).',
                    'Datalake Blindado: Baixa e armazena fisicamente todos os PDFs originais para auditoria permanente.',
                    'Visão Multimodal Flash: Analisa imagens e scans via Gemini 1.5 Flash, extraindo CNPJs e Valores Totais reais.',
                    'Detecção de Fraude: Gera flags inteligentes de divergência (kaka_divergencia_*) quando o valor da nota difere do portal.',
                ],
                libs: ['google-generativeai', 'pypdfium2', 'fitz', 'aiohttp', 'tenacity'],
                defaultPos: { x: 760, y: 80 },
                color: '#8a2be2',
            },
            {
                id: 'ronaldo',
                name: 'Ronaldo Gold v1.0: O Finalizador',
                role: 'Engenheiro Relacional e DQA',
                tech: 'python',
                color: '#ffd60a',
                description: 'Cruza a tabela de Parlamentares (Supabase) com os dados higienizados para gerar a chave primária definitiva. Empacota todas as validações forenses em formato JSONB, preparando para o banco.',
                howItWorks: [
                    'Mapeamento Relacional: Busca e valida os IDs dos parlamentares da ALBA usando Fuzzy Match.',
                    'Garantia de Tipagem: Ouro — Normaliza tipos, booleanos, scores e garante consistência do esquema (DQA).',
                    'Empacotamento de Metadados: Agrupa informações sobre validações, lixo extraído, notas (JSONB).',
                    'Construção de Prisma ID Ouro: Hashes invioláveis e chaves estrangeiras perfeitamente preenchidas.'
                ],
                libs: ['supabase', 'pydantic', 'datetime'],
                defaultPos: { x: 1100, y: 80 },
            },
            {
                id: 'zidane_e',
                name: 'Zidane-E: O Injetor de Ouro',
                role: 'Loader Supabase — Verbas',
                tech: 'python',
                color: '#bf5af2',
                description: 'Etapa final da Crew Verbas ALBA. Lê todos os JSONs Ouro gerados pelo Ronaldo e executa o Upsert definitivo na tabela despesas_gabinete no Supabase. Batches de 500 registros, retry 3x, idempotente via prisma_id.',
                howItWorks: [
                    'Ingestão em Lote: Processa os arquivos Ouro em batches de 500 para máxima performance e segurança.',
                    'Idempotência Garantida: on_conflict=prisma_id como query param garante que re-execuções não criem duplicatas.',
                    'Retry Automático: 3 tentativas com backoff em caso de falha de rede ou timeout do Supabase.',
                    'Log de Carga: Reporta em tempo real quantos registros foram inseridos, atualizados ou ignorados.',
                ],
                libs: ['requests', 'python-dotenv', 'json', 'glob'],
                defaultPos: { x: 1440, y: 80 },
            },
        ],
    },

    // ───────────────────── CREW 2 — Pelé: Emendas Estaduais (BA) ─────────────────
    {
        id: '2',
        name: 'Pelé - Emendas Estaduais BA',
        icon: '📜',
        color: '#ff9f0a',
        sourceUrl: 'https://dados.ba.gov.br/dataset/emendas-parlamentares',
        notes: 'Pipeline de 4 agentes que extrai, purifica, enriquece e injeta emendas parlamentares estaduais da Bahia no PRISMA DADOS.',
        agents: [
            {
                id: 'pele_1',
                name: 'Zrix-Tostão: O Coletor de Planilhas',
                role: 'Integrador de Fontes — Emendas BA',
                tech: 'python',
                color: '#ff9f0a',
                description: 'Agente 1 do Pelé. Especialista em capturar as planilhas oficiais de emendas parlamentares do portal de Dados Abertos do Estado da Bahia (dados.ba.gov.br). Ele baixa os arquivos CSV/ZIP de cada ano, normaliza os cabeçalhos e produz um Bronze JSON estruturado pronto para purificação.',
                howItWorks: [
                    'Monitoramento Oficial: Acessa o portal dados.ba.gov.br e verifica novos datasets de emendas parlamentares estaduais.',
                    'Download Inteligente: Baixa arquivos CSV compactados em .zip sem precisar descompactar tudo no disco.',
                    'Normalização de Cabeçalhos: Traduz colunas governamentais brutas (ex: "NR_EMENDA", "VL_EMPENHADO") para o schema interno do Pelé.',
                    'Checkpoint por Ano: Salva progresso em arquivo de controle para não re-baixar exercícios já processados.',
                    'Bronze JSON: Gera emendas_ba_{ano}_bronze.json com todos os registros brutos estruturados para o Agente 2.',
                ],
                libs: ['requests', 'zipfile', 'pandas', 'json', 'pathlib'],
                defaultPos: { x: 80, y: 80 },
            },
            {
                id: 'pele_2',
                name: 'Xylos-Bebeto: O Purificador de Plasma',
                role: 'Motor de Purificação — Emendas BA',
                tech: 'python',
                color: '#ff9f0a',
                description: 'Agente 2 do Pelé. Motor determinístico bebeto_v2 adaptado ao schema de emendas estaduais. Aplica 12 diretrizes de limpeza sobre os dados Bronze: valida CPF/CNPJ do beneficiário, normaliza valores monetários BR, decompõe datas de empenho/liquidação/pagamento, classifica a fase de execução orçamentária e gera o PrismaID único por emenda — tudo sem IA.',
                howItWorks: [
                    'Diretrizes 1-3: String vazia → None, Title Case com stopwords BR nos campos de nome do parlamentar e do beneficiário, normalização de UF e município.',
                    'Diretrizes 4-6: Validação matemática de CNPJ do beneficiário (cnpj_valido bool), normalização de CPF oculto no nome, decomposição de datas de empenho/liquidação/pagamento em date + ano + mes.',
                    'Diretrizes 7-9: Classificação da fase de execução (empenhado/liquidado/pago) em slug padronizado, normalização de valores R$ BR → float para os três estágios financeiros.',
                    'Diretrizes 10-12: PrismaID Pelé (MD5 de nr_emenda|exercicio|cnpj_beneficiario|vl_empenhado|parlamentar_id), qualidade_score, preservação de campos originais do governo (nr_emenda, cd_acao, ds_funcao).',
                ],
                libs: ['json', 'hashlib', 're', 'datetime', 'argparse'],
                defaultPos: { x: 460, y: 80 },
            },
            {
                id: 'pele_3',
                name: 'Ronaldo Gold: O Finalizador de Emendas',
                role: 'Engenheiro Relacional — Emendas BA',
                tech: 'python',
                color: '#ffd60a',
                description: 'Agente 3 do Pelé. Cruza os dados Prata da emenda com a tabela de Parlamentares do Supabase para resolver o parlamentar_id definitivo via Fuzzy Match. Também enriquece o registro com os dados do beneficiário (CNPJ → razão social, porte) e empacota tudo em formato Ouro JSONB pronto para ingestão.',
                howItWorks: [
                    'Resolução de Parlamentar: Usa Fuzzy Match (rapidfuzz) para casar o nome do deputado da planilha com os registros da tabela parlamentares no Supabase, resolvendo o parlamentar_id.',
                    'Enriquecimento de Beneficiário: Cruza o CNPJ do beneficiário com a tabela empresas para adicionar razão social, porte e município da empresa.',
                    'DQA — Data Quality Assurance: Valida tipos de todos os campos do schema final, corrige booleanos e scores, garante que prisma_id seja único.',
                    'Empacotamento Ouro: Gera emendas_ba_{ano}_ouro.json com todos os campos do schema emendas_estaduais_ba incluindo metadados de auditoria (pele_coletado_em, qualidade_score, parlamentar_match_score).',
                ],
                libs: ['supabase', 'rapidfuzz', 'pydantic', 'json', 'datetime'],
                defaultPos: { x: 840, y: 80 },
            },
            {
                id: 'pele_4',
                name: 'Vorx-Garrincha: O Injetor de Emendas',
                role: 'Loader Supabase — Emendas BA',
                tech: 'python',
                color: '#ff9f0a',
                description: 'Agente 4 do Pelé — etapa final. Lê todos os JSONs Ouro gerados pelo Ronaldo Gold e executa o Upsert definitivo na tabela emendas_estaduais_ba no Supabase. Batches de 500 registros, retry 3x, idempotente via prisma_id.',
                howItWorks: [
                    'Ingestão em Lote: Processa os arquivos Ouro em batches de 500 registros para máxima performance.',
                    'Idempotência Garantida: on_conflict=prisma_id garante que re-execuções não criem duplicatas — operação segura.',
                    'Retry Automático: 3 tentativas com backoff exponencial em caso de falha de rede ou timeout do Supabase.',
                    'Log de Carga: Reporta em tempo real quantos registros foram inseridos, atualizados ou ignorados por batch.',
                    'Dry-Run Mode: Suporte ao flag --dry-run para validar o payload sem gravar nada no banco.',
                ],
                libs: ['requests', 'python-dotenv', 'json', 'glob'],
                defaultPos: { x: 1220, y: 80 },
            },
        ],
    },

    // ───────────────────── CREW 3 — Emendas Federais ─────────────────────────────
    {
        id: '3',
        name: 'Emendas Federais (Brasília)',
        icon: '🇧🇷',
        color: '#30d158',
        sourceUrl: 'https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares',
        agents: [
            {
                id: '1',
                name: 'Stryx-Didi: O Auditor Federal',
                role: 'Monitor de Dados Federais',
                tech: 'python',
                description: 'Sentinela do Portal da Transparência do Governo Federal. Ele filtra, no meio de milhões de dados nacionais de Brasília, apenas o dinheiro que foi destinado para cidades aqui da Bahia.',
                howItWorks: [
                    'Busca no Brasil Todo: Varre o banco de dados federal procurando por recursos destinados à Bahia.',
                    'Filtro por Estado: Separa apenas o que interessa para o nosso estado entre bilhões de registros.',
                    'Análise de Fluxo: Acompanha quanto dinheiro está vindo de Brasília para cada prefeito baiano.',
                ],
                libs: ['requests', 'pandas', 'io'],
                defaultPos: { x: 80, y: 80 },
            },
            ...UNIVERSAL_AGENTS,
        ],
    },

    // ───────────────────── CREW 4 — CEAP Câmara ──────────────────────────────────
    {
        id: '4',
        name: 'Gastos Deputados Federais',
        icon: '🏛️',
        color: '#0a84ff',
        sourceUrl: 'https://dadosabertos.camara.leg.br/dados/despesasDeputados/{ano}/ano{ano}.zip',
        agents: [
            {
                id: '1',
                name: 'Pulx-Rivelino: O Analista Legislativo',
                role: 'Auditor de Cota Parlamentar',
                tech: 'python',
                description: 'Auditor especializado nos gastos dos deputados federais eleitos pela Bahia. Ele fiscaliza o uso da Verba de Gabinete (CEAP), detalhando gastos com combustível, passagens e publicidade dos nossos representantes em Brasília.',
                howItWorks: [
                    'Conexão com a Câmara: Busca os dados oficiais direto do sistema da Câmara dos Deputados.',
                    'Filtro de Bancada: Identifica automaticamente quem são os deputados da Bahia.',
                    'Divisão por Tipo: Separa o que é gasto com avião, o que é almoço e o que é divulgação do mandato.',
                ],
                libs: ['requests', 'zipfile', 'csv'],
                defaultPos: { x: 80, y: 80 },
            },
            ...UNIVERSAL_AGENTS,
        ],
    },

    // ───────────────────── CREW 5 — CEAP Senado ──────────────────────────────────
    {
        id: '5',
        name: 'Gastos Senadores',
        icon: '🔱',
        color: '#5e5ce6',
        sourceUrl: 'https://www.senado.leg.br/transparencia/LAI/verba/{ano}_Senadores.csv',
        agents: [
            {
                id: '1',
                name: 'Vael-Falcão: O Monitor do Senado',
                role: 'Auditor do Senado',
                tech: 'python',
                description: 'Monitor especializado nos gastos dos 3 senadores baianos. Ele processa as contas enviadas ao Senado Federal para garantir que cada reembolso solicitado por eles seja transparente para o cidadão.',
                howItWorks: [
                    'Captura Autônoma: Pega as planilhas de gastos direto do site do Senado Federal.',
                    'Limpeza de Texto: Corrige nomes de empresas e prestadores de serviço para facilitar a leitura.',
                    'Foco na Bahia: Descarta gastos de senadores de outros estados para focar no que importa aqui.',
                ],
                libs: ['requests', 'chardet', 'pandas'],
                defaultPos: { x: 80, y: 80 },
            },
            ...UNIVERSAL_AGENTS,
        ],
    },

    // ───────────────────── CREW 6 — TSE Doações ──────────────────────────────────
    {
        id: '6',
        name: 'Contas Eleitorais (TSE)',
        icon: '🗳️',
        color: '#ff453a',
        sourceUrl: 'https://dadosabertos.tse.jus.br',
        agents: [
            {
                id: '1',
                name: 'Nexo-Pelé: O Auditor de Campanhas',
                role: 'Auditor Eleitoral',
                tech: 'python',
                description: 'Estrategista de dados eleitorais. Ele audita quem doou dinheiro para quem nas eleições, rastreando empresas e pessoas físicas para mostrar quanto custou cada campanha na Bahia.',
                howItWorks: [
                    'Rastreador de Doadores: Identifica quem são os maiores financiadores de cada candidato.',
                    'Busca de Padrões: Avisa se encontrar doações muito altas que pareçam suspeitas.',
                    'Histórico Eleitoral: Organiza os dados das eleições passadas para você comparar.',
                ],
                libs: ['requests', 'pandas', 'sqlite3'],
                defaultPos: { x: 80, y: 80 },
            },
            ...UNIVERSAL_AGENTS,
        ],
    },

    // ───────────────────── CREW 7 — Empresas BA ──────────────────────────────────
    {
        id: '7',
        name: 'Empresas Ativas (Bahia)',
        icon: '🏢',
        color: '#ffd60a',
        sourceUrl: 'https://brasil.io/dataset/socios-brasil/files/',
        agents: [
            {
                id: '1',
                name: 'Gork-Zizinho: O Analista de CNPJs',
                role: 'Processador de Big Data',
                tech: 'python',
                description: 'Processador de grandes volumes de dados de empresas. Ele analisa milhões de CNPJs registrados na Bahia para que possamos cruzar essas empresas com as que recebem dinheiro do governo.',
                howItWorks: [
                    'Leitura em Fluxo: Lê arquivos gigantescos sem travar o seu computador.',
                    'Economia de Espaço: Usa técnicas que fazem o arquivo ficar 10x menor mas com a mesma informação.',
                    'Aceleração de Busca: Prepara os dados de um jeito que a pesquisa por nome de empresa seja instantânea.',
                ],
                libs: ['pandas', 'pyarrow', 'gzip'],
                defaultPos: { x: 80, y: 80 },
            },
            ...UNIVERSAL_AGENTS,
        ],
    },

    // ───────────────────── CREW 8 — Sócios BA ────────────────────────────────────
    {
        id: '8',
        name: 'Sócios de Empresas',
        icon: '👥',
        color: '#64d2ff',
        sourceUrl: 'https://brasil.io/dataset/socios-brasil/files/',
        agents: [
            {
                id: '1',
                name: 'Thyra-Leônidas: O Detetive Societário',
                role: 'Analista de Vínculos',
                tech: 'python',
                description: 'O detetive do grupo. Ele descobre quem são os donos por trás de cada empresa, permitindo saber se um mesmo grupo de pessoas é dono de várias empresas que ganham licitações.',
                howItWorks: [
                    'Busca de Donos: Cruza os nomes dos sócios com os CNPJs das empresas.',
                    'Rede de Contatos: Organiza os dados para mostrar um "mapa" de quem é sócio de quem.',
                    'Filtro de Influência: Destaca pessoas que são donas de muitas empresas diferentes no estado.',
                ],
                libs: ['pandas', 'networkx', 'json'],
                defaultPos: { x: 80, y: 80 },
            },
            ...UNIVERSAL_AGENTS,
        ],
    },

    // ───────────────────── CREW 9 — TCM-BA ───────────────────────────────────────
    {
        id: '9',
        name: 'Contas das Prefeituras (TCM)',
        icon: '🔍',
        color: '#ff6b6b',
        sourceUrl: 'https://www.tcm.ba.gov.br/portal-da-transparencia/',
        agents: [
            {
                id: '1',
                name: 'Crix-Ademir: O Inspetor de Municípios',
                role: 'Monitor Municipal',
                tech: 'python',
                description: 'Sentinela das prefeituras baianas. Ele entra nos sites de todas as 417 cidades da Bahia para buscar as contas dos prefeitos através do Portal do Tribunal de Contas dos Municípios (TCM).',
                howItWorks: [
                    'Robô Navegador: O robô entra nos sistemas das prefeituras que são difíceis de acessar manualmente.',
                    'Trabalho em Lote: Faz o trabalho de busca em várias cidades ao mesmo tempo de forma organizada.',
                    'Memória de Progresso: Sabe exatamente onde parou, permitindo fiscalizar o estado todo sem erro.',
                ],
                libs: ['selenium', 'webdriver-manager', 'pandas'],
                defaultPos: { x: 80, y: 80 },
            },
            ...UNIVERSAL_AGENTS,
        ],
    },

    // ───────────────────── CREW 10 — Loa/Seplan PDFs ─────────────────────────────
    {
        id: '10',
        name: 'Leitura de Diários Oficiais',
        icon: '📑',
        color: '#a8edea',
        sourceUrl: 'http://www.ba.gov.br/seplan/emendas-parlamentares',
        agents: [
            {
                id: '1',
                name: 'Lyra-Sócrates: O Tradutor de Documentos',
                role: 'Inteligência de Documentos',
                tech: 'python',
                description: 'Especialista em documentos oficiais pesados. Ele analisa as leis orçamentárias (LOA) em PDF e extrai as tabelas de emendas anexas, transformando papel burocrático em dados que o sistema entende.',
                howItWorks: [
                    'Raio-X de Documento: Usa algoritmos matemáticos para "ver" onde terminam e começam as tabelas no papel.',
                    'Correção Auditiva: Ajusta textos que ficaram borrados ou tortos no arquivo original do governo.',
                    'Extrato de Dados: Pega as descrições dos programas e transforma tudo em uma lista fácil de ler.',
                ],
                libs: ['camelot-py', 'opencv-python', 'pytesseract'],
                defaultPos: { x: 80, y: 80 },
            },
            ...UNIVERSAL_AGENTS,
        ],
    },
];
