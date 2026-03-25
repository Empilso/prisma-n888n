import React, { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import AgentAvatar from './AgentAvatar';
import DataPreviewStudio from './DataPreviewStudio';
import AgentTerminal from './AgentTerminal';
import { crewDefs } from './crewDefs';

interface AgentDetailsDrawerProps {
    isOpen: boolean;
    onClose: () => void;
    agentId: string | null;
    agentLabel: string;
    selectedCrewId: string;
    onOpenStudio: (layer: 'bronze' | 'prata' | 'ouro') => void;
    inputReady?: boolean;
    systemStatus?: any;
}

type TabKey = 'overview' | 'prompts' | 'logs';

const tabs: { key: TabKey; icon: string; label: string }[] = [
    { key: 'overview', icon: '⚡', label: 'Visão Geral' },
    { key: 'prompts', icon: '📝', label: 'Diretrizes' },
    { key: 'logs', icon: '📊', label: 'Apuração' },
];

const modelProviders = [
    { id: 'groq', name: 'Groq Cloud', icon: '⚡', models: ['llama-3.3-70b-versatile', 'mixtral-8x7b-32768'], desc: 'Velocidade extrema' },
    { id: 'deepseek', name: 'DeepSeek AI', icon: '🧠', models: ['deepseek-chat', 'deepseek-reasoner'], desc: 'Raciocínio avançado' },
    { id: 'ollama', name: 'Ollama Local', icon: '🦙', models: ['llama3.1:8b', 'mistral:latest'], desc: 'Privacidade total' },
    { id: 'openrouter', name: 'OpenRouter', icon: '🔮', models: ['google/gemini-pro-1.5', 'anthropic/claude-3-haiku'], desc: 'Multi-modelos' },
];

const getLayer = (agentId: string | null): string => {
    if (agentId === '1') return 'bronze';
    if (agentId === '2') return 'prata';
    if (agentId === 'zidane_a') return 'parlamentares';
    if (agentId === 'zidane_b') return 'parlamentares/raw';
    if (agentId === 'zidane_c') return 'parlamentares/gold';
    return 'ouro';
};

const Section = ({ title, children, icon, actions }: { title: string; children: React.ReactNode; icon?: string; actions?: React.ReactNode }) => (
    <div className="animate-in fade-in slide-in-from-bottom-1 duration-300">
        <h4 className="text-[8px] font-black text-white/20 uppercase tracking-[0.2em] mb-3 flex items-center gap-2">
            {icon && <span className="text-[10px]">{icon}</span>}
            {title}
            <span className="flex-1 h-px bg-white/5" />
            {actions && <div className="flex gap-2 ml-2">{actions}</div>}
        </h4>
        {children}
    </div>
);

const InfoRow = ({ label, value }: { label: string; value: string }) => (
    <div className="flex items-center gap-2 py-1 group">
        <span className="text-[8px] font-black text-white/15 uppercase w-24 shrink-0 tracking-tighter transition-colors">{label}</span>
        <span className="text-[10px] text-white/50 font-mono-glass break-all bg-white/[0.01] px-2 py-0.5 rounded border border-white/[0.03] flex-1 group-hover:border-white/10 transition-colors">{value}</span>
    </div>
);

const Metric = ({ label, value, sub, color, trend }: { label: string, value: string, sub?: string, color?: string, trend?: string }) => (
    <div className="bg-white/[0.01] p-3 rounded-[20px] border border-white/[0.04] shadow-xl group hover:border-white/10 transition-all relative overflow-hidden">
        <div className="text-[7px] text-white/20 uppercase font-black mb-1 tracking-[0.1em]">{label}</div>
        <div className="flex items-baseline gap-2">
            <div className="text-lg font-bold text-white tracking-tighter" style={color ? { color } : undefined}>{value}</div>
            {trend && <div className="text-[7px] font-black text-[var(--accent-green)]">{trend}</div>}
        </div>
        {sub && <div className="text-[8px] text-white/20 mt-0.5 font-medium opacity-50 group-hover:opacity-100 transition-opacity uppercase tracking-tighter leading-tight">{sub}</div>}
        <div className="absolute right-[-10px] bottom-[-10px] w-12 h-12 bg-white/5 blur-2xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" style={color ? { backgroundColor: color } : undefined} />
    </div>
);

const CodePreview = ({ code }: { code: string }) => {
    const linesCount = code.split('\n').length;
    return (
        <div className="bg-[#08080a] border border-white/[0.03] rounded-[20px] overflow-hidden flex flex-col shadow-2xl">
            <div className="flex items-center justify-between px-4 py-1.5 border-b border-white/[0.03] bg-white/[0.01]">
                <div className="flex items-center gap-4">
                    <div className="flex gap-1">
                        <div className="w-1.5 h-1.5 rounded-full bg-white/10" />
                        <div className="w-1.5 h-1.5 rounded-full bg-white/10" />
                        <div className="w-1.5 h-1.5 rounded-full bg-white/10" />
                    </div>
                    <span className="text-[8px] text-white/20 font-mono-glass tracking-widest uppercase">monitoramento_bruto.log</span>
                </div>
                <span className="text-[8px] text-[var(--accent-green)] font-black font-mono-glass">L:{linesCount}</span>
            </div>
            <div className="h-[180px] overflow-auto custom-scrollbar flex bg-[#020202]">
                <div className="w-8 bg-black/40 border-r border-white/5 py-2 flex flex-col items-center shrink-0 select-none">
                    {Array.from({ length: Math.min(linesCount, 500) }).map((_, i) => (
                        <span key={i} className="text-[7px] font-mono-glass text-white/5 leading-relaxed block">{i + 1}</span>
                    ))}
                </div>
                <pre className="p-3 font-mono-glass text-[9px] text-[var(--accent-green)]/70 leading-relaxed flex-1 overflow-x-auto whitespace-pre">
                    {code}
                </pre>
            </div>
        </div>
    );
};

const AgentDetailsDrawer = ({ isOpen, onClose, agentId, agentLabel, selectedCrewId, onOpenStudio, inputReady, systemStatus }: AgentDetailsDrawerProps) => {
    const [activeTab, setActiveTab] = useState<TabKey>('overview');
    const [prompt, setPrompt] = useState('');
    const [loading, setLoading] = useState(false);
    const [inputData, setInputData] = useState<any>(null);
    const [filename, setFilename] = useState('');
    const [fileStats, setFileStats] = useState<any>(null);
    const [viewMode, setViewMode] = useState<'grid' | 'code'>('grid');
    const [availableFiles, setAvailableFiles] = useState<any[]>([]);
    const [availableBronzeFiles, setAvailableBronzeFiles] = useState<any[]>([]);
    const [isFetchingFiles, setIsFetchingFiles] = useState(false);
    const [selectedBronzeFile, setSelectedBronzeFile] = useState<string>('');

    const [selectedAno, setSelectedAno] = useState<number | 'all'>(2024);
    const [selectedMunicipio, setSelectedMunicipio] = useState('Salvador');
    const [selectedProvider, setSelectedProvider] = useState('groq');
    const [selectedModel, setSelectedModel] = useState('llama-3.3-70b-versatile');

    const crew = useMemo(() => crewDefs.find(c => c.id === selectedCrewId) || crewDefs[0], [selectedCrewId]);
    const agent = useMemo(() => crew.agents.find(a => a.id === agentId), [crew, agentId]);

    const isActuallyRunning = systemStatus?.agents?.[agentId || '']?.status === 'running';

    useEffect(() => {
        if (isOpen && agentId) {
            setActiveTab('overview');
            fetchPrompt();
            fetchAvailableFiles();
            if (agentId === '2') fetchBronzeFiles();
            fetchPreview();
        }
    }, [isOpen, agentId, selectedCrewId]);

    const fetchBronzeFiles = async () => {
        try {
            const res = await fetch(`http://localhost:8001/api/agent/2/bronze-files`);
            const data = await res.json();
            setAvailableBronzeFiles(data.files || []);
            if (data.files?.length > 0 && !selectedBronzeFile) {
                setSelectedBronzeFile(data.files[0].name);
            }
        } catch (e) { }
    };

    const fetchPrompt = async () => {
        try {
            const res = await fetch(`http://localhost:8001/api/get-prompt/${agentId}`);
            const data = await res.json();
            setPrompt(data.prompt || '');
        } catch (e) { }
    };

    const fetchAvailableFiles = async () => {
        if (!agentId) return;
        setIsFetchingFiles(true);
        try {
            const res = await fetch(`http://localhost:8001/api/datalake/files`);
            const json = await res.json();
            if (json.status === 'ok') {
                const layer = getLayer(agentId);
                const filtered = json.files.filter((f: any) => f.layer === layer);
                setAvailableFiles(filtered);
            }
        } catch (e) { }
        setIsFetchingFiles(false);
    };

    const fetchPreview = async (targetFile?: string) => {
        try {
            const layer = getLayer(agentId);
            const fname = targetFile || filename;

            let url = `http://localhost:8001/api/agent-data/${layer}`;
            if (targetFile) {
                url = `http://localhost:8001/api/datalake/files/${layer}/${targetFile}`;
            }

            const res = await fetch(url);
            const json = await res.json();
            // Normalização: se for um objeto de checkpoint, extrai a lista 'records'. Caso contrário, usa o dado direto ou array vazio.
            const normalizedData = json.data?.records || (Array.isArray(json.data) ? json.data : []);
            setInputData(normalizedData);
            const finalFname = targetFile || json.filename || filename;
            setFilename(finalFname);

            // Busca estatísticas se tiver nome de arquivo
            if (finalFname) {
                // Reseta stats antes da nova busca para evitar confusão de dados
                setFileStats(null);
                const sResp = await fetch(`http://localhost:8001/api/datalake/stats/${agentId}?filename=${finalFname}`);
                const sData = await sResp.json();
                if (sData.status === 'ok') setFileStats(sData);
            }
        } catch (e) { }
    };

    const handleSave = async () => {
        setLoading(true);
        try {
            await fetch(`http://localhost:8001/api/configure-prompt/${agentId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ custom_prompt: prompt }),
            });
        } catch (e) { }
        setLoading(false);
    };

    const handleRun = async () => {
        if (!agentId) return;
        setLoading(true);
        try {
            // Determina qual ano usar: prioritize o ano do arquivo carregado (filename) se disponível
            const yearMatch = filename.match(/20\d{2}/);
            const yearToRun = yearMatch ? yearMatch[0] : selectedAno.toString();

            const queryParams = new URLSearchParams({
                ano: yearToRun,
                municipio: selectedMunicipio,
                provider: selectedProvider,
                model: selectedModel
            });

            if (agentId === '2' && selectedBronzeFile) {
                queryParams.append('filename', selectedBronzeFile);
            }

            const url = `http://localhost:8001/api/run-agent/${agentId}?${queryParams.toString()}`;
            console.log(`🚀 [AGENT_DRAWER] Disparando Agente ${agentId}:`, url);

            await fetch(url, { method: 'POST' });
        } catch (e) {
            console.error(`❌ [AGENT_DRAWER] Erro ao disparar agente:`, e);
        }
        setLoading(false);
    };

    const handleStop = async () => {
        if (!agentId) return;
        try {
            await fetch(`http://localhost:8001/api/stop-agent/${agentId}`, { method: 'POST' });
        } catch (e) { }
    };

    const renderConfigControls = () => {
        const needsYear = ['1', '3', '4', '5', '6', '10'].includes(selectedCrewId) && agentId === '1';
        const needsCity = selectedCrewId === '9' && agentId === '1';
        const isLLM = agent?.tech === 'llm';

        return (
            <div className="grid grid-cols-1 gap-3 mt-2">
                {isLLM && (
                    <div className="bg-white/[0.02] p-3 rounded-xl border border-white/5 space-y-3">
                        <div>
                            <label className="text-[7px] font-black text-white/20 uppercase tracking-[0.1em] mb-2 block">Motor de Inteligência (IA)</label>
                            <div className="grid grid-cols-2 gap-1.5">
                                {modelProviders.map(p => (
                                    <button
                                        key={p.id}
                                        onClick={() => {
                                            setSelectedProvider(p.id);
                                            setSelectedModel(p.models[0]);
                                        }}
                                        className={`flex flex-col items-start gap-1 p-2 rounded-lg border transition-all ${selectedProvider === p.id
                                            ? 'bg-white/10 border-white/20 text-white shadow-lg'
                                            : 'bg-white/5 border-white/5 text-white/30 hover:bg-white/10'
                                            }`}
                                    >
                                        <div className="flex items-center gap-1.5">
                                            <span className="text-xs">{p.icon}</span>
                                            <span className="text-[8px] font-black uppercase tracking-tighter">{p.name}</span>
                                        </div>
                                        <span className="text-[6px] font-bold text-white/20 uppercase leading-none">{p.desc}</span>
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div>
                            <label className="text-[7px] font-black text-white/20 uppercase tracking-[0.1em] mb-2 block">Modelo Especializado</label>
                            <select
                                value={selectedModel}
                                onChange={(e) => setSelectedModel(e.target.value)}
                                className="w-full bg-black/40 border border-white/5 rounded-lg px-2 py-1.5 text-[9px] font-bold text-white/60 focus:outline-none focus:border-white/20"
                            >
                                {modelProviders.find(p => p.id === selectedProvider)?.models.map(m => (
                                    <option key={m} value={m}>{m}</option>
                                ))}
                            </select>
                        </div>
                    </div>
                )}

                {needsYear && (
                    <div className="flex flex-col gap-2">
                        <label className="text-[7px] font-black text-white/20 uppercase tracking-[0.1em] block">Seleção de Safra (Ano de Referência)</label>

                        {/* NOVO: Botão Extrair Todos (Filas/Lote) */}
                        {agentId === '1' && (
                            <button
                                onClick={() => setSelectedAno('all')}
                                className={`w-full py-2.5 rounded-xl border transition-all flex items-center justify-center gap-3 relative overflow-hidden group ${selectedAno === 'all'
                                    ? 'bg-[var(--accent-purple)]/20 border-[var(--accent-purple)]/50 text-white shadow-[0_0_20px_rgba(191,90,242,0.25)]'
                                    : 'bg-white/5 border-white/10 text-white/40 hover:bg-white/10 hover:text-white/80'
                                    }`}
                            >
                                {selectedAno === 'all' && <div className="absolute inset-0 bg-gradient-to-r from-transparent via-[var(--accent-purple)]/10 to-transparent animate-premium-glow" />}
                                <span className={`text-xl filter drop-shadow-md transition-transform duration-300 ${selectedAno === 'all' ? 'scale-110' : 'grayscale opacity-50 group-hover:grayscale-0 group-hover:opacity-100'}`}>🚀</span>
                                <div className="flex flex-col items-start pr-2 z-10">
                                    <span className="text-[11px] font-black uppercase tracking-[0.15em] text-left drop-shadow-sm">Extrair Todos os Anos</span>
                                    <span className="text-[7px] font-bold text-white/40 uppercase tracking-widest mt-0.5">Criar Fila Sequencial (Autônomo)</span>
                                </div>
                            </button>
                        )}

                        <div className="grid grid-cols-5 gap-1.5 mt-1">
                            {[2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025].map(ano => {
                                const agentStatus = systemStatus?.agents?.[agentId || ''];
                                const isExtracted = agentStatus?.completed_years?.includes(ano.toString());
                                const isCheckpointed = agentStatus?.checkpoint_years?.includes(ano.toString());
                                const isAvailable = agentStatus?.available_input_years?.includes(ano.toString());

                                return (
                                    <button
                                        key={ano}
                                        onClick={() => {
                                            setSelectedAno(ano);
                                            // Se já estiver extraído, tenta focar no arquivo bronze/prata correspondente
                                            const entry = availableFiles.find(f => f.name.includes(ano.toString()));
                                            if (entry) {
                                                setFilename(entry.name);
                                                fetchPreview(entry.name);
                                            }
                                        }}
                                        className={`relative py-2 rounded-xl text-[10px] font-black border transition-all ${selectedAno === ano
                                            ? 'bg-[var(--accent-purple)]/20 border-[var(--accent-purple)]/40 text-white shadow-lg'
                                            : isExtracted
                                                ? 'bg-[var(--accent-green)]/10 border-[var(--accent-green)]/30 text-[var(--accent-green)]'
                                                : isCheckpointed
                                                    ? 'bg-[var(--orange)]/10 border-[var(--orange)]/30 text-[var(--orange)]'
                                                    : isAvailable
                                                        ? 'bg-[var(--accent-blue)]/10 border-[var(--accent-blue)]/30 text-[var(--accent-blue)]'
                                                        : 'bg-white/5 border-white/5 text-white/20 hover:text-white/40'
                                            }`}
                                    >
                                        {ano}
                                        {isExtracted && (
                                            <span className="absolute -top-1.5 -right-1.5 w-3.5 h-3.5 bg-[var(--accent-green)] rounded-full border-2 border-[#050505] flex items-center justify-center text-[7px] text-black font-black shadow-lg">✓</span>
                                        )}
                                        {isCheckpointed && !isExtracted && (
                                            <span className="absolute -top-1.5 -right-1.5 w-3 h-3 bg-[var(--orange)] rounded-full border-2 border-[#050505] animate-pulse shadow-lg" />
                                        )}
                                    </button>
                                );
                            })}
                        </div>
                        <div className="mt-2 flex items-center justify-between">
                            <span className="text-[6px] font-black text-white/20 uppercase tracking-widest">Legenda:</span>
                            <div className="flex gap-3">
                                <div className="flex items-center gap-1">
                                    <div className="w-1.5 h-1.5 rounded-full bg-[var(--accent-green)]" />
                                    <span className="text-[6px] font-black text-white/30 uppercase">Extraído</span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <div className="w-1.5 h-1.5 rounded-full bg-[var(--orange)]" />
                                    <span className="text-[6px] font-black text-white/30 uppercase">Em Andamento</span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <div className="w-1.5 h-1.5 rounded-full bg-white/20" />
                                    <span className="text-[6px] font-black text-white/30 uppercase">Pendente</span>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {needsCity && (
                    <div>
                        <label className="text-[7px] font-black text-white/20 uppercase tracking-[0.1em] mb-2 block">Município para Análise</label>
                        <select
                            value={selectedMunicipio}
                            onChange={(e) => setSelectedMunicipio(e.target.value)}
                            className="w-full bg-white/5 border border-white/5 rounded-lg px-2 py-1.5 text-[10px] font-bold text-white/80 focus:outline-none focus:border-white/20"
                        >
                            <option value="Salvador">Salvador</option>
                            <option value="Feira de Santana">Feira de Santana</option>
                            <option value="Senhor do Bonfim">Senhor do Bonfim</option>
                        </select>
                    </div>
                )}

                {selectedCrewId === '0' && (() => {
                    const agentStatus = systemStatus?.agents?.[agentId || ''];
                    const idsFile = availableFiles.find(f => f.name === 'parlamentares_ids.json');

                    if (agentId === 'zidane_a') {
                        return (
                            <div className="space-y-4">
                                <div className="p-4 bg-gradient-to-r from-yellow-500/10 to-transparent border border-yellow-500/20 rounded-xl relative overflow-hidden group">
                                    <div className="absolute -right-4 -top-4 text-6xl opacity-10 group-hover:scale-110 transition-transform">👤</div>
                                    <h3 className="text-[10px] font-black text-yellow-500 uppercase tracking-[0.15em] mb-1">Módulo de Reconhecimento</h3>
                                    <p className="text-[8px] text-white/40 leading-relaxed font-medium mb-3 max-w-[85%]">
                                        Varredura completa na Assembleia Legislativa da Bahia para identificação e mapeamento dos parlamentares oficiais.
                                    </p>

                                    {idsFile ? (
                                        <div className="flex items-center gap-3 p-2 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                                            <span className="text-xl">✅</span>
                                            <div>
                                                <div className="text-[9px] font-black text-yellow-400">COLETA CONCLUÍDA</div>
                                                <div className="text-[7px] text-yellow-500/60 uppercase font-black">{idsFile.size} • {idsFile.modified}</div>
                                            </div>
                                            <button
                                                onClick={() => {
                                                    setFilename('parlamentares_ids.json');
                                                    fetchPreview('parlamentares_ids.json');
                                                }}
                                                className="ml-auto px-3 py-1 bg-yellow-500/20 hover:bg-yellow-500/40 text-yellow-400 text-[8px] font-black rounded uppercase transition-colors"
                                            >
                                                Visualizar
                                            </button>
                                        </div>
                                    ) : (
                                        <div className="flex items-center gap-3 p-2 bg-white/5 border border-white/10 rounded-lg opacity-60">
                                            <span className="text-xl">⏳</span>
                                            <div>
                                                <div className="text-[9px] font-black text-white/50">AGUARDANDO COLETA</div>
                                                <div className="text-[7px] text-white/30 uppercase font-black">Nenhum dado encontrado no Datalake</div>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        );
                    }

                    if (agentId === 'zidane_b' || agentId === 'zidane_c') {
                        return (
                            <div className="space-y-4">
                                <div className="p-3 bg-[var(--accent-purple)]/5 border border-[var(--accent-purple)]/10 rounded-xl">
                                    <div className="flex items-center gap-2 mb-1.5">
                                        <span className="text-[10px]">⚙️</span>
                                        <span className="text-[8px] font-black text-[var(--accent-purple)] uppercase tracking-widest">{agentId === 'zidane_b' ? 'Mass Scraper' : 'LLM Brain'}</span>
                                    </div>
                                    <p className="text-[9px] text-white/40 leading-relaxed font-medium">
                                        Monitoramento de arquivos em andamento. Total disponíveis: {availableFiles.length} perfis.
                                    </p>
                                </div>
                            </div>
                        );
                    }
                    return null;
                })()}

                {agentId === '2' && (() => {
                    const ANOS = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025];
                    const agentStatus = systemStatus?.agents?.['2'];
                    const prataAnos: string[] = agentStatus?.completed_years || [];
                    const bronzeAnos: string[] = (systemStatus?.agents?.['1']?.completed_years || []);

                    return (
                        <div className="space-y-4">
                            {/* Radar de Safras Bronze → Prata */}
                            <div>
                                <label className="text-[7px] font-black text-white/20 uppercase tracking-[0.1em] mb-3 block">Status do Pipeline por Safra</label>
                                <div className="grid grid-cols-3 gap-1.5">
                                    {ANOS.map(ano => {
                                        const anoStr = ano.toString();
                                        const isPrata = prataAnos.includes(anoStr);
                                        const isBronze = bronzeAnos.includes(anoStr) && !isPrata;
                                        const isSelected = selectedBronzeFile.includes(anoStr);
                                        return (
                                            <button
                                                key={ano}
                                                onClick={() => {
                                                    const match = availableBronzeFiles.find((f: any) => f.name.includes(anoStr) && !f.name.includes('checkpoint'));
                                                    if (match) {
                                                        setSelectedBronzeFile(match.name);
                                                        setSelectedAno(ano);
                                                        fetchPreview(match.name);
                                                    }
                                                }}
                                                disabled={!isBronze && !isPrata}
                                                className={`relative flex flex-col items-center justify-center p-2 rounded-xl border transition-all ${isPrata ? 'bg-[var(--accent-green)]/5 border-[var(--accent-green)]/20 hover:border-[var(--accent-green)]/40'
                                                    : isBronze ? 'bg-orange-500/5 border-orange-500/20 hover:border-orange-500/40 cursor-pointer'
                                                        : 'bg-white/[0.01] border-white/5 opacity-30 cursor-not-allowed'
                                                    } ${isSelected ? 'ring-1 ring-[var(--accent-purple)]/60' : ''}`}
                                            >
                                                <div className={`w-2 h-2 rounded-full mb-1 ${isPrata ? 'bg-[var(--accent-green)] shadow-[0_0_8px_rgba(50,205,50,0.6)]'
                                                    : isBronze ? 'bg-orange-400 shadow-[0_0_8px_rgba(251,146,60,0.5)]'
                                                        : 'bg-white/10'
                                                    }`} />
                                                <span className={`text-[9px] font-black ${isPrata ? 'text-[var(--accent-green)]' : isBronze ? 'text-orange-400' : 'text-white/20'}`}>{ano}</span>
                                                <span className={`text-[6px] font-black uppercase mt-0.5 ${isPrata ? 'text-[var(--accent-green)]/60' : isBronze ? 'text-orange-400/60' : 'text-white/10'}`}>{isPrata ? 'PRATA' : isBronze ? 'PRONTO' : 'PEND.'}</span>
                                            </button>
                                        );
                                    })}
                                </div>
                                <div className="flex items-center gap-4 mt-2 px-1">
                                    <div className="flex items-center gap-1"><div className="w-1.5 h-1.5 rounded-full bg-[var(--accent-green)]" /><span className="text-[6px] font-black text-white/30 uppercase">Purificado (Prata)</span></div>
                                    <div className="flex items-center gap-1"><div className="w-1.5 h-1.5 rounded-full bg-orange-400" /><span className="text-[6px] font-black text-white/30 uppercase">Aguarda Purificação</span></div>
                                    <div className="flex items-center gap-1"><div className="w-1.5 h-1.5 rounded-full bg-white/20" /><span className="text-[6px] font-black text-white/30 uppercase">Pendente</span></div>
                                </div>
                            </div>

                            {/* Seletor de Arquivo Bronze */}
                            <div>
                                <label className="text-[7px] font-black text-white/20 uppercase tracking-[0.1em] mb-2 block">Arquivo Fonte (Camada Bronze)</label>
                                <div className="space-y-1.5 max-h-[200px] overflow-y-auto pr-1 custom-scrollbar">
                                    {availableBronzeFiles.length > 0 ? (
                                        availableBronzeFiles.map((f: any) => {
                                            const yrMatch = f.name.match(/20\d{2}/);
                                            const fileYear = yrMatch ? yrMatch[0] : null;
                                            const isAlreadyPrata = fileYear && prataAnos.includes(fileYear) && !f.name.includes('checkpoint');
                                            return (
                                                <button
                                                    key={f.name}
                                                    onClick={() => {
                                                        setSelectedBronzeFile(f.name);
                                                        if (fileYear) setSelectedAno(parseInt(fileYear));
                                                        fetchPreview(f.name);
                                                    }}
                                                    className={`w-full flex items-center justify-between p-2.5 rounded-xl border transition-all ${selectedBronzeFile === f.name
                                                        ? 'bg-[var(--accent-purple)]/10 border-[var(--accent-purple)]/40 text-white'
                                                        : 'bg-white/5 border-white/5 text-white/50 hover:bg-white/10 hover:text-white/80'}`}
                                                >
                                                    <div className="flex items-center gap-3">
                                                        <span className="text-sm">{f.name.includes('checkpoint') ? '⏳' : '📥'}</span>
                                                        <div className="text-left">
                                                            <div className="text-[9px] font-black tracking-tight">{f.name}</div>
                                                            <div className="text-[7px] opacity-40 font-black uppercase mt-0.5">{f.size} • {f.modified}</div>
                                                        </div>
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        {isAlreadyPrata && <span className="text-[7px] font-black px-1.5 py-0.5 rounded-lg bg-[var(--accent-green)]/15 text-[var(--accent-green)]">✓ PRATA</span>}
                                                        {fileYear && <span className={`text-[8px] font-black px-1.5 py-0.5 rounded-lg ${isAlreadyPrata ? 'bg-[var(--accent-green)]/10 text-[var(--accent-green)]' : 'bg-orange-500/15 text-orange-400'}`}>{fileYear}</span>}
                                                        {selectedBronzeFile === f.name && <div className="w-1.5 h-1.5 rounded-full bg-[var(--accent-purple)] shadow-[0_0_10px_var(--accent-purple)]" />}
                                                    </div>
                                                </button>
                                            );
                                        })
                                    ) : (
                                        <div className="text-center py-6 bg-white/[0.01] rounded-xl border border-dashed border-white/5 text-white/10 text-[8px] font-black uppercase tracking-widest">
                                            Aguardando geração pelo Romário...
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Missão */}
                            <div className="p-3 bg-[var(--accent-purple)]/5 border border-[var(--accent-purple)]/10 rounded-xl">
                                <div className="flex items-center gap-2 mb-1.5">
                                    <span className="text-[10px]">⚖️</span>
                                    <span className="text-[8px] font-black text-[var(--accent-purple)] uppercase tracking-widest">Missão de Bebeto</span>
                                </div>
                                <p className="text-[9px] text-white/40 leading-relaxed font-medium">
                                    Aplica as 12 diretrizes determinísticas para transformar o Bronze em dados <span className="text-white/60">Camada Prata</span> com integridade auditada, sem depender de IA.
                                </p>
                            </div>

                            {/* Saídas Prata geradas */}
                            {availableFiles.length > 0 && (
                                <div>
                                    <label className="text-[7px] font-black text-white/20 uppercase tracking-[0.1em] mb-2 block">Arquivos Purificados (Camada Prata)</label>
                                    <div className="space-y-1 bg-white/[0.02] p-2 rounded-xl border border-white/5 max-h-[150px] overflow-y-auto custom-scrollbar">
                                        {availableFiles.map((f: any) => (
                                            <div key={f.name} className="flex items-center justify-between p-1.5 border-b border-white/[0.03] last:border-0">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-[10px]">💎</span>
                                                    <span className="text-[9px] font-bold text-[var(--accent-green)]/70">{f.name}</span>
                                                </div>
                                                <span className="text-[7px] font-black text-white/10 uppercase">{f.size}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    );
                })()}
            </div>
        );
    };

    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} className="fixed inset-0 bg-black/60 backdrop-blur-[4px] z-[100]" />
                    <motion.div
                        initial={{ x: '100%' }}
                        animate={{ x: 0 }}
                        exit={{ x: '100%' }}
                        transition={{ type: 'spring', damping: 40, stiffness: 400 }}
                        className="fixed right-0 top-0 bottom-0 w-[380px] bg-[#050505] border-l border-white/[0.04] shadow-[0_0_100px_rgba(0,0,0,0.8)] z-[101] flex flex-col overflow-hidden"
                    >
                        {/* Ultra Compact Header */}
                        <div className="p-5 pb-4 border-b border-white/[0.04] bg-white/[0.01]">
                            <button onClick={onClose} className="absolute right-4 top-4 w-6 h-6 rounded-full flex items-center justify-center hover:bg-white/5 text-white/20 hover:text-white transition-all text-sm">✕</button>

                            <div className="flex items-center gap-4">
                                <div className="p-0.5 rounded-[18px] bg-gradient-to-br from-[var(--accent-purple)]/40 to-transparent border border-white/10 shadow-2xl">
                                    <AgentAvatar
                                        agentId={agentId || '1'}
                                        size={64}
                                        skinVariant={systemStatus?.agents?.[agentId || '']?.skin_variant}
                                    />
                                </div>
                                <div className="flex-1">
                                    <div className="flex items-center gap-2 mb-0.5">
                                        <h2 className="text-base font-black text-white tracking-tighter uppercase">{agent?.name.split(':')[0] || agentLabel}</h2>
                                    </div>
                                    <p className="text-[9px] text-white/30 font-black uppercase tracking-widest">{agent?.role}</p>
                                </div>
                            </div>

                            <div className="mt-4 bg-white/[0.02] p-3 rounded-xl border border-white/5">
                                <p className="text-[10px] leading-snug text-white/50 font-medium">
                                    {agent?.description.split('.')[0]}.
                                </p>
                            </div>
                        </div>

                        {/* Status Bar */}
                        <div className="px-5 mt-4">
                            <div className="flex p-1 bg-white/[0.02] rounded-xl border border-white/5 gap-1">
                                {tabs.map(t => (
                                    <button
                                        key={t.key}
                                        onClick={() => setActiveTab(t.key)}
                                        className={`flex-1 py-1.5 rounded-lg flex items-center justify-center gap-2 text-[8px] font-black uppercase tracking-widest transition-all ${activeTab === t.key
                                            ? 'bg-white/10 text-white border border-white/5'
                                            : 'text-white/20 hover:text-white/40'
                                            }`}
                                    >
                                        <span>{t.icon}</span> {t.label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Body */}
                        <div className="flex-1 overflow-y-auto px-5 py-5 custom-scrollbar">
                            {activeTab === 'overview' && (
                                <div className="space-y-6">
                                    <Section title="Configurações de Execução" icon="⚙️">
                                        {renderConfigControls()}
                                    </Section>

                                    <div className="grid grid-cols-2 gap-2">
                                        <Metric label="Resposta" value="12ms" sub="Velocidade de Processamento" color="var(--accent-purple)" />
                                        <Metric label="Disponibilidade" value="100%" sub="Status da conexão" color="var(--accent-green)" />
                                    </div>

                                    <Section title="Especificações Técnicas" icon="🎖️">
                                        <div className="grid grid-cols-1 gap-0.5 bg-white/[0.01] p-2 rounded-xl border border-white/[0.02]">
                                            <InfoRow label="Protocolo" value={agent?.tech === 'llm' ? 'DeepSeek-V3 Nexus Core' : 'Python 3.12 Engine'} />
                                            <InfoRow label="Camada de Dados" value={getLayer(agentId).toUpperCase()} />
                                            <InfoRow label="Grupo de Operação" value={crew.name} />
                                            <InfoRow label="Segurança" value="Criptografia TLS-1.3" />
                                        </div>
                                    </Section>

                                    {agent?.howItWorks && (
                                        <Section title="Manual de Operação (Passo a Passo)" icon="📖">
                                            <div className="space-y-1.5">
                                                {agent.howItWorks.map((step, i) => (
                                                    <div key={i} className="flex items-start gap-3 p-2.5 rounded-lg bg-white/[0.01] border border-white/[0.03] hover:bg-white/[0.04] transition-all group">
                                                        <span className="w-4 h-4 rounded-full bg-white/5 flex items-center justify-center text-[7px] font-black text-white/20 group-hover:text-white shrink-0">{i + 1}</span>
                                                        <p className="text-[9px] font-bold text-white/50 leading-tight group-hover:text-white/70">{step}</p>
                                                    </div>
                                                ))}
                                            </div>
                                        </Section>
                                    )}

                                    <div className="pt-2 flex gap-3 h-14">
                                        <button
                                            onClick={isActuallyRunning ? handleStop : handleRun}
                                            className={`flex-[3] rounded-2xl flex items-center justify-center gap-4 transition-all active:scale-95 shadow-2xl border relative overflow-hidden group ${isActuallyRunning
                                                ? 'bg-[var(--accent-red)]/10 border-[var(--accent-red)]/20 text-[var(--accent-red)]'
                                                : 'bg-[var(--accent-purple)]/10 border-[var(--accent-purple)]/20 text-[var(--accent-purple)] hover:bg-[var(--accent-purple)]/20 shadow-[0_0_30px_rgba(191,90,242,0.1)]'
                                                }`}
                                        >
                                            <div className="relative flex items-center justify-center">
                                                {isActuallyRunning ? (
                                                    <div className="relative flex items-center justify-center">
                                                        <div className="absolute w-6 h-6 border-2 border-[var(--accent-red)]/20 border-t-[var(--accent-red)] rounded-full animate-spinner-sticker" />
                                                        <span className="text-lg relative z-10">⏹️</span>
                                                    </div>
                                                ) : (
                                                    <span className="text-lg">
                                                        {systemStatus?.agents?.[agentId || '']?.checkpoint_years?.includes(selectedAno.toString()) ? '⏯️' : '▶️'}
                                                    </span>
                                                )}
                                            </div>
                                            <span className="text-[11px] font-black uppercase tracking-[0.2em]">
                                                {isActuallyRunning
                                                    ? 'Interromper Operação'
                                                    : (() => {
                                                        const isResume = systemStatus?.agents?.[agentId || '']?.checkpoint_years?.includes(selectedAno.toString());
                                                        const action = agentId === '1' ? 'Extrair' : agentId === '2' ? 'Purificar' : agentId === 'kaka' ? 'Arquivar' : 'Analisar';

                                                        // Tenta extrair o ano do arquivo carregado no preview (filename)
                                                        const currentFileYear = filename.match(/20\d{2}/)?.[0] || selectedAno.toString();

                                                        return isResume ? `Continuar ${action} ${currentFileYear}` : `Iniciar ${action} ${currentFileYear}`;
                                                    })()}
                                            </span>
                                        </button>

                                        {!isActuallyRunning && (
                                            <button
                                                onClick={async () => {
                                                    if (!agentId) return;
                                                    setLoading(true);
                                                    try {
                                                        const queryParams = new URLSearchParams({
                                                            ano: selectedAno.toString(), municipio: selectedMunicipio,
                                                            provider: selectedProvider, model: selectedModel, restart: 'true'
                                                        });
                                                        await fetch(`http://localhost:8001/api/run-agent/${agentId}?${queryParams.toString()}`, { method: 'POST' });
                                                    } finally { setLoading(false); }
                                                }}
                                                className="flex-1 rounded-2xl bg-white/5 border border-white/5 flex items-center justify-center text-lg hover:bg-white/10 transition-all active:scale-90"
                                                title={`Reiniciar ${selectedAno} do Zero`}
                                            >
                                                🔄
                                            </button>
                                        )}

                                        <button onClick={() => onOpenStudio(getLayer(agentId))} className="w-14 rounded-2xl bg-white/5 border border-white/5 hover:bg-white/10 transition-all flex items-center justify-center text-xl active:scale-90 shadow-xl">🕵️</button>
                                    </div>
                                </div>
                            )}

                            {activeTab === 'prompts' && (
                                <div className="space-y-4 h-full flex flex-col">
                                    <Section title="Instruções de Inteligência" icon="📜">
                                        <textarea
                                            value={prompt}
                                            onChange={(e) => setPrompt(e.target.value)}
                                            className="w-full flex-1 min-h-[300px] bg-black/40 border border-white/[0.03] rounded-xl p-4 text-[10px] font-mono-glass leading-relaxed text-[var(--accent-green)]/60 focus:outline-none focus:border-white/10 transition-all custom-scrollbar shadow-inner"
                                            placeholder="Descrevendo as diretrizes do agente..."
                                        />
                                    </Section>
                                    <button onClick={handleSave} disabled={loading} className="h-10 bg-[var(--accent-purple)]/10 border border-[var(--accent-purple)]/20 rounded-xl text-white/80 font-black text-[9px] uppercase tracking-widest hover:bg-[var(--accent-purple)]/20 transition-all">
                                        {loading ? 'SINCRONIZANDO...' : 'ATUALIZAR DIRETRIZES'}
                                    </button>
                                </div>
                            )}

                            {activeTab === 'logs' && (
                                <div className="space-y-6">

                                    {/* Console de Apuração Exclusivo do Agente */}
                                    <Section title={`Console Dedicado: ${agentLabel}`} icon="🖥️">
                                        <AgentTerminal agentId={agentId || ''} />
                                    </Section>

                                    {/* Visão Geral de Safras */}
                                    <Section title="Status do Pipeline por Safra" icon="📊">
                                        <div className="grid grid-cols-3 gap-2">
                                            {[2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025].map(ano => {
                                                const agentStatus = systemStatus?.agents?.[agentId || ''];
                                                const isExtracted = agentStatus?.completed_years?.includes(ano.toString());
                                                const isCheckpointed = agentStatus?.checkpoint_years?.includes(ano.toString());
                                                const icon = isExtracted ? '✅' : isCheckpointed ? '⏳' : '⬜';
                                                const colorClass = isExtracted
                                                    ? 'bg-[var(--accent-green)]/10 border-[var(--accent-green)]/30 text-[var(--accent-green)]'
                                                    : isCheckpointed
                                                        ? 'bg-orange-500/10 border-orange-500/30 text-orange-400'
                                                        : 'bg-white/[0.02] border-white/5 text-white/15';
                                                return (
                                                    <button
                                                        key={ano}
                                                        onClick={() => {
                                                            const entry = availableFiles.find((f: any) => f.name.includes(ano.toString()));
                                                            if (entry) fetchPreview(entry.name);
                                                            setSelectedAno(ano);
                                                        }}
                                                        className={`flex items-center justify-between px-2.5 py-2 rounded-xl border transition-all text-[9px] font-black ${colorClass}`}
                                                    >
                                                        <span>{icon} {ano}</span>
                                                        {isExtracted && <span className="text-[7px] opacity-60">PRONTO</span>}
                                                        {isCheckpointed && !isExtracted && <span className="text-[7px] opacity-60">PARCIAL</span>}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                        <div className="mt-3 flex justify-between items-center">
                                            <div className="flex gap-3">
                                                <span className="flex items-center gap-1 text-[6px] text-[var(--accent-green)] font-black uppercase">✅ Extraído</span>
                                                <span className="flex items-center gap-1 text-[6px] text-orange-400 font-black uppercase">⏳ Em Andamento</span>
                                                <span className="flex items-center gap-1 text-[6px] text-white/20 font-black uppercase">⬜ Pendente</span>
                                            </div>
                                            <span className="text-[6px] text-white/20 font-black uppercase">
                                                {systemStatus?.agents?.[agentId || '']?.completed_years?.length || 0} / 11 safras concluídas
                                            </span>
                                        </div>
                                    </Section>

                                    <Section title="Arquivos de Saída (Datalake)" icon="📁">
                                        <div className="grid grid-cols-1 gap-1.5">
                                            {availableFiles.length > 0 ? (
                                                availableFiles.map((f: any) => {
                                                    // Extrai o ano do nome do arquivo
                                                    const yearMatch = f.name.match(/20\d{2}/);
                                                    const fileYear = yearMatch ? yearMatch[0] : null;
                                                    const agentStatus = systemStatus?.agents?.[agentId || ''];
                                                    const yearExtracted = fileYear && agentStatus?.completed_years?.includes(fileYear);
                                                    const yearCheckpoint = fileYear && agentStatus?.checkpoint_years?.includes(fileYear);
                                                    const isCheckpointFile = f.name.includes('checkpoint');

                                                    return (
                                                        <div key={f.name} className="flex flex-col gap-1">
                                                            <div className="flex items-center gap-1">
                                                                <button
                                                                    onClick={() => {
                                                                        const yearMatch = f.name.match(/20\d{2}/);
                                                                        const targetYear = yearMatch ? parseInt(yearMatch[0]) : selectedAno;
                                                                        setSelectedAno(targetYear);
                                                                        fetchPreview(f.name);
                                                                    }}
                                                                    className={`flex-1 flex items-center justify-between p-2.5 rounded-xl border transition-all ${filename === f.name ? 'bg-[var(--accent-green)]/10 border-[var(--accent-green)]/40' : 'bg-white/5 border-white/5 hover:bg-white/10'}`}
                                                                >
                                                                    <div className="flex items-center gap-3">
                                                                        <span className="text-base">{isCheckpointFile ? '⏳' : '📄'}</span>
                                                                        <div className="text-left">
                                                                            <div className={`text-[10px] font-black tracking-tight ${filename === f.name ? 'text-[var(--accent-green)]' : 'text-white/70'}`}>{f.name}</div>
                                                                            <div className="text-[7px] text-white/20 font-black uppercase mt-0.5">{f.size} • {f.modified}</div>
                                                                        </div>
                                                                    </div>
                                                                    <div className="flex items-center gap-2">
                                                                        {fileYear && (
                                                                            <span className={`text-[8px] font-black px-1.5 py-0.5 rounded-lg ${yearExtracted && !isCheckpointFile
                                                                                ? 'bg-[var(--accent-green)]/20 text-[var(--accent-green)]'
                                                                                : yearCheckpoint || isCheckpointFile
                                                                                    ? 'bg-orange-500/20 text-orange-400'
                                                                                    : 'bg-white/5 text-white/30'
                                                                                }`}>
                                                                                {fileYear}
                                                                            </span>
                                                                        )}
                                                                        {filename === f.name && <div className="w-1.5 h-1.5 rounded-full bg-[var(--accent-green)] animate-pulse shadow-[0_0_10px_rgba(50,205,50,0.5)]" />}
                                                                    </div>
                                                                </button>
                                                                <button
                                                                    onClick={() => onOpenStudio(getLayer(agentId))}
                                                                    className="w-10 h-10 rounded-xl bg-white/5 border border-white/5 flex items-center justify-center text-xs hover:bg-white/10 transition-all hover:scale-105 active:scale-95 group"
                                                                    title="Abrir no Data Studio"
                                                                >
                                                                    <span className="group-hover:filter group-hover:drop-shadow-[0_0_5px_rgba(255,255,255,0.5)]">🕵️</span>
                                                                </button>
                                                            </div>
                                                            {filename === f.name && fileStats && (
                                                                <div className="px-3 py-3 bg-black/60 rounded-xl border border-[var(--accent-green)]/20 mt-1 border-dashed animate-in fade-in slide-in-from-top-2 duration-300">
                                                                    <div className="text-[7px] font-black text-[var(--accent-green)]/40 uppercase mb-3 tracking-[0.2em] flex items-center gap-2">
                                                                        <span className="w-1 h-1 rounded-full bg-[var(--accent-green)] animate-pulse" />
                                                                        Relatório de Auditoria Fiel
                                                                    </div>

                                                                    <div className="space-y-2">
                                                                        <div className="grid grid-cols-2 gap-2">
                                                                            <div className="p-2 bg-white/[0.02] rounded-lg border border-white/[0.03]">
                                                                                <div className="text-[6px] text-white/20 uppercase font-black mb-1">Total de Registros</div>
                                                                                <div className="text-xs font-mono-glass text-white/80">{fileStats.total_records.toLocaleString()}</div>
                                                                            </div>
                                                                            <div className="p-2 bg-white/[0.02] rounded-lg border border-white/[0.03]">
                                                                                <div className="text-[6px] text-white/20 uppercase font-black mb-1">Duplicatas</div>
                                                                                <div className="text-xs font-mono-glass text-[var(--accent-red)]">{fileStats.duplicatas}</div>
                                                                            </div>
                                                                        </div>

                                                                        <div className="grid grid-cols-2 gap-2">
                                                                            <div className="p-2 bg-white/[0.02] rounded-lg border border-white/[0.03]">
                                                                                <div className="text-[6px] text-white/20 uppercase font-black mb-1">Tokens Estimados</div>
                                                                                <div className="text-xs font-mono-glass text-[var(--accent-blue)]">{fileStats.tokens.toLocaleString()}</div>
                                                                            </div>
                                                                            <div className="p-2 bg-white/[0.02] rounded-lg border border-white/[0.03]">
                                                                                <div className="text-[6px] text-white/20 uppercase font-black mb-1">Codificação</div>
                                                                                <div className="text-[9px] font-mono-glass text-[var(--accent-green)]">{fileStats.encoding}</div>
                                                                            </div>
                                                                        </div>

                                                                        {/* Normalização Detalhada uma a uma */}
                                                                        {fileStats.normalizations && fileStats.normalizations.length > 0 && (
                                                                            <div className="mt-3 pt-3 border-t border-white/5">
                                                                                <div className="text-[6px] text-white/20 uppercase font-black mb-2 tracking-widest">Normalização Detalhada (Step-by-Step)</div>
                                                                                <div className="space-y-1.5">
                                                                                    {fileStats.normalizations.map((step: string, idx: number) => (
                                                                                        <div key={idx} className="flex items-start gap-2 group/step">
                                                                                            <div className="w-3 h-3 rounded-full bg-[var(--accent-green)]/10 border border-[var(--accent-green)]/30 flex items-center justify-center text-[6px] text-[var(--accent-green)] shrink-0 mt-0.5 group-hover/step:bg-[var(--accent-green)]/20 transition-all">
                                                                                                {idx + 1}
                                                                                            </div>
                                                                                            <span className="text-[8px] text-white/50 leading-tight group-hover/step:text-white/80 transition-all">{step}</span>
                                                                                        </div>
                                                                                    ))}
                                                                                </div>
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            )}
                                                        </div>
                                                    );
                                                })
                                            ) : (
                                                <div className="text-center py-10 bg-white/[0.01] rounded-2xl border border-dashed border-white/5 text-white/10 text-[8px] font-black uppercase tracking-widest">Aguardando geração de arquivos...</div>
                                            )}
                                        </div>
                                    </Section>

                                    {inputData && (
                                        <Section
                                            title="Data Health & Sourcing Grid"
                                            icon="📊"
                                            actions={
                                                <div className="flex items-center gap-3">
                                                    {/* Quick Stats Integration */}
                                                    <div className="flex gap-3 px-3 py-1 bg-white/[0.03] rounded-lg border border-white/5 text-[8px] font-mono-glass">
                                                        <div className="flex gap-1.5 items-center">
                                                            <span className="text-white/20">REG:</span>
                                                            <span className="text-[var(--accent-blue)] font-black">{fileStats?.total_records?.toLocaleString() || '0'}</span>
                                                        </div>
                                                        <div className="flex gap-1.5 items-center">
                                                            <span className="text-white/20">TOKENS:</span>
                                                            <span className="text-[var(--accent-green)] font-black">{fileStats?.tokens?.toLocaleString() || '0'}</span>
                                                        </div>
                                                        <div className="flex gap-1.5 items-center">
                                                            <span className="text-white/20">CUSTO:</span>
                                                            <span className="text-[var(--orange)] font-black">${(((fileStats?.tokens || 0) * 0.000001)).toFixed(4)}</span>
                                                        </div>
                                                    </div>

                                                    <div className="flex gap-2">
                                                        <button
                                                            onClick={() => setViewMode(viewMode === 'grid' ? 'code' : 'grid')}
                                                            className="px-3 py-1 bg-white/5 border border-white/10 rounded-lg text-[7px] font-black uppercase tracking-widest hover:bg-white/10 transition-all text-white/50"
                                                        >
                                                            {viewMode === 'grid' ? '📟 Ver Código' : '📊 Ver Grid'}
                                                        </button>
                                                        <button
                                                            onClick={() => {
                                                                navigator.clipboard.writeText(JSON.stringify(inputData, null, 2));
                                                                alert('Dados copiados para a área de transferência! 📋');
                                                            }}
                                                            className="px-3 py-1 bg-[var(--accent-green)]/10 border border-[var(--accent-green)]/20 rounded-lg text-[7px] font-black uppercase tracking-widest hover:bg-[var(--accent-green)]/20 transition-all text-[var(--accent-green)]"
                                                        >
                                                            📋 Copiar Tudo
                                                        </button>
                                                    </div>
                                                </div>
                                            }
                                        >
                                            {viewMode === 'code' ? (
                                                <div className="animate-in fade-in zoom-in-95 duration-300">
                                                    <div className="bg-black/60 rounded-2xl border border-white/5 p-4 overflow-hidden shadow-2xl">
                                                        <CodePreview code={JSON.stringify(inputData, null, 2)} />
                                                    </div>
                                                </div>
                                            ) : (
                                                <DataPreviewStudio
                                                    data={inputData}
                                                    completeness={fileStats?.completeness}
                                                />
                                            )}
                                        </Section>
                                    )}
                                </div>
                            )}
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );
};

export default AgentDetailsDrawer;
