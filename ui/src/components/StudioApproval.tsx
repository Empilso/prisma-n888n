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

type Layer = 'bronze' | 'prata' | 'kaka' | 'ouro' | 'parlamentares';

const layers: { key: Layer; label: string; icon: string; color: string; desc: string }[] = [
    { key: 'bronze', label: 'Bronze', icon: '🥉', color: '#cd7f32', desc: 'Dados brutos do scraper' },
    { key: 'prata', label: 'Prata', icon: '🥈', color: '#c0c0c0', desc: 'Normalizado + dedup' },
    { key: 'kaka', label: 'PDF Forense', icon: '🔎', color: '#8a2be2', desc: 'Auditoria de Notas Fiscais (PDF)' },
    { key: 'ouro', label: 'Ouro', icon: '🥇', color: '#ffd700', desc: 'Validado + score de risco' },
    { key: 'parlamentares', label: 'Zidane', icon: '🕵️', color: '#9b59b6', desc: 'Biografias e Perfis' },
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
        { key: 'categoria_slug', label: 'Categoria', width: 'w-[160px]' },
        { key: 'valor', label: 'Valor (R$)', width: 'w-[120px]' },
        { key: 'competencia_date', label: 'Competência', width: 'w-[110px]' },
        { key: 'nome_fornecedor', label: 'Fornecedor', width: 'w-[200px]' },
        { key: 'cnpj_fornecedor', label: 'CNPJ', width: 'w-[160px]' },
        { key: 'hash_id', label: 'Hash ID', width: 'w-[140px]' },
        { key: 'processado_em', label: 'Processado em', width: 'w-[180px]' },
    ],
    ouro: [
        { key: 'deputado', label: 'Deputado', width: 'w-[180px]' },
        { key: 'categoria_slug', label: 'Categoria', width: 'w-[160px]' },
        { key: 'valor', label: 'Valor (R$)', width: 'w-[120px]' },
        { key: 'risco_nivel', label: 'Risco', width: 'w-[100px]' },
        { key: 'comentario_aguia', label: 'Análise Águia', width: 'w-[250px]' },
        { key: 'competencia_date', label: 'Competência', width: 'w-[110px]' },
        { key: 'nome_fornecedor', label: 'Fornecedor', width: 'w-[200px]' },
        { key: 'hash_id', label: 'Hash ID', width: 'w-[140px]' },
    ],
    kaka: [
        { key: 'deputado', label: 'Deputado', width: 'w-[160px]' },
        { key: 'kaka_status', label: 'Status', width: 'w-[90px]' },
        { key: 'kaka_tipo_pdf', label: 'Tipo PDF', width: 'w-[110px]' },
        { key: 'kaka_qualidade_pdf', label: 'Qualidade', width: 'w-[90px]' },
        { key: 'kaka_confianca', label: 'Conf %', width: 'w-[70px]' },
        { key: 'kaka_metodo_extracao', label: 'Metodo', width: 'w-[120px]' },
        { key: 'valor', label: 'Valor Portal', width: 'w-[110px]' },
        { key: 'kaka_valor_nf', label: 'Valor NF', width: 'w-[110px]' },
        { key: 'kaka_delta_valor', label: 'Delta R$', width: 'w-[90px]' },
        { key: 'kaka_divergencia_valor', label: 'Div.Valor', width: 'w-[80px]' },
        { key: 'kaka_divergencia_cnpj', label: 'Div.CNPJ', width: 'w-[80px]' },
        { key: 'kaka_emitente_cnpj', label: 'CNPJ NF', width: 'w-[140px]' },
        { key: 'cnpj_fornecedor', label: 'CNPJ Portal', width: 'w-[140px]' },
        { key: 'url_pdf_nf', label: 'PDF', width: 'w-[180px]' },
    ],
    parlamentares: [
        { key: 'foto_url', label: 'Foto', width: 'w-[100px]' },
        { key: 'nome_limpo', label: 'Parlamentar', width: 'w-[200px]' },
        { key: 'sigla_partido', label: 'Partido', width: 'w-[100px]' },
        { key: 'biografia_resumo', label: 'Resumo Bio', width: 'w-[300px]' },
        { key: 'qualidade_score', label: 'Score', width: 'w-[80px]' },
        { key: 'mandatos_count', label: 'Mandatos', width: 'w-[100px]' },
        { key: 'processado_em', label: 'Extraído', width: 'w-[150px]' },
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
    const [explorerTree, setExplorerTree] = useState<any[]>([]);
    
    // UI State para Accordion
    const [expandedCrews, setExpandedCrews] = useState<Record<string, boolean>>({ alba: true, zidane: true });
    const [expandedLayers, setExpandedLayers] = useState<Record<string, boolean>>({ 'alba-ouro': true, 'alba-prata': false, 'alba-bronze': false });

    // PAGINATION STATE
    const [currentPage, setCurrentPage] = useState(1);
    const ROWS_PER_PAGE = 75;

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
            fetchExplorerTree();
            fetchData(activeLayer);
            if (viewMode === 'code' && codeTab === 'source') {
                fetchSource(activeLayer);
            }
        }
    }, [isOpen, activeLayer, viewMode, codeTab]);

    const fetchExplorerTree = async () => {
        try {
            const res = await fetch(`http://localhost:8003/api/studio/explorer`);
            const json = await res.json();
            if (json.status === 'ok') {
                setExplorerTree(json.crews);
            }
        } catch(e) {}
    };

    const fetchAvailableFiles = async (layer: Layer) => {
        try {
            const res = await fetch(`http://localhost:8003/api/datalake/files`);
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
            let url = `http://localhost:8003/api/agent-data/${layer}`;
            if (targetFile) {
                url = `http://localhost:8003/api/datalake/files/${layer}/${targetFile}`;
            }
            const res = await fetch(url);
            const json = await res.json();
            
            if (json.status === 'ok') {
                let rawData = json.data;
                // Se for um objeto único (perfil individual), envelopa em array para o grid
                if (rawData && !Array.isArray(rawData) && typeof rawData === 'object') {
                    // Enriquecimento ad-hoc se necessário
                    if (layer === 'parlamentares' || targetFile?.includes('parlamentar')) {
                        rawData.biografia_resumo = (rawData.biografia_completa || '') .substring(0, 200) + '...';
                        rawData.mandatos_count = rawData.mandatos?.length || 0;
                    }
                    rawData = [rawData];
                }
                
                if (Array.isArray(rawData)) {
                    setData(rawData);
                    setFilename(targetFile || json.filename || '');
                } else {
                    setData([]);
                    setFilename('');
                }
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
            const res = await fetch(`http://localhost:8003/api/agent-source/${layer}`);
            const json = await res.json();
            if (json.status === 'ok') {
                setSourceCode(json.content);
                setSourceFilename(json.filename);
            }
        } catch (e) {
            setSourceCode('# Erro ao carregar fonte');
        }
    };

    const handleFileDelete = async (layer: Layer, name: string) => {
        if (!confirm(`Deseja realmente deletar o arquivo ${name}?`)) return;
        try {
            const res = await fetch(`http://localhost:8003/api/datalake/files/${layer}/${name}`, { method: 'DELETE' });
            const json = await res.json();
            if (json.status === 'ok') {
                if (filename === name) {
                    setData([]);
                    setFilename('');
                }
                fetchAvailableFiles(layer);
            } else {
                alert(`Erro: ${json.message}`);
            }
        } catch (e) {
            alert('Erro ao conectar com servidor');
        }
    };

    const handleProjectReset = async () => {
        if (!confirm('⚠️ ATENÇÃO: Isso irá apagar TODOS os arquivos de TODAS as camadas (Bronze, Prata, Kaká, Ouro) e PDFs. Confirma?')) return;
        if (!confirm('CONFIRMAÇÃO FINAL: Deseja apagar TUDO do projeto?')) return;
        
        try {
            const res = await fetch(`http://localhost:8003/api/datalake/reset`, { method: 'DELETE' });
            const json = await res.json();
            if (json.status === 'ok') {
                setData([]);
                setFilename('');
                fetchAvailableFiles(activeLayer);
                alert(`${json.removidos} arquivos removidos. Projeto limpo.`);
            }
        } catch (e) {
            alert('Erro ao resetar projeto');
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

    useEffect(() => {
        setCurrentPage(1);
    }, [search, sortConfig, activeLayer, data]);

    const totalPages = Math.max(1, Math.ceil(filtered.length / ROWS_PER_PAGE));
    const paginatedData = useMemo(() => {
        const start = (currentPage - 1) * ROWS_PER_PAGE;
        return filtered.slice(start, start + ROWS_PER_PAGE);
    }, [filtered, currentPage]);

    const totalValor = useMemo(() => data.reduce((s, r) => s + (parseFloat(r.valor) || 0), 0), [data]);
    const uniqueDeputados = useMemo(() => new Set(data.map(r => r.deputado)).size, [data]);
    const uniqueCnpjs = useMemo(() => new Set(data.map(r => r.cnpj_fornecedor).filter(Boolean)).size, [data]);

    const fieldStats = useMemo(() => {
        if (!data || data.length === 0) return { total: 0, filled: 0 };
        const keys = Object.keys(data[0]);
        let filledCount = 0;
        keys.forEach(k => {
            const isFilled = data.some(row => row[k] !== null && row[k] !== undefined && row[k] !== '');
            if (isFilled) filledCount++;
        });
        return { total: keys.length, filled: filledCount };
    }, [data]);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[200] flex bg-black/40 backdrop-blur-sm animate-in fade-in duration-300">
            <div className="absolute inset-0" onClick={onClose} />

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



                    <div className="flex-1 flex flex-col min-h-0">
                        <div className="flex items-center justify-between px-2 mb-4 shrink-0">
                            <h3 className="text-[10px] font-black text-[var(--text-tertiary)] uppercase tracking-widest flex items-center gap-2">
                                <span className="opacity-50">📂</span> Datasets Explorer
                            </h3>
                        </div>

                        <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-3 min-h-0">
                            {explorerTree.map(crew => (
                                <div key={crew.id} className="w-full">
                                    {/* CREW LEVEL */}
                                    <button 
                                        onClick={() => setExpandedCrews(p => ({...p, [crew.id]: !p[crew.id]}))}
                                        className="w-full flex items-center justify-between px-3 py-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.06] transition-all group border border-white/[0.02]"
                                    >
                                        <div className="flex items-center gap-2">
                                            <span className="text-sm">{crew.icon}</span>
                                            <span className="text-[10px] font-black text-white/80 uppercase tracking-widest group-hover:text-white transition-colors">{crew.name}</span>
                                        </div>
                                        <span className={`text-[8px] text-white/30 transition-transform duration-300 ${expandedCrews[crew.id] ? 'rotate-180' : ''}`}>▼</span>
                                    </button>

                                    <AnimatePresence>
                                        {expandedCrews[crew.id] && (
                                            <motion.div 
                                                initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                                                className="overflow-hidden pl-2 mt-2 space-y-2 border-l border-white/[0.05] ml-4"
                                            >
                                                {/* LAYER LEVEL */}
                                                {Object.keys(crew.layers).map(layerKey => {
                                                    const layerFiles = crew.layers[layerKey];
                                                    const lInfo = layers.find(l => l.key === layerKey) || { label: layerKey, icon: '📄', color: '#fff' };
                                                    const layerId = `${crew.id}-${layerKey}`;
                                                    const isExpLayer = expandedLayers[layerId];

                                                    return (
                                                        <div key={layerKey} className="w-full">
                                                            <button 
                                                                onClick={() => setExpandedLayers(p => ({...p, [layerId]: !p[layerId]}))}
                                                                className="w-full flex items-center justify-between px-2 py-1.5 rounded-lg hover:bg-white/[0.03] transition-all group/layer"
                                                            >
                                                                <div className="flex items-center gap-2">
                                                                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: lInfo.color, boxShadow: `0 0 5px ${lInfo.color}80` }} />
                                                                    <span className="text-[9px] font-bold text-white/60 uppercase tracking-widest group-hover/layer:text-white transition-colors">
                                                                        {lInfo.label} <span className="opacity-50">({layerFiles.length})</span>
                                                                    </span>
                                                                </div>
                                                            </button>

                                                            <AnimatePresence>
                                                                {isExpLayer && (
                                                                    <motion.div 
                                                                        initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                                                                        className="overflow-hidden pl-5 mt-1 space-y-1"
                                                                    >
                                                                        {layerFiles.length === 0 ? (
                                                                            <div className="px-2 py-1 text-[9px] text-white/20 italic">Vazio</div>
                                                                        ) : (
                                                                            layerFiles.map((f: string) => {
                                                                                const isSelected = filename === f && activeLayer === layerKey;
                                                                                let shortName = f.replace('_processed.json', '').replace('_gold.json', '').replace('.json', '');
                                                                                if (f.match(/_(\d{4})/)) shortName = `Safra ${f.match(/_(\d{4})/)![1]}`;
                                                                                
                                                                                return (
                                                                                    <div 
                                                                                        key={f}
                                                                                        onClick={() => {
                                                                                            onLayerChange(layerKey as Layer);
                                                                                            fetchData(layerKey as Layer, f);
                                                                                        }}
                                                                                        className={`group/file w-full flex items-center justify-between px-2 py-1.5 rounded-md cursor-pointer transition-all border border-transparent ${
                                                                                            isSelected ? 'bg-white/10 border-white/20 shadow-inner text-white' : 'hover:bg-white/[0.04] text-[var(--text-secondary)] hover:text-white'
                                                                                        }`}
                                                                                    >
                                                                                        <span className="text-[10px] font-mono-glass truncate flex-1" title={f}>{shortName}</span>
                                                                                        <button
                                                                                            onClick={(e) => { e.stopPropagation(); handleFileDelete(layerKey as Layer, f); }}
                                                                                            className="opacity-0 group-hover/file:opacity-100 text-red-500/50 hover:text-red-400 p-0.5"
                                                                                        >
                                                                                            ✕
                                                                                        </button>
                                                                                    </div>
                                                                                );
                                                                            })
                                                                        )}
                                                                    </motion.div>
                                                                )}
                                                            </AnimatePresence>
                                                        </div>
                                                    );
                                                })}
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="mt-4 pt-4 border-t border-white/[0.04] shrink-0">
                        <button 
                            onClick={handleProjectReset}
                            className="w-full group/reset flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-red-500/5 hover:bg-red-500/10 border border-red-500/10 transition-all text-[9px] font-black uppercase tracking-widest text-red-500/40 hover:text-red-400"
                        >
                            <span>Nuclear Reset</span>
                            <span className="text-xs group-hover/reset:animate-bounce">☢️</span>
                        </button>
                    </div>
                </div>

                <div className="flex-1 flex flex-col overflow-hidden bg-white/[0.01]">
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
                                        Viewing {filename || 'live_stream'} ({data.length})
                                        {activeLayer === 'parlamentares' && data.length > 0 && (
                                            <span className="ml-2 text-[var(--accent-green)] opacity-80">
                                                · 🕐 {new Date(data[data.length-1].processado_em).toLocaleString('pt-BR')}
                                            </span>
                                        )}
                                        {data.length > 0 && <span className="ml-3 px-2 py-0.5 rounded bg-[var(--accent-purple)]/10 text-[var(--accent-purple)] font-black uppercase shadow-inner border border-[var(--accent-purple)]/20">🧮 ~{Math.ceil(JSON.stringify(data).length / 4).toLocaleString('pt-BR')} Tokens</span>}
                                    </span>
                                </div>
                            </div>
                        </div>

                        <div className="flex bg-black/40 p-1.5 rounded-[18px] border border-white/[0.08] shadow-inner">
                            <button onClick={() => setViewMode('table')}
                                className={`px-6 py-2 rounded-xl text-[10px] font-black transition-all ${viewMode === 'table' ? 'bg-white/[0.1] text-white shadow-xl border border-white/10' : 'text-[var(--text-tertiary)] hover:text-white'}`}>
                                📊 EXPLORER
                            </button>
                            <button onClick={() => setViewMode('code')}
                                className={`px-6 py-2 rounded-xl text-[10px] font-black transition-all ${viewMode === 'code' ? 'bg-white/[0.1] text-white shadow-xl border border-white/10' : 'text-[var(--text-tertiary)] hover:text-white'}`}>
                                ⚛️ CODE 5X
                            </button>
                        </div>

                        <div className="flex items-center gap-4">
                            <div className="relative group">
                                <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Audit Search..."
                                    className="relative w-64 h-10 bg-black/40 border border-white/[0.08] rounded-xl px-4 pl-10 text-[11px] text-white outline-none focus:border-[var(--accent-purple)]/40 transition-all font-mono-glass" />
                                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-xs opacity-40">🔍</span>
                            </div>
                        </div>
                    </div>

                    <div className="flex-1 flex flex-col min-h-0">
                        {loading ? (
                            <div className="flex-1 flex flex-col items-center justify-center">
                                <div className="relative w-16 h-16 mb-6">
                                    <div className="absolute inset-0 border-4 border-[var(--accent-purple)]/10 rounded-full" />
                                    <div className="absolute inset-0 border-4 border-[var(--accent-purple)] border-t-transparent rounded-full animate-spin shadow-[0_0_20px_rgba(191,90,242,0.4)]" />
                                </div>
                                <span className="text-[10px] font-black text-[var(--accent-purple)] uppercase tracking-[0.3em] animate-pulse">Syncing...</span>
                            </div>
                        ) : viewMode === 'table' ? (
                            <div className="flex-1 flex flex-col p-6 min-h-0 bg-white/[0.01]">
                                <div className="flex items-center justify-between px-4 mb-5 shrink-0">
                                    <div className="flex items-center gap-8">
                                        <div className="flex flex-col">
                                            <div className="flex items-center gap-1.5 mb-1">
                                                <div className="w-1.5 h-1.5 rounded-full bg-[var(--accent-purple)] shadow-[0_0_8px_var(--accent-purple)]" />
                                                <span className="text-[8px] font-black text-[var(--accent-purple)] uppercase">Registros</span>
                                            </div>
                                            <span className="text-xl font-mono-glass text-white font-black">{data.length.toLocaleString('pt-BR')}</span>
                                        </div>
                                        <div className="w-px h-8 bg-white/5" />
                                        <div className="flex flex-col">
                                            <div className="flex items-center gap-1.5 mb-1">
                                                <div className="w-1.5 h-1.5 rounded-full bg-[var(--accent-green)]" />
                                                <span className="text-[8px] font-black text-[var(--accent-green)] uppercase">Financeiro</span>
                                            </div>
                                            <span className="text-xl font-mono-glass text-white font-black">{formatCurrency(totalValor)}</span>
                                        </div>
                                        <div className="w-px h-8 bg-white/5" />
                                        <div className="flex flex-col">
                                            <div className="flex items-center gap-1.5 mb-1">
                                                <div className="w-1.5 h-1.5 rounded-full bg-[#00f2fe]" />
                                                <span className="text-[8px] font-black text-[#00f2fe] uppercase">Schema</span>
                                            </div>
                                            <span className="text-xl font-mono-glass text-white font-black">{fieldStats.filled} / {fieldStats.total}</span>
                                        </div>
                                    </div>
                                </div>

                                <div className="rounded-[24px] overflow-auto custom-scrollbar border border-white/[0.06] bg-black/40 flex-1 relative">
                                    <table className="w-full text-left border-collapse min-w-[800px]">
                                        <thead>
                                            <tr className="bg-white/[0.02] border-b border-white/[0.06]">
                                                <th className="w-[60px] px-6 py-4 text-[9px] font-black text-[var(--text-tertiary)] uppercase text-center">ID</th>
                                                {columns.map(col => (
                                                    <th key={col.key} onClick={() => handleSort(col.key)} className={`${col.width} px-6 py-4 text-[9px] font-black text-[var(--text-tertiary)] uppercase cursor-pointer hover:bg-white/[0.04]`}>
                                                        {col.label}
                                                    </th>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {paginatedData.map((row, idx) => {
                                                const i = (currentPage - 1) * ROWS_PER_PAGE + idx;
                                                return (
                                                    <tr key={i} onClick={() => setSelectedRow(selectedRow === i ? null : i)} className={`cursor-pointer ${selectedRow === i ? 'bg-[var(--accent-purple)]/10' : 'hover:bg-white/[0.02]'}`}>
                                                        <td className="px-6 py-3.5 text-[10px] text-[var(--text-tertiary)] font-mono-glass text-center">{(i + 1).toString().padStart(3, '0')}</td>
                                                        {columns.map(col => {
                                                            const val = row[col.key];
                                                            const isUrl = typeof val === 'string' && val.startsWith('http');
                                                            
                                                            return (
                                                                <td key={col.key} className="px-6 py-3.5 text-[11px] text-[var(--text-secondary)]">
                                                                    {col.key === 'valor' || col.key === 'kaka_valor_nf' ? (
                                                                        <span className="text-[var(--accent-green)] font-bold">{val != null ? formatCurrency(val) : '—'}</span>
                                                                    ) : col.key === 'kaka_delta_valor' ? (
                                                                        val != null ? (
                                                                            <span className={`font-mono-glass font-bold ${Math.abs(val) > 0.10 ? 'text-red-400' : 'text-green-400'}`}>
                                                                                {val > 0 ? '+' : ''}{typeof val === 'number' ? val.toFixed(2) : val}
                                                                            </span>
                                                                        ) : <span className="opacity-30">—</span>
                                                                    ) : typeof val === 'boolean' ? (
                                                                        <span className={`px-2 py-0.5 rounded-full text-[9px] font-bold ${val ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 'bg-green-500/15 text-green-400 border border-green-500/20'}`}>
                                                                            {val ? 'SIM' : 'NAO'}
                                                                        </span>
                                                                    ) : col.key === 'kaka_status' ? (
                                                                        <span className={`px-2 py-0.5 rounded-full text-[9px] font-bold ${val === 'ok' ? 'bg-green-500/15 text-green-400' : val === 'manual' ? 'bg-yellow-500/15 text-yellow-400' : 'bg-red-500/15 text-red-400'}`}>
                                                                            {(val || '—').toUpperCase()}
                                                                        </span>
                                                                    ) : col.key === 'kaka_tipo_pdf' ? (
                                                                        <span className={`px-2 py-0.5 rounded-lg text-[9px] font-bold bg-white/5 border border-white/10`}>
                                                                            {val || '—'}
                                                                        </span>
                                                                    ) : col.key === 'kaka_confianca' ? (
                                                                        <div className="flex items-center gap-1.5">
                                                                            <div className="w-12 h-1.5 bg-white/10 rounded-full overflow-hidden">
                                                                                <div className="h-full rounded-full transition-all" style={{ width: `${val || 0}%`, background: (val || 0) > 70 ? '#34d399' : (val || 0) > 40 ? '#fbbf24' : '#f87171' }} />
                                                                            </div>
                                                                            <span className="text-[9px] font-mono-glass opacity-60">{val || 0}%</span>
                                                                        </div>
                                                                    ) : isUrl ? (
                                                                        <a href={val} target="_blank" rel="noopener noreferrer" 
                                                                           className="text-[var(--accent-blue)] hover:underline truncate block max-w-[200px]"
                                                                           onClick={(e) => e.stopPropagation()}>
                                                                            {val}
                                                                        </a>
                                                                    ) : (
                                                                        val ?? '—'
                                                                    )}
                                                                </td>
                                                            );
                                                        })}
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                                <div className="mt-4 flex items-center justify-between px-2">
                                    <span className="text-[10px] text-white/30 uppercase">Page {currentPage} of {totalPages}</span>
                                    <div className="flex gap-2">
                                        <button disabled={currentPage === 1} onClick={() => setCurrentPage(p => p - 1)} className="px-4 py-2 rounded-lg bg-black/40 border border-white/10 text-white/60 disabled:opacity-30">Anterior</button>
                                        <button disabled={currentPage === totalPages} onClick={() => setCurrentPage(p => p + 1)} className="px-4 py-2 rounded-lg bg-black/40 border border-white/10 text-white/60 disabled:opacity-30">Próxima</button>
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="flex-1 flex flex-col bg-black/30 m-6 rounded-[24px] border border-white/[0.04] overflow-hidden">
                                <div className="h-10 flex items-center justify-between px-6 bg-white/[0.02] border-b border-white/[0.06]">
                                    <div className="flex p-1 bg-white/5 rounded-lg space-x-1">
                                        <button onClick={() => setCodeTab('json')} className={`px-4 py-1 rounded-md text-[9px] font-black ${codeTab === 'json' ? 'bg-[var(--accent-purple)] text-white' : 'text-white/40'}`}>JSON</button>
                                        <button onClick={() => setCodeTab('source')} className={`px-4 py-1 rounded-md text-[9px] font-black ${codeTab === 'source' ? 'bg-[var(--accent-purple)] text-white' : 'text-white/40'}`}>SOURCE</button>
                                    </div>
                                </div>
                                <div className="flex-1 overflow-auto bg-black/20 p-6 custom-scrollbar">
                                    {codeTab === 'json' ? (
                                        <div className="space-y-4">
                                            {data.slice(0, 100).map((item, idx) => (
                                                <div key={idx} className="p-4 bg-white/[0.02] rounded-xl font-mono text-[11px] border border-white/5">
                                                    <pre className="text-white/60">{JSON.stringify(item, null, 2)}</pre>
                                                </div>
                                            ))}
                                            {data.length > 100 && <div className="text-center py-8 text-[10px] text-white/20 uppercase tracking-widest font-black">Restante omitido para performance...</div>}
                                        </div>
                                    ) : (
                                        <SyntaxHighlighter language="python" style={vscDarkPlus} customStyle={{ background: 'transparent', padding: 0 }}>{sourceCode}</SyntaxHighlighter>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                <AnimatePresence>
                    {selectedRow !== null && filtered[selectedRow] && (
                        <motion.div initial={{ x: 300 }} animate={{ x: 0 }} exit={{ x: 300 }} className="w-[400px] bg-black/80 border-l border-white/5 p-8 overflow-y-auto custom-scrollbar">
                            <div className="flex items-center justify-between mb-8">
                                <h4 className="text-lg font-black text-white uppercase tracking-tighter">Detalhes</h4>
                                <button onClick={() => setSelectedRow(null)} className="text-white/40 hover:text-white">✕</button>
                            </div>
                            <div className="space-y-6">
                                {Object.entries(filtered[selectedRow]).map(([k, v]) => (
                                    <div key={k}>
                                        <div className="text-[9px] text-white/30 uppercase font-black mb-1">{k}</div>
                                        <div className={`text-xs text-white/90 break-all bg-white/5 p-3 rounded-lg border border-white/5 font-mono-glass`}>
                                            {typeof v === 'string' && v.startsWith('http') ? (
                                                <a href={v} target="_blank" rel="noopener noreferrer" className="text-[var(--accent-blue)] hover:underline">
                                                    {v}
                                                </a>
                                            ) : (
                                                String(v ?? '—')
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
};

const StatLine = ({ label, value }: { label: string; value: string }) => (
    <div className="flex justify-between items-center text-[10px]">
        <span className="text-[var(--text-tertiary)]">{label}</span>
        <span className="text-white font-bold">{value}</span>
    </div>
);

export default StudioApproval;
