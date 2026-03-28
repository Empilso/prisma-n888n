import React, { memo, useState } from 'react';
import { Handle, Position } from 'reactflow';
import { motion, AnimatePresence } from 'framer-motion';
import AgentAvatar, { SKIN_CATALOG } from '../AgentAvatar';

interface BaseNodeProps {
    data: {
        id?: string;
        label: string;
        role?: string;
        avatar?: string;
        description?: string;
        tech?: 'python' | 'llm' | 'hybrid';
        status?: 'idle' | 'running' | 'success' | 'error';
        lastRun?: string;
        duration?: string;
        color?: string;
        onConfigClick?: () => void;
        onPlay?: (restart?: boolean, yearOverride?: string) => void;
        onStop?: () => void;
        inputReady?: boolean;
        config?: any;
        detail?: string;
        completedYears?: string[];
        checkpointYears?: string[];
        extractedYears?: string[];
        auditGaps?: Record<string, boolean>;
        availableInputYears?: string[];
        skinVariant?: string;
        onSkinChange?: (skin: string) => void;
        onRename?: (newName: string) => void;
    };
};

const roleColors: Record<string, string> = {
    Scraper: '#0a84ff',
    Refiner: '#ff9f0a',
    Analyst: '#bf5af2',
    Validator: '#30d158',
    Forensic: '#ff453a',
    Consolidator: '#5e5ce6',
};

const statusConfig: Record<string, { label: string; dot: string; glow?: string }> = {
    idle: { label: 'Em Espera', dot: 'bg-[var(--text-tertiary)]' },
    running: { label: 'Processando...', dot: 'bg-[var(--accent-purple)]', glow: 'shadow-[0_0_8px_rgba(191,90,242,0.6)]' },
    success: { label: 'Concluído', dot: 'bg-[var(--accent-green)]', glow: 'shadow-[0_0_8px_rgba(48,209,88,0.5)]' },
    error: { label: 'Erro', dot: 'bg-[var(--accent-red)]', glow: 'shadow-[0_0_8px_rgba(255,69,58,0.5)]' },
};

const techBadge: Record<string, { icon: string; label: string; color: string }> = {
    python: { icon: '🐍', label: 'Python', color: '#3776ab' },
    llm: { icon: '🧠', label: 'Inteligência', color: '#bf5af2' },
    hybrid: { icon: '⚡', label: 'Híbrido', color: '#ff9f0a' },
};

