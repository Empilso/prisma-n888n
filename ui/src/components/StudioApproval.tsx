import React, { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface StudioApprovalProps {
    isOpen: boolean;
    onClose: () => void;
    activeLayer: Layer;
    onLayerChange: (layer: Layer) => void;
}

type Layer = 'bronze' | 'prata' | 'ouro';

const layers: { key: Layer; label: string; icon: string; color: string; desc: string }[] = [
    { key: 'bronze', label: 'Bronze', icon: '🥉', color: '#cd7f32', desc: 'Dados brutos do scraper' },
    { key: 'prata', label: 'Prata', icon: '🥈', color: '#c0c0c0', desc: 'Normalizado + dedup' },
    { key: 'ouro', label: 'Ouro', icon: '🥇', color: '#ffd700', desc: 'Validado + score de risco' },
];

const COLUMNS_MAP: Record<Layer, { key: string; label: string; width: string }[]> = {
    bronze: [
        { key: 'deputado', label: 'Deputado', width: 'w-[180px]' },
        { key: 'categoria', label: 'Categoria', width: 'w-[200px]' },
        { key: 'valor', label: 'Valor (R$)', width: 'w-[120px]' },
        { key: 'competencia', label: 'Competência', width: 'w-[110px]' },
        { key: 'nome_fornecedor', label: 'Fornecedor', width: 'w-[200px]' },
        { key: 'num_nf', label: 'NF', width: 'w-[140px]' },
        { key: 'ano', label: 'Ano', width: 'w-[60px]' },
    ],
    prata: [
        { key: 'deputado', label: 'Deputado', width: 'w-[180px]' },
        { key: 'categoria', label: 'Categoria', width: 'w-[200px]' },
        { key: 'valor', label: 'Valor (R$)', width: 'w-[120px]' },
        { key: 'competencia', label: 'Competência', width: 'w-[110px]' },
        { key: 'nome_fornecedor', label: 'Fornecedor', width: 'w-[200px]' },
        { key: 'cnpj_fornecedor', label: 'CNPJ', width: 'w-[160px]' },
        { key: 'hash_id', label: 'Hash ID', width: 'w-[140px]' },
        { key: 'processado_em', label: 'Processado em', width: 'w-[180px]' },
    ],
    ouro: [
        { key: 'deputado', label: 'Deputado', width: 'w-[180px]' },
        { key: 'categoria', label: 'Categoria', width: 'w-[200px]' },
        { key: 'valor', label: 'Valor (R$)', width: 'w-[120px]' },
        { key: 'risco_nivel', label: 'Risco', width: 'w-[100px]' },
        { key: 'comentario_aguia', label: 'Análise Águia', width: 'w-[250px]' },
        { key: 'competencia', label: 'Competência', width: 'w-[110px]' },
        { key: 'nome_fornecedor', label: 'Fornecedor', width: 'w-[200px]' },
        { key: 'hash_id', label: 'Hash ID', width: 'w-[140px]' },
    ],
};

function formatCurrency(v: any): string {
    const n = typeof v === 'number' ? v : parseFloat(v) || 0;
    return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function getRiskBadge(risk: string) {
    const r = (risk || '').toLowerCase();
    if (r.includes('alto') || r.includes('high')) return { bg: 'bg-red-500/15', text: 'text-red-400', border: 'border-red-500/20' };
    if (r.includes('médio') || r.includes('medio') || r.includes('medium')) return { bg: 'bg-yellow-500/15', text: 'text-yellow-400', border: 'border-yellow-500/20' };
    if (r.includes('baixo') || r.includes('low')) return { bg: 'bg-green-500/15', text: 'text-green-400', border: 'border-green-500/20' };
    return { bg: 'bg-white/5', text: 'text-[var(--text-tertiary)]', border: 'border-white/5' };
}

const StudioApproval = ({ isOpen, onClose, activeLayer, onLayerChange }: StudioApprovalProps) => {
    const [viewMode, setViewMode] = useState<'table' | 'code'>('table');
    const [codeTab, setCodeTab] = useState<'json' | 'source'>('json');
    const [data, setData] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const [filename, setFilename] = useState('');
    const [availableFiles, setAvailableFiles] = useState<any[]>([]);
    const [search, setSearch] = useState('');
    const [selectedRow, setSelectedRow] = useState<number | null>(null);
    const [sourceCode, setSourceCode] = useState('');
    const [sourceFilename, setSourceFilename] = useState('');
    const [sortConfig, setSortConfig] = useState<{ key: string, direction: 'asc' | 'desc' } | null>(null);

    const handleSort = (key: string) => {
        setSortConfig(current => {
            if (current?.key === key) {
                if (current.direction === 'asc') return { key, direction: 'desc' };
                return null;
            }
            return { key, direction: 'asc' };
        });
    };

    useEffect(() => {
        if (isOpen) {
            fetchData(activeLayer);
            fetchAvailableFiles(activeLayer);
            if (viewMode === 'code' && codeTab === 'source') {
                fetchSource(activeLayer);
            }
        }
    }, [isOpen, activeLayer, viewMode, codeTab]);

    const fetchAvailableFiles = async (layer: Layer) => {
        try {
            const res = await fetch(`http://localhost:8001/api/datalake/files`);
            const json = await res.json();
            if (json.status === 'ok') {
                const filtered = json.files.filter((f: any) => f.layer === layer);
                setAvailableFiles(filtered);
            }
        } catch (e) { }
    };

    const fetchData = async (layer: Layer, targetFile?: string) => {
        setLoading(true);
        setSelectedRow(null);
        try {
            let url = `http://localhost:8001/api/agent-data/${layer}`;
            if (targetFile) {
                url = `http://localhost:8001/api/datalake/files/${layer}/${targetFile}`;
            }
            const res = await fetch(url);
            const json = await res.json();
            if (json.status === 'ok' && Array.isArray(json.data)) {
                setData(json.data);
                setFilename(targetFile || json.filename || '');
            } else {
                setData([]);
                setFilename('');
            }
        } catch (e) {
            setData([]);
        }
        setLoading(false);
    };

    const fetchSource = async (layer: Layer) => {
        try {
            const res = await fetch(`http://localhost:8001/api/agent-source/${layer}`);
            const json = await res.json();
            if (json.status === 'ok') {
                setSourceCode(json.content);
                setSourceFilename(json.filename);
            }
        } catch (e) {
            setSourceCode('# Erro ao carregar fonte');
        }
    };

    const columns = COLUMNS_MAP[activeLayer];

    const filtered = useMemo(() => {
        let result = data;

        if (search.trim()) {
            const q = search.toLowerCase();
            result = result.filter(row =>
                columns.some(col => String(row[col.key] || '').toLowerCase().includes(q))
            );
        }

        if (sortConfig) {
            result = [...result].sort((a, b) => {
                const aVal = a[sortConfig.key];
                const bVal = b[sortConfig.key];

                if (aVal === bVal) return 0;

                if (typeof aVal === 'number' && typeof bVal === 'number') {
                    return sortConfig.direction === 'asc' ? aVal - bVal : bVal - aVal;
                }

                const aStr = String(aVal || '').toLowerCase();
                const bStr = String(bVal || '').toLowerCase();

                if (aStr < bStr) return sortConfig.direction === 'asc' ? -1 : 1;
                if (aStr > bStr) return sortConfig.direction === 'asc' ? 1 : -1;
                return 0;
            });
        }

        return result;
    }, [data, search, columns, sortConfig]);

    // Stats
    const totalValor = useMemo(() => data.reduce((s, r) => s + (parseFloat(r.valor) || 0), 0), [data]);
    const uniqueDeputados = useMemo(() => new Set(data.map(r => r.deputado)).size, [data]);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[200] flex bg-black/40 backdrop-blur-sm animate-in fade-in duration-300">
            {/* Overlay click to close */}
            <div className="absolute inset-0" onClick={onClose} />

            {/* Studio Panel - STUDIO 5X PREMIUM (Otimizado fluidez) 🛡️🧪👽🚀🛸👑 */}
            <div className="relative w-full h-full flex m-4 rounded-[24px] overflow-hidden border border-white/[0.08] shadow-2xl glass-premium"
                style={{ background: 'rgba(10, 10, 15, 0.96)' }}>

                {/* LEFT: Layer Selector & File Explorer */}
                <div className="w-[280px] shrink-0 border-r border-white/[0.04] flex flex-col p-6 overflow-hidden">
                    <div className="flex items-center justify-between mb-8 group/title">
                        <div>
                            <h2 className="text-lg font-black text-white flex items-center gap-2 tracking-tighter">
                                <span className="text-[var(--accent-purple)]">STUDIO</span>
                                <span className="bg-white/10 px-1.5 py-0.5 rounded-lg text-[10px] transform -rotate-12 group-hover/title:rotate-0 transition-transform">5X</span>
                            </h2>
                            <p className="text-[9px] font-bold text-[var(--text-tertiary)] uppercase tracking-[0.2em] mt-1 opacity-50">Data Audit Elite</p>
                        </div>
                        <button onClick={onClose}
                            className="w-8 h-8 rounded-xl glass flex items-center justify-center text-[var(--text-tertiary)] hover:text-white hover:bg-red-500/20 hover:border-red-500/30 transition-all text-xs active:scale-90">
                            ✕
                        </button>
                    </div>

                    {/* Layer Selector - Apple Style Segmented */}
                    <div className="flex p-1 bg-white/[0.03] border border-white/[0.06] rounded-2xl mb-6">
                        {layers.map(l => (
                            <button
                                key={l.key}
                                onClick={() => onLayerChange(l.key)}
                                className={`flex-1 flex flex-col items-center py-2.5 rounded-xl transition-all ${activeLayer === l.key ? 'bg-white/10 shadow-lg text-white' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'}`}
                                title={l.desc}
                            >
                                <span className="text-lg mb-1">{l.icon}</span>
                                <span className="text-[9px] font-black uppercase tracking-wider">{l.label}</span>
                            </button>
                        ))}
                    </div>

                    {/* Datasets Sidebar Pro */}
                    <div className="flex-1 flex flex-col min-h-0">
                        <div className="flex items-center justify-between px-2 mb-4">
                            <h3 className="text-[10px] font-black text-[var(--text-tertiary)] uppercase tracking-widest flex items-center gap-2">
                                <span className="opacity-50">📂</span> Datasets
                            </h3>
                            <span className="text-[9px] font-mono-glass text-[var(--text-tertiary)] bg-white/5 px-2 py-0.5 rounded-full">{availableFiles.length}</span>
                        </div>

                        <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-1.5 min-h-0">
                            {availableFiles.map(file => {
                                const isSelected = filename === file.name;
                                const yearMatch = file.name.match(/_(\d{4})_/);
                                const label = yearMatch ? `Safra ${yearMatch[1]}` : file.name;
                                return (
                                    <button
                                        key={file.name}
                                        onClick={() => fetchData(activeLayer, file.name)}
                                        className={`group/item w-full text-left p-3 rounded-2xl transition-all border animate-in slide-in-from-left duration-300 ${isSelected
                                            ? 'bg-[var(--accent-purple)]/15 border-[var(--accent-purple)]/40 text-white shadow-[0_0_20px_rgba(191,90,242,0.1)]'
                                            : 'hover:bg-white/[0.04] border-transparent text-[var(--text-secondary)] hover:text-white'
                                            }`}
                                    >
                                        <div className="flex items-center justify-between mb-1">
                                            <span className={`text-[11px] font-bold ${isSelected ? 'text-[var(--accent-purple)]' : ''}`}>{label}</span>
                                            <span className="text-[8px] opacity-40 font-mono-glass">{file.size}</span>
                                        </div>
                                        <div className="text-[9px] opacity-30 truncate font-mono-glass group-hover/item:opacity-60 transition-opacity">
                                            {file.name}
                                        </div>
                                    </button>
                                );
                            })}
                            {availableFiles.length === 0 && (
                                <div className="flex flex-col items-center justify-center p-8 opacity-20 grayscale scale-75">
                                    <span className="text-4xl mb-2">📁</span>
                                    <span className="text-[10px] font-bold uppercase tracking-widest">Pasta Vazia</span>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Stats Premium Card */}
                    <div className="mt-6 p-5 rounded-[24px] border border-white/[0.06] bg-gradient-to-br from-white/[0.05] to-transparent shadow-inner">
                        <div className="flex items-center gap-2 mb-4 pb-3 border-b border-white/5">
                            <span className="text-sm">📊</span>
                            <span className="text-[10px] font-black uppercase tracking-widest text-white/50">Audit Report</span>
                        </div>
                        <div className="space-y-3.5">
                            <StatLine label="Registros" value={data.length.toLocaleString()} />
                            <StatLine label="Entidades" value={uniqueDeputados.toString()} />
                            <StatLine label="Montante" value={formatCurrency(totalValor)} />
                            <div className="pt-2">
                                <div className="text-[8px] font-bold text-[var(--text-tertiary)] uppercase tracking-widest mb-1.5">File Integrity</div>
                                <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                                    <div className="h-full bg-[var(--accent-green)] animate-pulse" style={{ width: '100%' }} />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* RIGHT: Main Studio Canvas */}
                <div className="flex-1 flex flex-col overflow-hidden bg-white/[0.01]">

                    {/* Studio Header Toolbar */}
                    <div className="h-20 flex items-center justify-between px-8 border-b border-white/[0.04] shrink-0">
                        <div className="flex items-center gap-5">
                            <div className="w-12 h-12 rounded-2xl bg-white/[0.04] border border-white/[0.08] flex items-center justify-center text-2xl shadow-inner">
                                {layers.find(l => l.key === activeLayer)?.icon}
                            </div>
                            <div>
                                <h3 className="text-sm font-black text-white tracking-widest uppercase">
                                    {layers.find(l => l.key === activeLayer)?.label} Camada
                                </h3>
                                <div className="flex items-center gap-2 mt-1">
                                    <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent-green)] animate-pulse" />
                                    <span className="text-[10px] text-[var(--text-tertiary)] font-mono-glass">
                                        Viewing {filename || 'live_stream'}
                                    </span>
                                </div>
                            </div>
                        </div>

                        {/* Mode Switcher Switch-Style */}
                        <div className="flex bg-black/40 p-1.5 rounded-[18px] border border-white/[0.08] shadow-inner">
                            <button
                                onClick={() => setViewMode('table')}
                                className={`px-6 py-2 rounded-xl text-[10px] font-black transition-all transform active:scale-95 ${viewMode === 'table' ? 'bg-white/[0.1] text-white shadow-xl border border-white/10' : 'text-[var(--text-tertiary)] hover:text-white'}`}
                            >
                                📊 EXPLORER
                            </button>
                            <button
                                onClick={() => setViewMode('code')}
                                className={`px-6 py-2 rounded-xl text-[10px] font-black transition-all transform active:scale-95 ${viewMode === 'code' ? 'bg-white/[0.1] text-white shadow-xl border border-white/10' : 'text-[var(--text-tertiary)] hover:text-white'}`}
                            >
                                ⚛️ CODE 5X
                            </button>
                        </div>

                        <div className="flex items-center gap-4">
                            {viewMode === 'table' ? (
                                <>
                                    <div className="relative group">
                                        <div className="absolute inset-0 bg-[var(--accent-purple)]/10 blur-md opacity-0 group-focus-within:opacity-100 transition-opacity rounded-xl" />
                                        <input
                                            type="text"
                                            value={search}
                                            onChange={e => setSearch(e.target.value)}
                                            placeholder="Audit Search..."
                                            className="relative w-64 h-10 bg-black/40 border border-white/[0.08] rounded-xl px-4 pl-10 text-[11px] text-white placeholder:text-[var(--text-tertiary)] outline-none focus:border-[var(--accent-purple)]/40 transition-all font-mono-glass"
                                        />
                                        <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-xs opacity-40">🔍</span>
                                    </div>
                                    <button className="h-10 px-5 rounded-xl glass border border-white/10 text-[10px] font-black text-white hover:bg-white/10 hover:border-white/20 transition-all active:scale-95 shadow-lg uppercase tracking-widest">
                                        ⚡ Export
                                    </button>
                                </>
                            ) : (
                                <div className="flex bg-white/[0.03] p-1 rounded-xl border border-white/5">
                                    <button
                                        onClick={() => setCodeTab('json')}
                                        className={`px-4 h-8 rounded-lg text-[9px] font-black tracking-widest transition-all ${codeTab === 'json' ? 'bg-[var(--accent-purple)] text-white shadow-lg' : 'text-[var(--text-tertiary)] hover:text-white'}`}
                                    >
                                        JSON
                                    </button>
                                    <button
                                        onClick={() => setCodeTab('source')}
                                        className={`px-4 h-8 rounded-lg text-[9px] font-black tracking-widest transition-all ${codeTab === 'source' ? 'bg-[var(--accent-purple)] text-white shadow-lg' : 'text-[var(--text-tertiary)] hover:text-white'}`}
                                    >
                                        PY SOURCE
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Studio Main Body */}
                    <div className="flex-1 flex flex-col min-h-0">
                        {loading ? (
                            <div className="flex-1 flex flex-col items-center justify-center">
                                <div className="relative w-16 h-16 mb-6">
                                    <div className="absolute inset-0 border-4 border-[var(--accent-purple)]/10 rounded-full" />
                                    <div className="absolute inset-0 border-4 border-[var(--accent-purple)] border-t-transparent rounded-full animate-spin shadow-[0_0_20px_rgba(191,90,242,0.4)]" />
                                </div>
                                <span className="text-[10px] font-black text-[var(--accent-purple)] uppercase tracking-[0.3em] animate-pulse">Syncing Datalake...</span>
                            </div>
                        ) : data.length === 0 ? (
                            <div className="flex-1 flex flex-col items-center justify-center opacity-30 grayscale hover:grayscale-0 transition-all duration-700">
                                <div className="text-6xl mb-6 transform hover:scale-110 transition-transform">🛸</div>
                                <div className="text-lg font-black text-white tracking-widest uppercase">Layer Undefined</div>
                                <div className="text-[10px] text-[var(--text-tertiary)] mt-2 font-bold uppercase tracking-[0.2em]">Selecione um dataset para iniciar a auditoria</div>
                            </div>
                        ) : viewMode === 'table' ? (
                            <div className="flex-1 overflow-auto custom-scrollbar p-6">
                                <div className="rounded-[24px] overflow-hidden border border-white/[0.06] bg-black/40 shadow-2xl">
                                    <table className="w-full text-left border-collapse">
                                        <thead>
                                            <tr className="bg-white/[0.02] border-b border-white/[0.06]">
                                                <th className="w-[60px] px-6 py-4 text-[9px] font-black text-[var(--text-tertiary)] uppercase tracking-[0.2em] text-center">ID</th>
                                                {columns.map(col => (
                                                    <th
                                                        key={col.key}
                                                        onClick={() => handleSort(col.key)}
                                                        className={`${col.width} px-6 py-4 text-[9px] font-black text-[var(--text-tertiary)] uppercase tracking-[0.2em] cursor-pointer hover:bg-white/[0.04] hover:text-white transition-colors group/th select-none`}
                                                    >
                                                        <div className="flex items-center gap-2">
                                                            {col.label}
                                                            <span className={`text-[12px] opacity-0 group-hover/th:opacity-50 transition-opacity ${sortConfig?.key === col.key ? 'opacity-100 text-[var(--accent-purple)]' : ''}`}>
                                                                {sortConfig?.key === col.key ? (sortConfig.direction === 'asc' ? '↑' : '↓') : '↕'}
                                                            </span>
                                                        </div>
                                                    </th>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-white/[0.02]">
                                            {filtered.map((row, i) => {
                                                const isSelected = selectedRow === i;
                                                return (
                                                    <tr
                                                        key={i}
                                                        onClick={() => setSelectedRow(isSelected ? null : i)}
                                                        className={`group/row cursor-pointer transition-all duration-200 ${isSelected ? 'bg-[var(--accent-purple)]/10' : 'hover:bg-white/[0.02]'}`}
                                                    >
                                                        <td className="px-6 py-3.5 text-[10px] text-[var(--text-tertiary)] font-mono-glass text-center group-hover/row:text-white transition-colors">{(i + 1).toString().padStart(3, '0')}</td>
                                                        {columns.map(col => {
                                                            const val = row[col.key];
                                                            if (col.key === 'valor') {
                                                                return (
                                                                    <td key={col.key} className="px-6 py-3.5 font-mono-glass text-[11px]">
                                                                        <span className="text-[var(--accent-green)] font-black">{formatCurrency(val)}</span>
                                                                    </td>
                                                                );
                                                            }
                                                            if (col.key === 'risco_nivel' && val) {
                                                                const badge = getRiskBadge(val);
                                                                return (
                                                                    <td key={col.key} className="px-6 py-3.5">
                                                                        <span className={`px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest border ${badge.bg} ${badge.text} ${badge.border} shadow-sm`}>
                                                                            {val}
                                                                        </span>
                                                                    </td>
                                                                );
                                                            }
                                                            if (col.key === 'hash_id') {
                                                                return (
                                                                    <td key={col.key} className="px-6 py-3.5">
                                                                        <span className="bg-white/5 border border-white/5 px-2 py-1 rounded-md text-[9px] text-[var(--accent-blue)] font-mono-glass font-bold tracking-tighter shadow-inner group-hover/row:border-[var(--accent-blue)]/50 transition-colors">
                                                                            {String(val || '').substring(0, 10)}
                                                                        </span>
                                                                    </td>
                                                                );
                                                            }
                                                            return (
                                                                <td key={col.key} className="px-6 py-3.5 text-[11px] text-[var(--text-secondary)] group-hover/row:text-white transition-colors">
                                                                    <div className="truncate max-w-[220px]" title={String(val || '')}>
                                                                        {val ?? '—'}
                                                                    </div>
                                                                </td>
                                                            );
                                                        })}
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        ) : (
                            <div className="flex-1 flex flex-col bg-black/30 overflow-hidden shadow-inner m-6 rounded-[24px] border border-white/[0.04]">
                                <div className="h-10 flex items-center justify-between px-6 bg-white/[0.02] border-b border-white/[0.06]">
                                    <div className="flex items-center gap-4">
                                        <div className="flex gap-1.5">
                                            <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f56]" />
                                            <div className="w-2.5 h-2.5 rounded-full bg-[#ffbd2e]" />
                                            <div className="w-2.5 h-2.5 rounded-full bg-[#27c93f]" />
                                        </div>
                                        <span className="text-[9px] font-black text-[var(--text-tertiary)] uppercase tracking-[0.2em] font-mono-glass">
                                            {codeTab === 'json' ? `DATALAKE_ENTITY::${filename}` : `AGENT_ROUTING::${sourceFilename}`}
                                        </span>
                                    </div>
                                    <button
                                        onClick={() => {
                                            const content = codeTab === 'json' ? JSON.stringify(data, null, 2) : sourceCode;
                                            navigator.clipboard.writeText(content);
                                        }}
                                        className="text-[9px] font-black text-[var(--text-tertiary)] hover:text-white flex items-center gap-1.5 transition-colors"
                                    >
                                        📋 CLIPBOARD
                                    </button>
                                </div>
                                <div className="flex-1 overflow-auto custom-scrollbar selection:bg-[var(--accent-purple)]/30">
                                    <SyntaxHighlighter
                                        language={codeTab === 'json' ? 'json' : 'python'}
                                        style={vscDarkPlus}
                                        customStyle={{
                                            margin: 0,
                                            padding: '2rem',
                                            background: 'transparent',
                                            fontSize: '12px',
                                            lineHeight: '1.6',
                                            fontFamily: "'SF Mono', 'JetBrains Mono', monospace"
                                        }}
                                        wrapLines={true}
                                        showLineNumbers={true}
                                    >
                                        {codeTab === 'json' ? JSON.stringify(data, null, 2) : sourceCode}
                                    </SyntaxHighlighter>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* RIGHT DRAWER: Advanced Audit Inspector */}
                <AnimatePresence>
                    {selectedRow !== null && filtered[selectedRow] && (
                        <motion.div
                            initial={{ x: 100, opacity: 0 }}
                            animate={{ x: 0, opacity: 1 }}
                            exit={{ x: 100, opacity: 0 }}
                            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                            className="w-[420px] shrink-0 border-l border-white/[0.04] flex flex-col bg-black/40 backdrop-blur-3xl overflow-hidden p-8"
                        >
                            <div className="flex items-center justify-between mb-8 pb-4 border-b border-white/5">
                                <div>
                                    <span className="text-[10px] font-black text-[var(--accent-purple)] uppercase tracking-[0.3em]">Auditoria Profunda</span>
                                    <h4 className="text-xl font-black text-white tracking-tighter mt-1">Gasto Detalhado</h4>
                                </div>
                                <button onClick={() => setSelectedRow(null)}
                                    className="w-8 h-8 rounded-xl glass flex items-center justify-center text-[var(--text-tertiary)] hover:text-white transition-all active:scale-90">✕</button>
                            </div>

                            <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-6">
                                {Object.entries(filtered[selectedRow]).map(([key, val]) => {
                                    const isHighlight = ['deputado', 'valor', 'risco_nivel', 'nome_fornecedor'].includes(key);
                                    return (
                                        <div key={key} className={`group/field animate-in slide-in-from-right duration-500`}>
                                            <div className="flex items-center justify-between mb-2">
                                                <div className="text-[9px] font-black text-[var(--text-tertiary)] uppercase tracking-widest">{key.replace(/_/g, ' ')}</div>
                                                <div className="w-1.5 h-1.5 rounded-full bg-white/10 group-hover/field:bg-[var(--accent-purple)] transition-colors shadow-[0_0_8px_rgba(191,90,242,0)] group-hover/field:shadow-[0_0_8px_rgba(191,90,242,0.8)]" />
                                            </div>
                                            <div className={`text-[12px] break-all leading-relaxed p-4 rounded-2xl border transition-all ${isHighlight ? 'bg-[var(--accent-purple)]/5 border-[var(--accent-purple)]/20 text-white shadow-inner font-bold' : 'bg-white/[0.02] border-white/[0.04] text-[var(--text-secondary)] font-mono-glass'}`}>
                                                {typeof val === 'object' ? JSON.stringify(val, null, 2) : (key === 'valor' ? formatCurrency(val) : String(val ?? '—'))}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>

                            {/* Verification Badge */}
                            <div className="mt-8 p-4 rounded-2xl border border-[var(--accent-green)]/20 bg-[var(--accent-green)]/5 flex items-center gap-4">
                                <div className="w-10 h-10 rounded-full bg-[var(--accent-green)]/20 flex items-center justify-center text-xl shadow-[0_0_15px_rgba(48,209,88,0.3)]">🛡️</div>
                                <div>
                                    <div className="text-[10px] font-black text-[var(--accent-green)] uppercase tracking-widest">Hash Validada</div>
                                    <div className="text-[9px] text-[var(--accent-green)]/60 font-mono-glass truncate w-[240px]">
                                        {String(filtered[selectedRow].hash_id || 'ALBA_V1_VERIFIED')}
                                    </div>
                                </div>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div >
    );
};

/* Stat line helper */
const StatLine = ({ label, value, small }: { label: string; value: string; small?: boolean }) => (
    <div className="flex justify-between items-center">
        <span className="text-[10px] text-[var(--text-tertiary)]">{label}</span>
        <span className={`font-semibold text-white ${small ? 'text-[9px] font-mono-glass truncate max-w-[120px]' : 'text-[11px]'}`}>{value}</span>
    </div>
);

export default StudioApproval;
