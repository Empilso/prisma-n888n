import React, { useState, useEffect, useMemo } from 'react';
// v3.2 — year cards always visible + luxury pill style
import { motion, AnimatePresence } from 'framer-motion';
import {
    Cpu, Shield, Database, FileJson, Zap, Network, Target, ChevronRight,
    Terminal, Eye, RotateCcw, StopCircle, PlayCircle, Microscope, CheckCircle2,
    Clock, AlertCircle, HardDrive, Info, Layers, BookOpen, TrendingUp, Search
} from 'lucide-react';
import AgentAvatar from './AgentAvatar';
import DataPreviewStudio from './DataPreviewStudio';
import AgentTerminal from './AgentTerminal';
import PeleUploadPanel from './PeleUploadPanel';
import { crewDefs } from './crewDefs';

// ─── Types ────────────────────────────────────────────────────────────────────
interface AgentDetailsDrawerProps {
    isOpen: boolean;
    onClose: () => void;
    agentId: string | null;
    agentLabel: string;
    selectedCrewId: string;
    onOpenStudio: (layer: 'bronze' | 'prata' | 'ouro' | 'kaka') => void;
    inputReady?: boolean;
    systemStatus?: any;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
const modelProviders = [
    { id: 'groq', name: 'Groq', icon: Zap, models: ['llama-3.3-70b-versatile', 'mixtral-8x7b-32768'], desc: 'Velocidade extrema' },
    { id: 'deepseek', name: 'DeepSeek', icon: Cpu, models: ['deepseek-chat', 'deepseek-reasoner'], desc: 'Raciocínio avançado' },
    { id: 'ollama', name: 'Ollama', icon: HardDrive, models: ['llama3.1:8b', 'mistral:latest'], desc: 'Local & privado' },
    { id: 'openrouter', name: 'OpenRouter', icon: Network, models: ['google/gemini-pro-1.5', 'anthropic/claude-3-haiku'], desc: 'Multi-modelos' },
];

const getLayer = (agentId: string | null): 'bronze' | 'prata' | 'ouro' | 'kaka' => {
    if (agentId === '1') return 'bronze';
    if (agentId === '2') return 'prata';
    if (agentId === '3' || agentId === 'kaka') return 'kaka';
    return 'ouro';
};

// ─── Year Pill ───────────────────────────────────────────────────────────────
const YearPill = ({
    label, active, done, partial, onClick, tooltip
}: { label: string; active: boolean; done?: boolean; partial?: boolean; onClick: () => void; tooltip?: string }) => {
    const base = 'relative px-3.5 py-1.5 rounded-xl text-[11px] font-bold tracking-wide transition-all select-none border shadow-sm cursor-pointer';
    let colorClass = '';
    if (active) {
        colorClass = 'bg-gradient-to-br from-blue-500/25 to-purple-500/15 text-blue-200 border-blue-400/50 shadow-[0_0_14px_rgba(99,102,241,0.25)] scale-105';
    } else if (done) {
        colorClass = 'bg-emerald-500/10 text-emerald-300 border-emerald-400/25 hover:border-emerald-400/50 hover:scale-105';
    } else if (partial) {
        colorClass = 'bg-amber-500/10 text-amber-300 border-amber-400/25 hover:border-amber-400/50 hover:scale-105';
    } else {
        colorClass = 'bg-white/[0.04] text-white/40 border-white/[0.09] hover:bg-white/[0.07] hover:border-white/25 hover:text-white/70 hover:scale-105';
    }
    return (
        <button onClick={onClick} title={tooltip} className={`${base} ${colorClass}`}>
            {label}
            {done && !active && <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-400 border border-black" />}
            {partial && !done && !active && <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-amber-400 border border-black animate-pulse" />}
        </button>
    );
};

// ─── Compact Pill (para Linhagem / Safras) ────────────────────────────────────
const Pill = ({
    label, active, done, partial, onClick, tooltip
}: { label: string; active: boolean; done?: boolean; partial?: boolean; onClick: () => void; tooltip?: string }) => (
    <button
        onClick={onClick}
        title={tooltip}
        className={`relative px-2.5 py-1 rounded-full text-[9px] font-bold tracking-wide transition-all select-none border ${
            active
                ? 'bg-blue-500/15 text-blue-300 border-blue-400/40 shadow-[0_0_12px_rgba(59,130,246,0.2)]'
                : done
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-400/20'
                    : partial
                        ? 'bg-amber-500/10 text-amber-400 border-amber-400/20'
                        : 'bg-white/[0.03] text-white/30 border-white/[0.06] hover:border-white/20 hover:text-white/60'
        }`}
    >
        {label}
        {done && !active && <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-emerald-400 border border-black" />}
        {partial && !done && !active && <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-amber-400 border border-black animate-pulse" />}
    </button>
);

const DnaRow = ({ icon: Icon, label, value, tooltip, accent }: {
    icon: any; label: string; value: string; tooltip?: string; accent?: string
}) => (
    <div className="flex items-center gap-3 py-2.5 px-3 rounded-xl hover:bg-white/[0.02] transition-all group" title={tooltip}>
        <div className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0 border bg-white/[0.04] border-white/[0.06]">
            <Icon size={15} className="text-white/50" />
        </div>
        <div className="flex-1 min-w-0">
            <div className="text-[10px] font-black text-white/30 uppercase tracking-[0.12em] flex items-center gap-1">
                {label}
                {tooltip && <Info size={9} className="opacity-0 group-hover:opacity-60 transition-opacity" />}
            </div>
            <div className="text-[13px] font-semibold text-white/70 truncate mt-0.5 leading-tight">{value}</div>
        </div>
    </div>
);

const StatusBadge = ({ done, partial, running }: { done: boolean; partial: boolean; running: boolean }) => {
    if (running) return <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/15 border border-blue-400/25 text-blue-300 text-[11px] font-black uppercase tracking-wide animate-pulse"><span className="w-1.5 h-1.5 rounded-full bg-blue-400" />Operando</span>;
    if (done) return <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/15 border border-emerald-400/25 text-emerald-300 text-[11px] font-black uppercase tracking-wide"><CheckCircle2 size={10} />Concluído</span>;
    if (partial) return <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/15 border border-amber-400/25 text-amber-300 text-[11px] font-black uppercase tracking-wide animate-pulse"><Clock size={10} />Em Andamento</span>;
    return <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/[0.04] border border-white/[0.06] text-white/30 text-[11px] font-black uppercase tracking-wide"><AlertCircle size={10} />Aguardando</span>;
};

const CodePreview = ({ code }: { code: string }) => {
    const linesCount = code.split('\n').length;
    return (
        <div className="bg-[#060608] border border-white/[0.04] rounded-2xl overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between px-3 py-2 border-b border-white/[0.04] bg-white/[0.01]">
                <div className="flex gap-1.5">
                    <div className="w-2 h-2 rounded-full bg-white/[0.06]" /><div className="w-2 h-2 rounded-full bg-white/[0.06]" /><div className="w-2 h-2 rounded-full bg-white/[0.06]" />
                </div>
                <div className="flex items-center gap-2">
                    <FileJson size={10} className="text-white/20" />
                    <span className="text-[7px] text-white/20 font-mono tracking-wider">output.json</span>
                    <span className="text-[7px] text-emerald-400/60 font-mono">{linesCount}L</span>
                </div>
            </div>
            <div className="h-[200px] overflow-auto flex text-[8px]">
                <div className="w-7 bg-black/20 border-r border-white/[0.03] flex flex-col items-end pr-1.5 py-2 shrink-0 select-none">
                    {Array.from({ length: Math.min(linesCount, 500) }).map((_, i) => (
                        <span key={i} className="text-white/10 leading-relaxed font-mono">{i + 1}</span>
                    ))}
                </div>
                <pre className="p-3 text-emerald-400/70 leading-relaxed flex-1 overflow-x-auto whitespace-pre font-mono">{code}</pre>
            </div>
        </div>
    );
};

// ─── ALL_YEARS — lista fixa, sempre visível ───────────────────────────────────
const ALL_YEARS = [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025];

// ─── Main Component ───────────────────────────────────────────────────────────
const AgentDetailsDrawer = ({ isOpen, onClose, agentId, agentLabel, selectedCrewId, onOpenStudio, inputReady, systemStatus }: AgentDetailsDrawerProps) => {
    const [viewMode, setViewMode] = useState<'grid' | 'code'>('grid');
    const [inputData, setInputData] = useState<any>(null);
    const [filename, setFilename] = useState('');
    const [fileStats, setFileStats] = useState<any>(null);
    const [availableFiles, setAvailableFiles] = useState<any[]>([]);
    const [availableBronzeFiles, setAvailableBronzeFiles] = useState<any[]>([]);
    const [selectedBronzeFile, setSelectedBronzeFile] = useState<string>('');
    const [pageLimit, setPageLimit] = useState<number>(3474);
    const [agentManifest, setAgentManifest] = useState<any>(null);
    const [prompt, setPrompt] = useState('');
    const [loading, setLoading] = useState(false);

    const [selectedAno, setSelectedAno] = useState<number | 'all'>(2024);
    const [selectedMunicipio, setSelectedMunicipio] = useState('Salvador');
    const [selectedProvider, setSelectedProvider] = useState('groq');
    const [selectedModel, setSelectedModel] = useState('llama-3.3-70b-versatile');

    const crew = useMemo(() => crewDefs.find(c => c.id === selectedCrewId) || crewDefs[0], [selectedCrewId]);
    const agent = useMemo(() => crew.agents.find(a => a.id === agentId), [crew, agentId]);
    const isActuallyRunning = systemStatus?.agents?.[agentId || '']?.status === 'running';

    useEffect(() => {
        if (isOpen && agentId) {
            fetchManifest();
            fetchPrompt();
            fetchAvailableFiles();
            if (['2', 'kaka', '3', 'ronaldo', 'dunga'].includes(agentId)) fetchBronzeFiles();
            fetchPreview();
        }
    }, [isOpen, agentId, selectedCrewId]);

    const fetchBronzeFiles = async () => {
        try {
            const inputLayer = agentId === 'dunga' ? 'ouro' : (agentId === 'kaka' || agentId === '3' || agentId === 'ronaldo') ? 'prata' : 'bronze';
            const res = await fetch(`http://localhost:8003/api/agent/${agentId}/input-files?layer=${inputLayer}`);
            const data = await res.json();
            setAvailableBronzeFiles(data.files || []);
            if (data.files?.length > 0 && !selectedBronzeFile) setSelectedBronzeFile(data.files[0].name);
        } catch (e) {}
    };

    const fetchManifest = async () => {
        try {
            setAgentManifest(null);
            const res = await fetch(`http://localhost:8003/api/agent-manifest/${agentId}`);
            const data = await res.json();
            if (data.status === 'ok') setAgentManifest(data.manifest);
        } catch (e) {}
    };

    const fetchPrompt = async () => {
        try {
            const res = await fetch(`http://localhost:8003/api/get-prompt/${agentId}`);
            const data = await res.json();
            setPrompt(data.prompt || '');
        } catch (e) {}
    };

    const fetchAvailableFiles = async () => {
        if (!agentId) return;
        try {
            const res = await fetch(`http://localhost:8003/api/datalake/files`);
            const json = await res.json();
            if (json.status === 'ok') {
                const layer = getLayer(agentId);
                setAvailableFiles(json.files.filter((f: any) => f.layer === layer));
            }
        } catch (e) {}
    };

    const fetchPreview = async (targetFile?: string) => {
        try {
            const layer = getLayer(agentId);
            const url = targetFile
                ? `http://localhost:8003/api/datalake/files/${layer}/${targetFile}`
                : `http://localhost:8003/api/agent-data/${layer}`;
            const res = await fetch(url);
            const json = await res.json();
            const normalized = json.data?.records || (Array.isArray(json.data) ? json.data : []);
            setInputData(normalized);
            const finalFname = targetFile || json.filename || filename;
            setFilename(finalFname);
            if (finalFname) {
                setFileStats(null);
                const sResp = await fetch(`http://localhost:8003/api/datalake/stats/${agentId}?filename=${finalFname}`);
                const sData = await sResp.json();
                if (sData.status === 'ok') setFileStats(sData);
            }
        } catch (e) {}
    };

    const handleRun = async () => {
        if (!agentId) return;
        setLoading(true);
        try {
            const yearMatch = filename.match(/20\d{2}/);
            const yearToRun = yearMatch ? yearMatch[0] : selectedAno.toString();
            const isZidaneD = agentId === 'zidane_d';
            const qp = new URLSearchParams();
            if (!isZidaneD) {
                qp.append('ano', yearToRun);
                qp.append('municipio', selectedMunicipio);
                qp.append('provider', selectedProvider);
                qp.append('model', selectedModel);
            }
            if (agentId === '2' && selectedBronzeFile) qp.append('filename', selectedBronzeFile);
            if ((agentId === '3' || agentId === 'kaka') && pageLimit > 0) qp.append('limit', pageLimit.toString());
            await fetch(`http://localhost:8003/api/run-agent/${agentId}?${qp.toString()}`, { method: 'POST' });
        } catch (e) {}
        setLoading(false);
    };

    const handleStop = async () => {
        if (!agentId) return;
        try { await fetch(`http://localhost:8003/api/stop-agent/${agentId}`, { method: 'POST' }); } catch (e) {}
    };

    const handleRestart = async () => {
        if (!agentId) return;
        setLoading(true);
        try {
            const qp = new URLSearchParams();
            if (agentId !== 'zidane_d') { qp.append('ano', selectedAno.toString()); qp.append('provider', selectedProvider); qp.append('model', selectedModel); }
            qp.append('restart', 'true');
            await fetch(`http://localhost:8003/api/run-agent/${agentId}?${qp.toString()}`, { method: 'POST' })
        } finally { setLoading(false); }
    };

    // ─── Derived state ─────────────────────────────────────────────────────────
    const vGeral = agentManifest?.visao_geral || {};
    const apuracao = agentManifest?.apuracao || {};
    const techStack: string[] = (vGeral.protocolo_tecnico || agent?.tech || 'Python').split('+').map((t: string) => t.trim());
    const camada: string = vGeral.camada_dados || getLayer(agentId).toUpperCase();
    const seguranca: string = vGeral.seguranca || 'TLS-1.3';
    const especialidade: string = vGeral.especialidade || agent?.role || 'Agente Extrator';
    const missao: string = vGeral.missao || agent?.description?.split('.')[0] || '—';
    const diretrizes: string[] = agentManifest?.diretrizes || [];
    const safras: string[] = apuracao.safras_suportadas || [];

    const agentStatus = systemStatus?.agents?.[agentId || ''];
    const completedYears: string[] = agentStatus?.completed_years || [];
    const checkpointYears: string[] = agentStatus?.checkpoint_years || [];
    const inputYears: string[] = agentStatus?.available_input_years || [];
    const currentRawAno = selectedAno.toString();

    const isTargetDone = safras.includes('all') ? completedYears.length > 0 : completedYears.includes(currentRawAno);
    const isTargetPartial = safras.includes('all') ? checkpointYears.length > 0 : checkpointYears.includes(currentRawAno);
    const isSourceReady = safras.includes('all') ? true : (inputYears.length > 0 ? inputYears.includes(currentRawAno) : true);
    const isRunningPulse = isActuallyRunning || isTargetPartial;
    const isGlobalDone = completedYears.length > 0;

    const resolvePath = (p: string) => p
        ? p.replace('{ano}', currentRawAno).replace('{num}', currentRawAno)
        : '';

    const rawEntrada: string = apuracao.entrada_esperada || '';
    const rawSaida: string = apuracao.saida_esperada || '';
    const sourceFile = resolvePath(rawEntrada) || 'Data Lake';
    const targetFile = resolvePath(rawSaida) || 'Banco de Dados';

    const runLabel = (() => {
        const zLabels: Record<string, string> = { zidane_a: 'Coletar IDs', zidane_b: 'Deep Scrape', zidane_c: 'Consolidar Hub' };
        const act = zLabels[agentId || ''] || (agentId === '1' ? 'Extrair' : agentId === '2' ? 'Purificar' : agentId === 'kaka' ? 'Auditar' : 'Executar');
        const isZ = (agentId || '').startsWith('zidane');
        const yr = isZ ? '' : ` ${filename.match(/20\d{2}/)?.[0] || selectedAno}`;
        return `${act}${yr}`;
    })();

    const needsYear = ['1', '3', '4', '5', '6', '10'].includes(selectedCrewId) && agentId === '1';
    const needsLegislatura = agentId === 'zidane_a' || agentId === 'zidane_b';
    const needsCity = selectedCrewId === '9' && agentId === '1';
    const needsLLM = agent?.tech === 'llm' && agentId !== 'zidane_c';
    const isZidaneCrew = selectedCrewId === '0';

    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    {/* Backdrop */}
                    <motion.div
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        onClick={onClose}
                        className="fixed inset-0 bg-black/50 backdrop-blur-[6px] z-[100]"
                    />

                    {/* Drawer */}
                    <motion.div
                        initial={{ x: '100%' }}
                        animate={{ x: 0 }}
                        exit={{ x: '100%' }}
                        transition={{ type: 'spring', damping: 38, stiffness: 380 }}
                        className="fixed right-0 top-0 bottom-0 w-[75vw] bg-[#070709]/95 backdrop-blur-2xl border-l border-white/[0.05] shadow-2xl z-[101] flex flex-col overflow-hidden font-condensed"
                    >
                        {/* ══ HEADER ══════════════════════════════════════════════ */}
                        <div className="px-6 py-4 border-b border-white/[0.05] bg-white/[0.008] flex items-center gap-4 shrink-0">
                            <div className="p-0.5 rounded-2xl bg-gradient-to-br from-blue-500/30 to-purple-500/10 border border-white/10 shrink-0">
                                <AgentAvatar agentId={agentId || '1'} size={52} skinVariant={agentStatus?.skin_variant} />
                            </div>
                            <div className="flex-1 min-w-0">
                                <h2 className="text-[20px] font-black text-white tracking-tight uppercase truncate leading-tight">{agent?.name?.split(':')[0] || agentLabel}</h2>
                                <p className="text-[12px] text-white/35 font-semibold uppercase tracking-widest mt-0.5">{agent?.role}</p>
                            </div>
                            <StatusBadge done={isGlobalDone} partial={isTargetPartial} running={isActuallyRunning} />
                            <button onClick={onClose} className="w-7 h-7 rounded-full flex items-center justify-center hover:bg-white/[0.06] text-white/20 hover:text-white/60 transition-all ml-2">
                                <span className="text-lg leading-none">×</span>
                            </button>
                        </div>

                        {/* ══ BODY — 2 COLUNAS ═════════════════════════════════ */}
                        <div className="flex-1 overflow-hidden flex">

                            {/* ── COLUNA ESQUERDA: O CÉREBRO (30%) ─────────── */}
                            <div className="w-[30%] shrink-0 border-r border-white/[0.05] overflow-y-auto custom-scrollbar py-5 flex flex-col gap-6">

                                {/* DNA Group */}
                                <div className="px-4">
                                    <div className="flex items-center gap-2 mb-3 px-1">
                                        <Layers size={13} className="text-white/30" />
                                        <span className="text-[11px] font-black text-white/30 uppercase tracking-[0.15em]">DNA do Agente</span>
                                        <span className="flex-1 h-px bg-white/[0.04]" />
                                    </div>
                                    <div className="space-y-0.5">
                                        <DnaRow icon={Cpu} label="Motor" value={techStack.join(' + ')} tooltip="Tecnologias que executam este agente" accent="#bf5af2" />
                                        <DnaRow icon={Shield} label="Segurança" value={seguranca} tooltip="Protocolo de proteção da conexão de dados" accent="#32ade6" />
                                        <DnaRow icon={Database} label="Camada" value={camada} tooltip={camada === 'BRONZE' ? 'Dados brutos originais do portal' : camada === 'PRATA' ? 'Dados limpos e normalizados' : 'Dados refinados prontos para IA'} accent="#30d158" />
                                        <DnaRow icon={Target} label="Especialidade" value={especialidade} tooltip="Função principal deste agente no pipeline" />
                                        <DnaRow icon={TrendingUp} label="Missão" value={missao} tooltip="Objetivo final desta operação" />
                                    </div>
                                </div>

                                {/* Protocolo / Diretrizes */}
                                {diretrizes.length > 0 && (
                                    <div className="px-4">
                                        <div className="flex items-center gap-2 mb-3 px-1">
                                            <BookOpen size={13} className="text-white/30" />
                                            <span className="text-[11px] font-black text-white/30 uppercase tracking-[0.15em]">Protocolo</span>
                                            <span className="flex-1 h-px bg-white/[0.04]" />
                                        </div>
                                        <div className="space-y-1.5">
                                            {diretrizes.map((d: string, idx: number) => (
                                                <div key={idx} className="flex items-start gap-2.5 px-3 py-2.5 rounded-xl bg-white/[0.015] border border-white/[0.04] hover:border-white/[0.08] transition-all group">
                                                    <div className="w-5 h-5 rounded-full bg-blue-500/10 border border-blue-400/20 flex items-center justify-center shrink-0 mt-0.5">
                                                        <span className="text-[9px] font-black text-blue-400">{idx + 1}</span>
                                                    </div>
                                                    <span className="text-[12px] font-medium text-white/45 leading-snug group-hover:text-white/65 transition-colors">{d}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {!agentManifest && (
                                    <div className="px-4 text-center py-6">
                                        <div className="w-5 h-5 border border-white/10 border-t-blue-400/50 rounded-full animate-spin mx-auto mb-2" />
                                        <p className="text-[7px] text-white/20 uppercase tracking-widest">Carregando manifesto...</p>
                                    </div>
                                )}
                            </div>

                            {/* ── COLUNA DIREITA: A OPERAÇÃO (70%) ─────────── */}
                            <div className="flex-1 overflow-y-auto custom-scrollbar px-6 py-5 space-y-6">

                                {/* LINHAGEM HORIZONTAL */}
                                <div>
                                    <div className="flex items-center gap-2 mb-4">
                                        <Microscope size={13} className="text-white/30" />
                                        <span className="text-[11px] font-black text-white/30 uppercase tracking-[0.15em]">Linhagem de Dados</span>
                                        <span className="flex-1 h-px bg-white/[0.04]" />
                                        {isRunningPulse && (
                                            <span className="text-[10px] font-black text-blue-400 uppercase flex items-center gap-1 animate-pulse">
                                                <span className="w-1.5 h-1.5 rounded-full bg-blue-400" /> Operação Ativa
                                            </span>
                                        )}
                                    </div>

                                    <div className="grid grid-cols-[1fr_64px_1fr] items-center gap-0">
                                        {/* SOURCE */}
                                        <div className={`p-4 rounded-2xl border transition-all ${isSourceReady ? 'bg-white/[0.015] border-white/[0.05]' : 'bg-amber-500/[0.04] border-amber-500/15'}`}>
                                            <div className="flex items-center gap-2 mb-2">
                                                <div className="w-7 h-7 rounded-xl bg-white/[0.04] border border-white/[0.06] flex items-center justify-center">
                                                    <HardDrive size={14} className="text-white/40" />
                                                </div>
                                                <div>
                                                    <div className="text-[11px] font-black text-white/30 uppercase tracking-wider">Fonte</div>
                                                    <div className="text-[10px] text-white/20">Arquivo de entrada</div>
                                                </div>
                                            </div>
                                            <div className="text-[11px] font-mono text-white/55 truncate mb-2" title={sourceFile}>{sourceFile}</div>
                                            {isSourceReady
                                                ? <span className="text-[10px] font-black px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-400/20 uppercase flex items-center gap-1 w-fit"><CheckCircle2 size={9} /> No Disco</span>
                                                : <span className="text-[10px] font-black px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-400/20 uppercase flex items-center gap-1 w-fit"><Clock size={9} /> Aguardando</span>
                                            }
                                        </div>

                                        {/* CONNECTOR + SELECTOR */}
                                        <div className="flex flex-col items-center gap-1 px-2">
                                            <div className={`w-full h-[1.5px] rounded ${isRunningPulse ? 'bg-blue-400/60 animate-pulse' : 'bg-white/[0.06]'}`} />
                                            <div className={`p-2 rounded-xl border transition-all w-full ${isRunningPulse ? 'bg-blue-500/10 border-blue-400/25' : 'bg-white/[0.02] border-white/[0.06]'}`}>
                                                <div className="text-[10px] font-black text-blue-400/80 uppercase tracking-wide text-center mb-1.5">Contexto</div>
                                                {safras.length > 0 ? (
                                                    <div className="flex flex-col gap-1 items-center">
                                                        {safras.map((safraRaw: any) => {
                                                            const safra = String(safraRaw);
                                                            const rawNum = safra.replace(/\D/g, '');
                                                            const isSel = currentRawAno === rawNum || (safra === 'all' && selectedAno === 'all');
                                                            const isDone = rawNum ? completedYears.includes(rawNum) : false;
                                                            const isPartial = rawNum ? checkpointYears.includes(rawNum) : false;
                                                            return (
                                                                <Pill
                                                                    key={safra}
                                                                    label={safra}
                                                                    active={isSel}
                                                                    done={isDone && !isSel}
                                                                    partial={isPartial && !isDone && !isSel}
                                                                    onClick={() => {
                                                                        if (safra === 'all') { setSelectedAno('all'); return; }
                                                                        const n = parseInt(rawNum);
                                                                        if (n) setSelectedAno(n);
                                                                    }}
                                                                    tooltip={isDone ? 'Concluído ✓' : isPartial ? 'Em andamento' : 'Pendente'}
                                                                />
                                                            );
                                                        })}
                                                    </div>
                                                ) : (
                                                    <div className="text-[6px] text-white/20 text-center">Auto</div>
                                                )}
                                            </div>
                                            <ChevronRight size={10} className={`${isRunningPulse ? 'text-blue-400/60' : 'text-white/10'}`} />
                                        </div>

                                        {/* TARGET */}
                                        <div className={`p-4 rounded-2xl border transition-all ${isTargetDone ? 'bg-emerald-500/[0.02] border-emerald-400/15' : 'bg-white/[0.015] border-white/[0.05]'}`}>
                                            <div className="flex items-center gap-2 mb-2">
                                                <div className={`w-7 h-7 rounded-xl border flex items-center justify-center ${isTargetDone ? 'bg-emerald-500/10 border-emerald-400/20' : 'bg-white/[0.04] border-white/[0.06]'}`}>
                                                    <FileJson size={14} className={isTargetDone ? 'text-emerald-400' : 'text-white/40'} />
                                                </div>
                                                <div>
                                                    <div className="text-[11px] font-black text-white/30 uppercase tracking-wider">Destino</div>
                                                    <div className="text-[10px] text-white/20">Arquivo gerado</div>
                                                </div>
                                            </div>
                                            <div className={`text-[11px] font-mono truncate mb-2 ${isTargetDone ? 'text-emerald-400' : 'text-white/50'}`} title={targetFile}>{targetFile}</div>
                                            {isTargetDone
                                                ? <span className="text-[10px] font-black px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-400/20 uppercase flex items-center gap-1 w-fit"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> Gerado</span>
                                                : isTargetPartial
                                                    ? <span className="text-[10px] font-black px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-400/20 uppercase flex items-center gap-1 w-fit animate-pulse"><span className="w-1.5 h-1.5 rounded-full bg-amber-400" /> Escrevendo...</span>
                                                    : <span className="text-[10px] font-black px-2.5 py-0.5 rounded-full bg-white/[0.04] text-white/20 border border-white/[0.06] uppercase">Pendente</span>
                                            }
                                        </div>
                                    </div>
                                </div>

                                {/* ══ FILTRO DE ANOS — sempre visível ═══════════════════════ */}
                                <div>
                                    <div className="flex items-center gap-2 mb-3">
                                        <Clock size={11} className="text-white/20" />
                                        <span className="text-[11px] font-black text-white/30 uppercase tracking-[0.15em]">Período</span>
                                        <span className="flex-1 h-px bg-white/[0.04]" />
                                        {selectedAno !== 'all' && (
                                            <span className="text-[10px] text-blue-300/70 font-bold">{selectedAno} selecionado</span>
                                        )}
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                        {/* Botão Todos */}
                                        <YearPill
                                            label="Todos"
                                            active={selectedAno === 'all'}
                                            onClick={() => setSelectedAno('all')}
                                            tooltip="Exibir todos os anos"
                                        />
                                        {/* Ano atual destacado */}
                                        <YearPill
                                            label="atual 2025"
                                            active={selectedAno === 2025}
                                            done={completedYears.includes('2025')}
                                            partial={checkpointYears.includes('2025') && !completedYears.includes('2025')}
                                            onClick={() => {
                                                setSelectedAno(2025);
                                                const entry = availableFiles.find(f => f.name.includes('2025'));
                                                if (entry) { setFilename(entry.name); fetchPreview(entry.name); }
                                            }}
                                            tooltip={completedYears.includes('2025') ? '2025 ✓ Extraído' : '2025 — atual'}
                                        />
                                        {/* Demais anos — TODOS SEMPRE VISÍVEIS */}
                                        {ALL_YEARS.filter(y => y !== 2025).reverse().map(ano => {
                                            const isDone = completedYears.includes(ano.toString());
                                            const isPartial = checkpointYears.includes(ano.toString()) && !isDone;
                                            return (
                                                <YearPill
                                                    key={ano}
                                                    label={ano.toString()}
                                                    active={selectedAno === ano}
                                                    done={isDone}
                                                    partial={isPartial}
                                                    onClick={() => {
                                                        setSelectedAno(ano);
                                                        const entry = availableFiles.find(f => f.name.includes(ano.toString()));
                                                        if (entry) { setFilename(entry.name); fetchPreview(entry.name); }
                                                    }}
                                                    tooltip={isDone ? `${ano} ✓ Extraído` : isPartial ? `${ano} — Em Andamento` : `${ano} — Pendente`}
                                                />
                                            );
                                        })}
                                    </div>
                                    {/* Legenda */}
                                    <div className="flex gap-4 mt-2">
                                        {[{ color: 'bg-emerald-400', label: 'Extraído' }, { color: 'bg-amber-400', label: 'Em Andamento' }, { color: 'bg-white/20', label: 'Pendente' }].map(l => (
                                            <div key={l.label} className="flex items-center gap-1">
                                                <div className={`w-1.5 h-1.5 rounded-full ${l.color}`} />
                                                <span className="text-[9px] text-white/20 uppercase">{l.label}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                {/* PELÉ-A1 e PELÉ-A2: UPLOAD DE ARQUIVOS */}
                                {(agentId === 'pele_a1' || agentId === 'pele_a2') && (
                                    <PeleUploadPanel 
                                        selectedAno={selectedAno} 
                                        tipoFixo={agentId === 'pele_a1' ? 'parlamentares' : 'transferencias'}
                                    />
                                )}

                                {/* CONFIGURAÇÕES */}
                                {(needsYear || needsLegislatura || needsCity || needsLLM || (isZidaneCrew && safras.length > 0)) && (
                                    <div>
                                        <div className="flex items-center gap-2 mb-3">
                                            <Network size={11} className="text-white/20" />
                                            <span className="text-[7px] font-black text-white/20 uppercase tracking-[0.2em]">Parâmetros de Execução</span>
                                            <span className="flex-1 h-px bg-white/[0.04]" />
                                        </div>
                                        <div className="space-y-3">

                                            {/* Safras (Agente 1 — anos) */}
                                            {needsYear && (
                                                <div>
                                                    <div className="text-[11px] font-black text-white/30 uppercase tracking-wider mb-1">Safra — Ano de Referência</div>
                                                    <div className="text-[11px] text-white/20 mb-2">Selecione o ano a ser processado pelo robô</div>
                                                    {agentId === '1' && (
                                                        <Pill
                                                            label="🚀 Extrair Todos"
                                                            active={selectedAno === 'all'}
                                                            onClick={() => setSelectedAno('all')}
                                                            tooltip="Processa todos os anos em fila sequencial"
                                                        />
                                                    )}
                                                    <div className="flex flex-wrap gap-1.5 mt-2">
                                                        {[2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026].map(ano => {
                                                            const aRef = systemStatus?.agents?.[agentId || ''];
                                                            const isDone = aRef?.completed_years?.includes(ano.toString());
                                                            const isPartial = aRef?.checkpoint_years?.includes(ano.toString());
                                                            return (
                                                                <Pill
                                                                    key={ano}
                                                                    label={ano.toString()}
                                                                    active={selectedAno === ano}
                                                                    done={isDone}
                                                                    partial={isPartial && !isDone}
                                                                    onClick={() => {
                                                                        setSelectedAno(ano);
                                                                        const entry = availableFiles.find(f => f.name.includes(ano.toString()));
                                                                        if (entry) { setFilename(entry.name); fetchPreview(entry.name); }
                                                                    }}
                                                                    tooltip={isDone ? `${ano} ✓ Extraído` : isPartial ? `${ano} — Em Andamento` : `${ano} — Pendente`}
                                                                />
                                                            );
                                                        })}
                                                    </div>
                                                    <div className="flex gap-4 mt-2">
                                                        {[{ color: 'bg-emerald-400', label: 'Extraído' }, { color: 'bg-amber-400', label: 'Em Andamento' }, { color: 'bg-white/20', label: 'Pendente' }].map(l => (
                                                            <div key={l.label} className="flex items-center gap-1">
                                                                <div className={`w-1.5 h-1.5 rounded-full ${l.color}`} />
                                                                <span className="text-[6px] text-white/20 uppercase">{l.label}</span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Legislatura */}
                                            {needsLegislatura && safras.length === 0 && (
                                                <div>
                                                    <div className="text-[11px] font-black text-white/30 uppercase tracking-wider mb-1">Legislatura</div>
                                                    <div className="text-[11px] text-white/20 mb-2">Selecione a legislatura parlamentar alvo</div>
                                                    <div className="flex gap-1.5">
                                                        {[18, 19, 20].map(leg => (
                                                            <Pill
                                                                key={leg}
                                                                label={`${leg}ª Leg.`}
                                                                active={selectedAno === leg}
                                                                done={completedYears.includes(leg.toString())}
                                                                partial={checkpointYears.includes(leg.toString())}
                                                                onClick={() => setSelectedAno(leg)}
                                                                tooltip={`${leg}ª Legislatura da ALBA`}
                                                            />
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Município */}
                                            {needsCity && (
                                                <div>
                                                    <div className="text-[11px] font-black text-white/30 uppercase tracking-wider mb-1">Município</div>
                                                    <select value={selectedMunicipio} onChange={e => setSelectedMunicipio(e.target.value)}
                                                        className="w-full bg-white/[0.03] border border-white/[0.07] rounded-lg px-3 py-1.5 text-[9px] text-white/60 focus:outline-none focus:border-blue-400/40">
                                                        <option value="Salvador">Salvador</option>
                                                        <option value="Feira de Santana">Feira de Santana</option>
                                                        <option value="Senhor do Bonfim">Senhor do Bonfim</option>
                                                    </select>
                                                </div>
                                            )}

                                            {/* LLM Provider */}
                                            {needsLLM && (
                                                <div>
                                                    <div className="text-[11px] font-black text-white/30 uppercase tracking-wider mb-1">Motor de Inteligência (IA)</div>
                                                    <div className="text-[11px] text-white/20 mb-2">Provedor de LLM para análise e enriquecimento</div>
                                                    <div className="grid grid-cols-4 gap-1.5 mb-2">
                                                        {modelProviders.map(p => {
                                                            const Icon = p.icon;
                                                            return (
                                                                <button key={p.id} onClick={() => { setSelectedProvider(p.id); setSelectedModel(p.models[0]); }}
                                                                    className={`flex flex-col items-center gap-1 p-2 rounded-xl border transition-all ${selectedProvider === p.id ? 'bg-blue-500/10 border-blue-400/30 text-blue-300' : 'bg-white/[0.02] border-white/[0.06] text-white/30 hover:border-white/20'}`}>
                                                                    <Icon size={13} />
                                                                    <span className="text-[10px] font-black uppercase">{p.name}</span>
                                                                    <span className="text-[9px] text-white/30">{p.desc}</span>
                                                                </button>
                                                            );
                                                        })}
                                                    </div>
                                                    <select value={selectedModel} onChange={e => setSelectedModel(e.target.value)}
                                                        className="w-full bg-white/[0.03] border border-white/[0.07] rounded-lg px-3 py-1.5 text-[9px] text-white/60 focus:outline-none focus:border-blue-400/40">
                                                        {modelProviders.find(p => p.id === selectedProvider)?.models.map(m => (
                                                            <option key={m} value={m}>{m}</option>
                                                        ))}
                                                    </select>
                                                </div>
                                            )}

                                            {/* Arquivo Seletor */}
                                            {availableBronzeFiles.length > 0 && (
                                                <div>
                                                    <div className="text-[11px] font-black text-white/30 uppercase tracking-wider mb-1">Arquivo Alvo</div>
                                                    <div className="text-[11px] text-white/20 mb-2">Selecione o arquivo de entrada para este agente</div>
                                                    <div className="space-y-1 max-h-[120px] overflow-y-auto custom-scrollbar">
                                                        {availableBronzeFiles.map((f: any) => (
                                                            <button key={f.name} onClick={() => { setSelectedBronzeFile(f.name); fetchPreview(f.name); }}
                                                                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg border text-left transition-all ${selectedBronzeFile === f.name ? 'bg-blue-500/10 border-blue-400/25 text-blue-300' : 'bg-white/[0.02] border-white/[0.05] text-white/40 hover:border-white/15'}`}>
                                                                <FileJson size={12} />
                                                                <span className="text-[11px] font-mono truncate">{f.name}</span>
                                                            </button>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Limite Kaká */}
                                            {(agentId === '3' || agentId === 'kaka') && (
                                                <div>
                                                    <div className="text-[11px] font-black text-white/30 uppercase tracking-wider mb-1">Limite de Auditoria</div>
                                                    <div className="text-[11px] text-white/20 mb-2">Número máximo de registros a processar</div>
                                                    <div className="flex items-center gap-3">
                                                        <input type="range" min={10} max={3474} step={10} value={pageLimit} onChange={e => setPageLimit(parseInt(e.target.value))}
                                                            className="flex-1 h-1 accent-blue-400 cursor-pointer" />
                                                        <span className="text-[11px] font-black text-blue-300 w-20 text-right">{pageLimit === 3474 ? 'COMPLETO' : `${pageLimit} itens`}</span>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}

                                {/* TERMINAL */}
                                <div>
                                    <div className="flex items-center gap-2 mb-3">
                                        <Terminal size={13} className="text-white/30" />
                                        <span className="text-[11px] font-black text-white/30 uppercase tracking-[0.15em]">Terminal — {agentLabel}</span>
                                        <span className="flex-1 h-px bg-white/[0.04]" />
                                    </div>
                                    <AgentTerminal agentId={agentId || ''} />
                                </div>

                                {/* DATA PREVIEW */}
                                {inputData && (
                                    <div>
                                        <div className="flex items-center gap-2 mb-3">
                                            <Search size={11} className="text-white/20" />
                                            <span className="text-[7px] font-black text-white/20 uppercase tracking-[0.2em]">Data Preview</span>
                                            <span className="flex-1 h-px bg-white/[0.04]" />
                                            <button onClick={() => setViewMode(vm => vm === 'grid' ? 'code' : 'grid')}
                                                className="flex items-center gap-1 px-2 py-0.5 bg-white/[0.03] border border-white/[0.07] rounded text-[6px] font-black text-white/30 hover:border-white/20 transition-all uppercase">
                                                {viewMode === 'grid' ? <><Eye size={8} /> Code</> : <><Eye size={8} /> Grid</>}
                                            </button>
                                        </div>
                                        {viewMode === 'code'
                                            ? <CodePreview code={JSON.stringify(inputData, null, 2)} />
                                            : <DataPreviewStudio data={inputData} completeness={fileStats?.completeness} />
                                        }
                                    </div>
                                )}

                            </div>{/* fim col direita */}
                        </div>{/* fim body */}

                        {/* ══ EXECUTOR FIXO ═══════════════════════════════════ */}
                        <div className="shrink-0 px-6 py-3 border-t border-white/[0.05] bg-[#060608]/80 backdrop-blur-xl">
                            <div className="flex gap-2 items-center">
                                <button
                                    onClick={isActuallyRunning ? handleStop : handleRun}
                                    disabled={loading}
                                    className={`flex-1 h-10 rounded-xl flex items-center justify-center gap-2.5 border transition-all font-black text-[9px] uppercase tracking-[0.15em] relative overflow-hidden group ${
                                        isActuallyRunning
                                            ? 'bg-red-500/10 border-red-400/25 text-red-300 hover:bg-red-500/15'
                                            : 'bg-gradient-to-r from-blue-500/10 via-purple-500/5 to-emerald-500/10 border-blue-400/20 text-white hover:border-blue-400/40 shadow-[0_0_20px_rgba(59,130,246,0.06)]'
                                    }`}
                                >
                                    {!isActuallyRunning && <div className="absolute inset-0 bg-gradient-to-r from-transparent via-blue-400/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />}
                                    {isActuallyRunning
                                        ? <><StopCircle size={15} className="relative z-10" /><span className="relative z-10">Abortar Operação</span></>
                                        : <><PlayCircle size={15} className="relative z-10" /><span className="relative z-10">Iniciar {runLabel}</span></>
                                    }
                                </button>
                                {!isActuallyRunning && (
                                    <button onClick={handleRestart} title="Reiniciar do Zero"
                                        className="w-11 h-11 rounded-xl bg-white/[0.03] border border-white/[0.07] flex items-center justify-center text-white/30 hover:border-white/20 hover:text-white/60 transition-all active:scale-90">
                                        <RotateCcw size={16} />
                                    </button>
                                )}
                                <button onClick={() => onOpenStudio(getLayer(agentId))} title="Abrir Studio de Dados"
                                    className="w-11 h-11 rounded-xl bg-white/[0.03] border border-white/[0.07] flex items-center justify-center text-white/30 hover:border-white/20 hover:text-white/60 transition-all active:scale-90">
                                    <Eye size={16} />
                                </button>
                            </div>
                        </div>

                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );
};

export default AgentDetailsDrawer;