const BaseNode = ({ data }: BaseNodeProps) => {
    const status = data.status || 'idle';
    const isRunning = status === 'running';
    const [selectedYear, setSelectedYear] = useState<string | null>(null);
    const roleColor = data.color || roleColors[data.role || ''] || '#bf5af2';
    const sConf = statusConfig[status];
    const tech = data.tech ? techBadge[data.tech] : null;

    const [isEditingName, setIsEditingName] = useState(false);
    const [editNameValue, setEditNameValue] = useState(data.label);

    // Optimistic UI for skins
    const [localSkin, setLocalSkin] = useState<string | null>(null);
    const activeSkin = localSkin || data.skinVariant || 'default';

    const handleSkinSelection = async (sk: string, e: React.MouseEvent) => {
        e.stopPropagation();
        setLocalSkin(sk);
        try {
            await fetch(`http://localhost:8003/api/configure-prompt/${(data as any).id}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ skin_variant: sk })
            });
        } catch (err) { }
    };

    return (
        <div className={`agent-node group relative w-[270px] ${isRunning ? 'active' : ''}`}>
            <Handle type="target" position={Position.Left} className="!left-[-5px] !top-1/2" />

            {/* Active glow */}
            {isRunning && (
                <div className="absolute -inset-2 rounded-3xl animate-glow pointer-events-none"
                    style={{ background: `radial-gradient(circle, ${roleColor}12 0%, transparent 70%)` }} />
            )}

            {/* ═══ CLICKABLE BODY (opens Config) ═══ */}

            <div
                className="cursor-pointer relative"
                onClick={() => data.onConfigClick?.()}
            >
                {/* Header: avatar + name + role + tech badge */}
                <div className="p-4 pb-2 relative">

                    <div className="flex items-start gap-3">
                        {/* Avatar com animação de transição de skin */}
                        <div className="w-[72px] h-[72px] rounded-[18px] flex items-center justify-center shrink-0 overflow-visible shadow-[0_0_20px_rgba(50,205,50,0.1)] border-2 transform -translate-x-[5px] -translate-y-[5px]"
                            style={{ background: `${roleColor}18`, borderColor: `${roleColor}40` }}>

                            <AnimatePresence mode="wait">
                                <motion.div
                                    key={activeSkin}
                                    initial={{ scale: 0.3, rotateY: -90, opacity: 0, filter: 'blur(6px) brightness(3)' }}
                                    animate={{ scale: 1, rotateY: 0, opacity: 1, filter: 'blur(0px) brightness(1)' }}
                                    exit={{ scale: 1.3, rotateY: 90, opacity: 0, filter: 'blur(8px) brightness(4)' }}
                                    transition={{ type: 'spring', stiffness: 500, damping: 28, duration: 0.3 }}
                                    className="w-full h-full flex items-center justify-center agent-avatar-container"
                                >
                                    <AgentAvatar
                                        agentId={(data as any).id}
                                        size={101}
                                        skinVariant={activeSkin}
                                        className="transform translate-x-[-25%] translate-y-[-45%]"
                                    />
                                </motion.div>
                            </AnimatePresence>

                        </div>

                        <div className="flex-1 min-w-0 pt-0.5">
                            {isEditingName ? (
                                <input
                                    autoFocus
                                    className="w-full bg-black/50 border border-[var(--accent-purple)]/50 rounded px-1.5 py-0.5 text-[13px] font-semibold text-white outline-none"
                                    value={editNameValue}
                                    onChange={e => setEditNameValue(e.target.value)}
                                    onBlur={() => {
                                        setIsEditingName(false);
                                        if (editNameValue.trim() && editNameValue !== data.label) {
                                            data.onRename?.(editNameValue.trim());
                                        }
                                    }}
                                    onClick={e => e.stopPropagation()}
                                    onKeyDown={e => {
                                        if (e.key === 'Enter') {
                                            setIsEditingName(false);
                                            if (editNameValue.trim() && editNameValue !== data.label) {
                                                data.onRename?.(editNameValue.trim());
                                            }
                                        }
                                        if (e.key === 'Escape') {
                                            setIsEditingName(false);
                                            setEditNameValue(data.label);
                                        }
                                    }}
                                />
                            ) : (
                                <h3 
                                    className="text-[13px] font-semibold text-white truncate leading-tight group-hover:text-[var(--accent-purple)] transition-colors" 
                                    onDoubleClick={(e) => {
                                        e.stopPropagation();
                                        setEditNameValue(data.label);
                                        setIsEditingName(true);
                                    }}
                                    title="Dê um duplo-clique para renomear"
                                >
                                    {data.label}
                                </h3>
                            )}
                            <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                                {data.role && (
                                    <span className="inline-flex items-center px-1.5 py-0.5 rounded-md text-[8px] font-bold uppercase tracking-wider"
                                        style={{ background: `${roleColor}15`, color: roleColor }}>
                                        {data.role}
                                    </span>
                                )}
                                {tech && (
                                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[8px] font-bold"
                                        style={{ background: `${tech.color}15`, color: tech.color }}>
                                        {tech.icon} {tech.label}
                                    </span>
                                )}
                                {data.completedYears?.map((year: string) => (
                                    <span key={year} className="inline-flex items-center px-1.2 py-0.5 rounded-md text-[7px] font-bold bg-white/5 text-[var(--accent-green)] border border-[var(--accent-green)]/20 shadow-sm animate-in fade-in zoom-in duration-700">
                                        {year} <span className="ml-0.5 text-[6px]">✓</span>
                                    </span>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>

                {/* Description */}
                {data.description && (
                    <div className="px-4 pb-2">
                        <p className="text-[10px] leading-relaxed text-[var(--text-secondary)] opacity-70">
                            {data.description}
                        </p>
                    </div>
                )}

                {/* Status bar */}

                <div className="px-4 py-2 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${sConf.dot} ${sConf.glow || ''} ${isRunning ? 'animate-pulse' : ''}`} />
                        <span className="text-[10px] font-medium text-[var(--text-secondary)]">{sConf.label}</span>
                    </div>
                    {data.inputReady && (
                        <div className="flex flex-col items-end gap-1">
                            <div className="bg-[var(--accent-green)]/10 px-1.5 py-0.5 rounded text-[8px] font-bold text-[var(--accent-green)] border border-[var(--accent-green)]/20 animate-in fade-in zoom-in duration-500">
                                DADO DISPONÍVEL
                            </div>
                            {data.detail && (
                                <span className="text-[9px] text-[var(--accent-green)] opacity-80 font-medium">
                                    {data.detail}
                                </span>
                            )}
                        </div>
                    )}
                    {data.duration && !data.inputReady && (
                        <span className="text-[10px] font-mono-glass text-[var(--text-tertiary)]">{data.duration}</span>
                    )}
                </div>
            </div>

            {/* Divider */}
            <div className="mx-4 h-px bg-white/[0.04]" />

            {/* Action buttons — PREMIUM APPLE-STYLE BAR  */}
            <div className="px-3 py-2 flex items-center gap-2">

                {isRunning ? (
                    // ══ STATUS BAR EM EXECUÇÃO (SPLIT) ══
                    <>
                        <div className="flex-1 h-10 rounded-[14px] bg-[var(--accent-purple)]/10 border border-[var(--accent-purple)]/30 flex items-center justify-center gap-2 relative overflow-hidden shadow-[0_0_20px_rgba(191,90,242,0.15)] group cursor-default">
                            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/5 to-transparent animate-premium-glow" />
                            <div className="w-3 h-3 border-[1.5px] border-white/20 border-t-[var(--accent-purple)] rounded-full animate-spin shadow-[0_0_8px_rgba(191,90,242,0.8)]" />
                            <span className="text-[9px] font-black uppercase tracking-widest text-white/90 drop-shadow-md">
                                Ativo
                            </span>
                        </div>
                        <button
                            onClick={async (e) => {
                                e.stopPropagation();
                                try {
                                    await fetch(`http://localhost:8003/api/agent/${(data as any).id}/stop`, { method: 'DELETE' });
                                    data.onStop?.();
                                } catch (err) { }
                            }}
                            className="h-10 px-3 rounded-[14px] bg-red-500/15 border border-red-500/30 text-red-500 hover:bg-red-500/25 hover:border-red-500/50 transition-all flex items-center gap-1.5 shadow-[0_0_15px_rgba(255,69,58,0.2)] active:scale-95 group/stop"
                            title="INTERROMPER PROCESSO NO TERMINAL"
                        >
                            <span className="text-xs filter drop-shadow-[0_0_3px_rgba(255,69,58,0.8)] group-hover/stop:scale-125 transition-transform">🛑</span>
                            <span className="text-[8px] font-black uppercase tracking-wider">Parar</span>
                        </button>
                    </>
                ) : (
                    // ══ BOTÃO INICIAR / RESUMIR NORMAL ══
                    <button
                        onClick={(e) => { e.stopPropagation(); data.onPlay?.(false, selectedYear || undefined); }}
                        disabled={!data.inputReady && !selectedYear && !data.config?.ano}
                        className={`flex-1 h-10 rounded-[14px] flex items-center justify-center gap-2.5 transition-all active:scale-95 border relative overflow-hidden group/btn ${(!data.inputReady && !selectedYear && !data.config?.ano)
                            ? 'bg-white/5 border-white/5 text-white/10 opacity-30 cursor-not-allowed'
                            : (data.checkpointYears && data.checkpointYears.length > 0 && selectedYear && data.checkpointYears.includes(selectedYear))
                                ? 'bg-[var(--orange)]/20 border-[var(--orange)]/40 text-[var(--orange)] shadow-[0_0_20px_rgba(255,159,10,0.2)] hover:bg-[var(--orange)]/30 hover:border-[var(--orange)]/60'
                                : 'bg-[var(--accent-green)]/15 border-[var(--accent-green)]/30 text-[var(--accent-green)] shadow-[0_0_20px_rgba(50,205,50,0.15)] hover:bg-[var(--accent-green)]/25 hover:border-[var(--accent-green)]/50'
                            }`}
                    >
                        <div className="absolute inset-0 backdrop-blur-md opacity-20" />

                        <span className="text-sm filter drop-shadow-sm z-10 transition-transform group-hover/btn:scale-110">
                            {(data.checkpointYears && selectedYear && data.checkpointYears.includes(selectedYear)) ? '⏯️' : '▶️'}
                        </span>
                        <span className="text-[10px] font-black uppercase tracking-[0.2em] relative z-10 drop-shadow-[0_1px_2px_rgba(0,0,0,0.5)]">
                            {selectedYear
                                ? ((data.checkpointYears?.includes(selectedYear)) ? `Resumir ${selectedYear.slice(-2)}` : `Iniciar ${selectedYear.slice(-2)}`)
                                : ((data.checkpointYears && data.checkpointYears.length > 0) ? 'Resumir' : 'Iniciar')
                            }
                        </span>
                    </button>
                )}

                {/* ══ NOVO: MINI-LIMITE PARA KAKÁ ══ */}
                {(data.id === '3' || data.id === 'kaka') && !isRunning && (
                    <div className="flex flex-col gap-1 shrink-0">
                        <label className="text-[6px] font-black text-white/20 uppercase text-center">Limite</label>
                        <input 
                            type="number"
                            value={data.config?.limit || 3474}
                            onChange={async (e) => {
                                const val = parseInt(e.target.value);
                                e.stopPropagation();
                                try {
                                    await fetch(`http://localhost:8003/api/configure-prompt/${data.id}`, {
                                        method: 'POST',
                                        headers: { 'Content-Type': 'application/json' },
                                        body: JSON.stringify({ limit: val })
                                    });
                                } catch(err) {}
                            }}
                            className="w-12 h-10 glass border border-white/10 rounded-[14px] bg-black/40 text-[9px] font-black text-[var(--accent-blue)] text-center outline-none focus:border-[var(--accent-blue)]/40 transition-all font-mono-glass"
                            min="10"
                            max="3474"
                            onClick={(e) => e.stopPropagation()}
                            title="Limite de registros para esta rodada"
                        />
                    </div>
                )}

                {/* ══ REINICIAR (Discreto) ══ */}
                {!isRunning && (
                    <button
                        onClick={(e) => { e.stopPropagation(); data.onPlay?.(true); }}
                        className="w-10 h-10 glass border border-white/10 rounded-[14px] flex items-center justify-center text-[var(--accent-blue)] hover:bg-[var(--accent-blue)]/20 hover:border-[var(--accent-blue)]/30 transition-all active:scale-90 shrink-0"
                        title="Reiniciar Sourcing (do zero)"
                    >
                        <span className="text-base filter drop-shadow-sm group-hover:rotate-180 transition-transform duration-700">🔄</span>
                    </button>
                )}

                {/* ══ CONFIG (Minimalista) ══ */}
                <button
                    onClick={(e) => { e.stopPropagation(); data.onConfigClick?.(); }}
                    className="w-10 h-10 glass border border-white/10 rounded-[14px] flex items-center justify-center text-white/50 hover:text-white hover:bg-white/20 transition-all active:scale-90 shrink-0"
                    title="Diretrizes e Safra"
                >
                    <span className="text-base filter drop-shadow-sm">⚙️</span>
                </button>

                {/* ══ AUDITORIA (Agente 1) ══ */}
                {data.id === '1' && !isRunning && (
                    <button
                        onClick={async (e) => {
                            e.stopPropagation();
                            if (!selectedYear) {
                                alert("Selecione uma safra (bolinha com ano) para revisar o scrap!");
                                return;
                            }
                            try {
                                await fetch(`http://localhost:8003/api/run/agent_1/audit/${selectedYear}`, { method: 'POST' });
                            } catch (err) {
                                console.error(err);
                            }
                        }}
                        className={`h-10 px-3 glass border rounded-[14px] flex items-center justify-center transition-all bg-black/40 group/audit shrink-0
                            ${selectedYear ? 'border-[var(--accent-purple)]/50 text-[var(--accent-purple)] hover:bg-[var(--accent-purple)]/20 shadow-[0_0_15px_rgba(191,90,242,0.2)] cursor-pointer active:scale-95' 
                                           : 'border-white/10 text-white/20 cursor-not-allowed opacity-50'}`}
                        title="Revisar extração e gaps (Smart Sync)"
                    >
                        <span className="text-sm">🔍</span>
                        <span className="text-[8px] font-black uppercase tracking-widest hidden group-hover/audit:block ml-1">
                            {selectedYear ? `Review ${selectedYear}` : 'Selecione Safra'}
                        </span>
                    </button>
                )}

                {/* ══ TERMINAL (Discreto) ══ */}
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        (window as any).toggleTerminal?.((data as any).id);
                    }}
                    className="w-10 h-10 glass border border-white/10 rounded-[14px] flex items-center justify-center text-white/30 hover:text-[var(--accent-purple)] hover:bg-[var(--accent-purple)]/10 transition-all active:scale-90 shrink-0 group/term"
                    title="Ver processo no terminal"
                >
                    <span className="text-sm filter drop-shadow-sm group-hover/term:scale-110">📟</span>
                </button>
            </div>

            {/* ══ YEAR STATUS MAPPING (Aplicado a todos que processam safras) ══ */}
            {(!data.id?.startsWith('zidane')) && (
                <div className="px-5 pb-6 flex flex-col items-center gap-3">
                    <div className="w-full h-[1px] bg-white/5 mb-1" />
                    <div className="grid grid-cols-6 gap-3">
                        {[2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025].map(year => {
                            const isExtracted = data.extractedYears?.includes(year.toString());
                            const isCheckpoint = data.checkpointYears?.includes(year.toString());
                            const isSelected = selectedYear === year.toString();
                            const hasGap = data.auditGaps?.[year.toString()];

                            let color = 'bg-white/5 border-white/10';
                            let glow = '';
                            let labelColor = 'text-white/20';

                            if (hasGap) {
                                color = 'bg-red-500/20 border-red-500/50';
                                glow = 'shadow-[0_0_10px_rgba(255,0,0,0.5)]';
                                labelColor = 'text-red-400 font-bold';
                            } else if (isExtracted) {
                                color = 'bg-[var(--accent-green)] border-[var(--accent-green)]/40';
                                glow = 'shadow-[0_0_10px_rgba(50,205,50,0.4)]';
                                labelColor = 'text-[var(--accent-green)] font-bold';
                            } else if (isCheckpoint) {
                                color = 'bg-[var(--orange)] border-[var(--orange)]/40';
                                glow = 'shadow-[0_0_10px_rgba(255,159,10,0.4)]';
                                labelColor = 'text-[var(--orange)] font-bold';
                            }

                            // Highlight selection via Border
                            const ringStyle = isSelected ? 'ring-2 ring-white/50 ring-offset-1 ring-offset-black/50 scale-125' : '';

                            return (
                                <div
                                    key={year}
                                    onClick={(e) => { e.stopPropagation(); setSelectedYear(year.toString()); }}
                                    className="flex flex-col items-center gap-1.5 cursor-pointer group/yr"
                                    title={`${year}: Clique para selecionar. Status: ${isExtracted ? 'Extraído' : (isCheckpoint ? 'Pausado' : 'Não Iniciado')}`}
                                >
                                    <div className={`w-3.5 h-3.5 rounded-full border transition-all duration-300 ${color} ${glow} ${ringStyle} group-hover/yr:scale-110 flex items-center justify-center`}>
                                        {hasGap && <span className="text-[8px]">⚠️</span>}
                                    </div>
                                    <span className={`text-[8px] font-black tracking-tighter ${isSelected ? 'text-white' : labelColor} transition-colors group-hover/yr:text-white/70`}>
                                        {year.toString().slice(-2)}
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* ══ SKIN SELECTOR ══ */}
            {(!data.id?.startsWith('zidane')) && (
                <div className="px-4 pb-4 flex flex-col items-center gap-2" onClick={(e) => e.stopPropagation()}>
                    <div className="flex flex-wrap items-center justify-center gap-2 max-w-[150px]">
                        {SKIN_CATALOG.map(sk => {
                            const isActive = activeSkin === sk.key;
                            const c = sk.color;
                            return (
                                <motion.button
                                    key={sk.key}
                                    whileTap={{ scale: 0.8 }}
                                    onClick={(e) => handleSkinSelection(sk.key, e)}
                                    animate={isActive
                                        ? { scale: 1.3, boxShadow: `0 0 15px 2px ${c}66` }
                                        : { scale: 1, boxShadow: 'none' }
                                    }
                                    className={`w-[14px] h-[14px] rounded-full transition-opacity ${isActive ? 'opacity-100 ring-2 ring-white/80 ring-offset-2 ring-offset-black' : 'opacity-40 hover:opacity-100'}`}
                                    style={{
                                        background: sk.gradient ? `linear-gradient(135deg, ${sk.gradient[0]}, ${sk.gradient[1]})` : c
                                    }}
                                    title={sk.label}
                                />
                            );
                        })}
                    </div>
                </div>
            )}

            <Handle type="source" position={Position.Right} className="!right-[-5px] !top-1/2" />
        </div>
    );
};

export default memo(BaseNode);
