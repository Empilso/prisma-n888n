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
        name: 'Zidane: Biografias',
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
                name: 'Zidane-C: IA Enricher',
                role: 'Analista de Inteligência Política',
                tech: 'llm',
                description: 'Fase 3 do Zidane. Refina os dados brutos usando modelos Claude 3.5 Sonnet para detecção de anomalias e score de risco.',
                howItWorks: [
                    'Score de Risco: Análise léxica de proposições para identificar potenciais conflitos de interesse.',
                    'Resumo Executivo: Geração de bio premium sintetizada por IA.',
                    'Áreas de Atuação: Clusterização de temas legislativos dominantes.',
                ],
                libs: ['litellm', 'json', 'argparse'],
                defaultPos: { x: 880, y: 150 },
            },
        ],
    },

    // ───────────────────── CREW 1 — Verbas ALBA (RESTAURADA) ─────────────────────
    {
        id: '1',
        name: 'Verbas ALBA',
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
                id: 'kaka',
                name: 'Kaká: O Arquivista Forense',
                role: 'Caçador de Notas Fiscais',
                tech: 'python',
                description: 'O elo perdido entre a extração bruta e a análise. Kaká baixa fisicamente os PDFs das notas fiscais, aplica algoritmos de detecção de imagem x texto e usa OCR/LLM para extrair metadados, sem nunca descartar um documento.',
                howItWorks: [
                    'Download Blindado: Baixa PDFs com retentativas inteligentes e delay amigável.',
                    'Classificação Autônoma: Lê o cabeçalho do PDF para saber se é texto puro, imagem chapada ou até manuscrito.',
                    'OCR Adaptativo: Usa PyMuPDF, Tesseract ou até modelos de visão no DeepSeek/Gemini como último recurso.',
                    'Revisão Fallback: Se tudo falhar, a nota não é jogada fora; vai pra gaveta de auditoria manual.',
                ],
                libs: ['requests', 'fitz', 'cv2', 'pytesseract', 'Pillow'],
                defaultPos: { x: 760, y: 80 },
                color: '#8a2be2',
            },
            {
                id: '3',
                name: 'Dungk-Alpha: O Analista de Inteligência',
                role: 'Cérebro de IA Artificial',
                tech: 'llm',
                description: 'O núcleo cerebral do Prisma. Ele utiliza inteligência artificial de última geração para "ler" as descrições dos gastos, entender do que se trata e avisar se encontrar algo fora do comum que precise de atenção.',
                howItWorks: [
                    'Análise por IA: Envia os textos para o motor de inteligência entender o contexto de cada gasto.',
                    'Categorização Esperta: Agrupa os gastos (ex: combustível, passagens) mesmo que o site original não diga.',
                    'Alerta de Anomalias: Identifica gastos com valores ou explicações muito estranhas automaticamente.',
                ],
                libs: ['crewai', 'litellm', 'requests', 'concurrent.futures'],
                defaultPos: { x: 1100, y: 80 },
            },
        ],
    },

    // ───────────────────── CREW 2 — Emendas BA ───────────────────────────────────
    {
        id: '2',
        name: 'Emendas Estaduais (BA)',
        icon: '📜',
        color: '#ff9f0a',
        sourceUrl: 'https://dados.ba.gov.br/dataset/emendas-parlamentares',
        agents: [
            {
                id: '1',
                name: 'Zrix-Tostão: O Coletor de Planilhas',
                role: 'Integrador de Fontes',
                tech: 'python',
                description: 'Especialista em capturar planilhas gigantes de emendas do Governo do Estado. Ele monitora novas atualizações e prepara esses arquivos pesados para que possam ser processados rapidamente por nossa equipe de robôs.',
                howItWorks: [
                    'Monitoramento Oficial: Fica de olho no portal de Dados Abertos da Bahia para pegar novos arquivos.',
                    'Processamento Rápido: Abre arquivos compactados (.zip) sem precisar descompactar tudo no disco.',
                    'Tradução de Termos: Traduz os termos governamentais difíceis para nomes que nós entendemos melhor.',
                ],
                libs: ['requests', 'zipfile', 'pandas'],
                defaultPos: { x: 80, y: 80 },
            },
            ...UNIVERSAL_AGENTS,
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
