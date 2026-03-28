import React, { useState, useCallback, useMemo } from 'react';
import { crewDefs, type AgentDef, type CrewDef } from './crewDefs';

/* ═══════════════════════════════════════════════════════════════════════════════
   AgentLayersPanel v2 — Photoshop-Style Layer Manager POR CREW/PALCO
   
   • O painel mostra os agentes do PALCO ATIVO (selectedCrew)
   • O catálogo mostra TODOS os agentes do sistema para adicionar ao palco
   • Botão de retração/expansão com animação
   • Adicionar agentes ao palco ativo
   • Conectar/desconectar fios entre agentes
   • Remover agentes do palco ativo
   ═══════════════════════════════════════════════════════════════════════════════ */

// Extrai TODOS os agentes únicos de todas as Crews (catálogo do sistema)
function getAllAgents(): (AgentDef & { crewId: string; crewName: string; crewIcon: string; crewColor: string })[] {
    const seen = new Set<string>();
    const agents: (AgentDef & { crewId: string; crewName: string; crewIcon: string; crewColor: string })[] = [];
    crewDefs.forEach(crew => {
        crew.agents.forEach(agent => {
            const uid = `${crew.id}_${agent.id}`;
            if (!seen.has(uid)) {
                seen.add(uid);
                agents.push({ ...agent, crewId: crew.id, crewName: crew.name, crewIcon: crew.icon, crewColor: crew.color });
            }
        });
    });
    return agents;
}

export interface StageAgent {
    uid: string;
    agentId: string;
    crewId: string;
    name: string;
    role: string;
    description: string;
    tech: string;
    color: string;
    icon: string;
    enabled: boolean;
    order: number;
}

export interface Wire {
    from: string;
    to: string;
    enabled: boolean;
}

// Armazena stages POR CREW
export interface CrewStage {
    crewId: string;
    agents: StageAgent[];
    wires: Wire[];
}

interface AgentLayersPanelProps {
    selectedCrewId: string;
    stages: Record<string, CrewStage>;
    onStagesChange: (stages: Record<string, CrewStage>) => void;
    systemStatus?: any;
}

const TECH_BADGES: Record<string, { label: string; color: string }> = {
    python: { label: 'PY', color: '#3b82f6' },
    llm: { label: 'AI', color: '#f59e0b' },
    hybrid: { label: 'HY', color: '#10b981' },
};

const AgentLayersPanel: React.FC<AgentLayersPanelProps> = ({
    selectedCrewId,
    stages,
    onStagesChange,
    systemStatus,
}) => {
    const [isCollapsed, setIsCollapsed] = useState(false);
    const [isLibraryOpen, setIsLibraryOpen] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [expandedAgent, setExpandedAgent] = useState<string | null>(null);

    const allAgents = useMemo(() => getAllAgents(), []);

    // Stage do palco ativo
    const currentStage = stages[selectedCrewId] || { crewId: selectedCrewId, agents: [], wires: [] };
    const stageAgents = currentStage.agents;
    const wires = currentStage.wires;
    const stageUids = new Set(stageAgents.map(a => a.uid));

    // Crew atual info
    const currentCrew = crewDefs.find(c => c.id === selectedCrewId);

    // Helper: atualiza o stage da crew ativa
    const updateCurrentStage = useCallback((agents: StageAgent[], newWires: Wire[]) => {
        onStagesChange({
            ...stages,
            [selectedCrewId]: { crewId: selectedCrewId, agents, wires: newWires },
        });
    }, [stages, selectedCrewId, onStagesChange]);

    // Filtro de busca no catálogo
    const filteredLibrary = useMemo(() => {
        return allAgents.filter(a => {
            const uid = `${a.crewId}_${a.id}`;
            if (stageUids.has(uid)) return false;
            if (!searchTerm) return true;
            const term = searchTerm.toLowerCase();
            return a.name.toLowerCase().includes(term) || a.role.toLowerCase().includes(term) || a.crewName.toLowerCase().includes(term);
        });
    }, [allAgents, stageUids, searchTerm]);

    // Adicionar agente ao palco ativo
    const addToStage = useCallback((agent: ReturnType<typeof getAllAgents>[0]) => {
        const uid = `${agent.crewId}_${agent.id}`;
        if (stageUids.has(uid)) return;
        const newAgent: StageAgent = {
            uid, agentId: agent.id, crewId: agent.crewId,
            name: agent.name, role: agent.role, description: agent.description,
            tech: agent.tech, color: agent.crewColor, icon: agent.crewIcon,
            enabled: true, order: stageAgents.length,
        };
        const newAgents = [...stageAgents, newAgent];
        let newWires = [...wires];
        if (stageAgents.length > 0) {
            newWires.push({ from: stageAgents[stageAgents.length - 1].uid, to: uid, enabled: true });
        }
        updateCurrentStage(newAgents, newWires);
    }, [stageAgents, wires, stageUids, updateCurrentStage]);

    // Remover agente
    const removeFromStage = useCallback((uid: string) => {
        const newAgents = stageAgents.filter(a => a.uid !== uid);
        const newWires = wires.filter(w => w.from !== uid && w.to !== uid);
        updateCurrentStage(newAgents, newWires);
    }, [stageAgents, wires, updateCurrentStage]);

    // Toggle agente ON/OFF
    const toggleAgent = useCallback((uid: string) => {
        const newAgents = stageAgents.map(a => a.uid === uid ? { ...a, enabled: !a.enabled } : a);
        updateCurrentStage(newAgents, wires);
    }, [stageAgents, wires, updateCurrentStage]);

    // Toggle wire
    const toggleWire = useCallback((from: string, to: string) => {
        const newWires = wires.map(w => (w.from === from && w.to === to) ? { ...w, enabled: !w.enabled } : w);
        updateCurrentStage(stageAgents, newWires);
    }, [stageAgents, wires, updateCurrentStage]);

    // Remover wire
    const removeWire = useCallback((from: string, to: string) => {
        const newWires = wires.filter(w => !(w.from === from && w.to === to));
        updateCurrentStage(stageAgents, newWires);
    }, [stageAgents, wires, updateCurrentStage]);

    // Move agent order
    const moveAgent = useCallback((uid: string, dir: 'up' | 'down') => {
        const idx = stageAgents.findIndex(a => a.uid === uid);
        const swapIdx = dir === 'up' ? idx - 1 : idx + 1;
        if (swapIdx < 0 || swapIdx >= stageAgents.length) return;
        const newAgents = [...stageAgents];
        [newAgents[idx], newAgents[swapIdx]] = [newAgents[swapIdx], newAgents[idx]];
        newAgents.forEach((a, i) => a.order = i);
        updateCurrentStage(newAgents, wires);
    }, [stageAgents, wires, updateCurrentStage]);

    // Status do agente
    const getStatus = (id: string) => systemStatus?.agents?.[id]?.status || 'idle';

    // ─── COLLAPSED STATE ────────────────────────────────────────────────────────
    if (isCollapsed) {
        return (
            <div
                className="w-[36px] h-full flex flex-col items-center pt-4 shrink-0 z-50 cursor-pointer group"
                style={{
                    background: 'linear-gradient(180deg, rgba(20,20,30,0.98) 0%, rgba(12,12,20,0.99) 100%)',
                    borderLeft: '1px solid rgba(255,255,255,0.06)',
                }}
                onClick={() => setIsCollapsed(false)}
            >
                <div className="w-5 h-5 rounded flex items-center justify-center text-[10px] text-white/30 group-hover:text-white transition-colors mb-3"
                    title="Expandir Painel de Layers">
                    ◀
                </div>
                <div className="writing-mode-vertical text-[9px] font-black uppercase tracking-[0.3em] text-white/15 group-hover:text-white/40 transition-colors"
                    style={{ writingMode: 'vertical-lr', textOrientation: 'mixed' }}>
                    LAYERS
                </div>
                <div className="mt-3 flex flex-col gap-1.5">
                    {stageAgents.slice(0, 6).map(a => (
                        <div key={a.uid} className="w-2 h-2 rounded-full shrink-0" title={a.name}
                            style={{ background: a.enabled ? a.color : 'rgba(255,255,255,0.08)', boxShadow: a.enabled ? `0 0 4px ${a.color}40` : 'none' }} />
                    ))}
                </div>
            </div>
        );
    }

    // ─── EXPANDED STATE ─────────────────────────────────────────────────────────
    return (
        <div className="w-[260px] h-full flex flex-col shrink-0 z-50 transition-all duration-200"
            style={{
                background: 'linear-gradient(180deg, rgba(20,20,30,0.98) 0%, rgba(12,12,20,0.99) 100%)',
                borderLeft: '1px solid rgba(255,255,255,0.06)',
                boxShadow: '-4px 0 30px rgba(0,0,0,0.4)',
            }}>

            {/* ═══ HEADER ═══ */}
            <div className="px-3 pt-4 pb-2">
                <div className="flex items-center justify-between mb-0.5">
                    <div className="flex items-center gap-2">
                        <button onClick={() => setIsCollapsed(true)}
                            className="w-5 h-5 rounded flex items-center justify-center text-[9px] text-white/30 hover:text-white hover:bg-white/10 transition-all"
                            title="Recolher">▶</button>
                        <span className="text-[9px] font-black uppercase tracking-[0.2em] text-white/40">Layers</span>
                        <span className="text-[8px] px-1 py-0.5 rounded font-bold"
                            style={{ background: 'rgba(191,90,242,0.15)', color: '#bf5af2' }}>{stageAgents.length}</span>
                    </div>
                    <button onClick={() => setIsLibraryOpen(!isLibraryOpen)}
                        className="w-5 h-5 rounded-md flex items-center justify-center text-[10px] transition-all hover:scale-110 active:scale-95"
                        style={{
                            background: isLibraryOpen ? 'linear-gradient(135deg, #bf5af2, #5e5ce6)' : 'rgba(255,255,255,0.06)',
                            color: isLibraryOpen ? '#fff' : 'rgba(255,255,255,0.4)',
                        }}
                        title="Catálogo de Agentes">+</button>
                </div>

                {/* Crew Ativa Label */}
                {currentCrew && (
                    <div className="flex items-center gap-1.5 mt-1.5 px-1">
                        <span className="text-sm">{currentCrew.icon}</span>
                        <span className="text-[9px] font-bold text-white/50 truncate">{currentCrew.name}</span>
                        <span className="text-[7px] px-1 py-0.5 rounded bg-green-500/10 text-green-400 font-bold ml-auto shrink-0">PALCO</span>
                    </div>
                )}

                {/* Mini pipeline dots */}
                {stageAgents.length > 1 && (
                    <div className="flex items-center gap-0.5 mt-2 px-1 overflow-hidden">
                        {stageAgents.map((agent, i) => (
                            <React.Fragment key={agent.uid}>
                                <div className="w-1.5 h-1.5 rounded-full shrink-0 transition-all"
                                    style={{ background: agent.enabled ? agent.color : 'rgba(255,255,255,0.1)', boxShadow: agent.enabled ? `0 0 4px ${agent.color}50` : 'none' }}
                                    title={agent.name} />
                                {i < stageAgents.length - 1 && (() => {
                                    const wire = wires.find(w => w.from === agent.uid && w.to === stageAgents[i + 1]?.uid);
                                    return <div className="flex-1 h-px min-w-[4px] cursor-pointer transition-all"
                                        style={{ background: wire?.enabled ? `linear-gradient(90deg, ${agent.color}60, ${stageAgents[i + 1]?.color}60)` : 'rgba(255,255,255,0.05)' }}
                                        onClick={() => wire && toggleWire(wire.from, wire.to)} />;
                                })()}
                            </React.Fragment>
                        ))}
                    </div>
                )}
            </div>

            {/* ═══ CATÁLOGO (Todos os agentes do sistema) ═══ */}
            {isLibraryOpen && (
                <div className="mx-2 mb-2 rounded-lg overflow-hidden" style={{ background: 'rgba(191,90,242,0.04)', border: '1px solid rgba(191,90,242,0.12)' }}>
                    <div className="px-2.5 py-1.5 flex items-center gap-1.5 border-b border-white/[0.03]">
                        <span className="text-[9px]">🔍</span>
                        <input type="text" value={searchTerm} onChange={e => setSearchTerm(e.target.value)}
                            placeholder="Buscar em todos os agentes..."
                            className="flex-1 bg-transparent text-[10px] text-white/80 placeholder-white/20 outline-none" />
                        {searchTerm && <button onClick={() => setSearchTerm('')} className="text-[8px] text-white/20 hover:text-white">✕</button>}
                    </div>
                    <div className="max-h-[180px] overflow-y-auto custom-scrollbar">
                        {filteredLibrary.length === 0 ? (
                            <div className="px-3 py-3 text-center text-[9px] text-white/20">
                                {searchTerm ? 'Sem resultados' : '✅ Todos no palco!'}
                            </div>
                        ) : (
                            filteredLibrary.map(agent => {
                                const badge = TECH_BADGES[agent.tech] || TECH_BADGES.python;
                                return (
                                    <div key={`${agent.crewId}_${agent.id}`} onClick={() => addToStage(agent)}
                                        className="flex items-center gap-2 px-2.5 py-1.5 cursor-pointer transition-all hover:bg-white/[0.04] active:scale-[0.98] group">
                                        <span className="text-xs">{agent.crewIcon}</span>
                                        <div className="flex-1 min-w-0">
                                            <div className="text-[9px] font-bold text-white/60 truncate group-hover:text-white transition-colors">
                                                {agent.name.split(':')[0]}</div>
                                            <div className="text-[7px] text-white/25 truncate">{agent.crewName} › {agent.role}</div>
                                        </div>
                                        <span className="text-[6px] font-black px-1 py-0.5 rounded" style={{ background: `${badge.color}15`, color: `${badge.color}90` }}>{badge.label}</span>
                                        <span className="text-[9px] text-white/15 group-hover:text-green-400 transition-colors font-bold">+</span>
                                    </div>
                                );
                            })
                        )}
                    </div>
                </div>
            )}

            {/* ═══ LAYERS DO PALCO ATIVO ═══ */}
            <div className="flex-1 overflow-y-auto custom-scrollbar px-2">
                {stageAgents.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full gap-2 opacity-30">
                        <span className="text-2xl">📋</span>
                        <span className="text-[9px] font-bold text-white/40 text-center leading-relaxed">
                            Palco vazio<br /><span className="text-[var(--accent-purple)]">+</span> para montar
                        </span>
                    </div>
                ) : (
                    stageAgents.map((agent, idx) => {
                        const badge = TECH_BADGES[agent.tech] || TECH_BADGES.python;
                        const status = getStatus(agent.agentId);
                        const isRunning = status === 'running';
                        const isExpanded = expandedAgent === agent.uid;
                        const wireToNext = idx < stageAgents.length - 1
                            ? wires.find(w => w.from === agent.uid && w.to === stageAgents[idx + 1]?.uid)
                            : null;

                        return (
                            <React.Fragment key={agent.uid}>
                                <div className={`group rounded-lg mb-0.5 transition-all duration-200 ${agent.enabled ? '' : 'opacity-35'}`}
                                    style={{
                                        background: agent.enabled ? `linear-gradient(135deg, ${agent.color}06, transparent)` : 'rgba(255,255,255,0.01)',
                                        border: `1px solid ${agent.enabled ? `${agent.color}12` : 'rgba(255,255,255,0.02)'}`,
                                    }}>
                                    {/* Main Row */}
                                    <div className="flex items-center gap-1.5 px-2 py-1.5">
                                        <button onClick={() => toggleAgent(agent.uid)} className="w-4 h-4 rounded flex items-center justify-center text-[9px] transition-all hover:scale-110 shrink-0"
                                            style={{ color: agent.enabled ? agent.color : 'rgba(255,255,255,0.12)' }}
                                            title={agent.enabled ? 'Desativar' : 'Ativar'}>
                                            {agent.enabled ? '👁' : '◌'}
                                        </button>
                                        <div className="flex-1 min-w-0 cursor-pointer" onClick={() => setExpandedAgent(isExpanded ? null : agent.uid)}>
                                            <div className="flex items-center gap-1">
                                                <span className="text-[10px] font-bold text-white/85 truncate">{agent.name.split(':')[0]}</span>
                                                {isRunning && <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse shrink-0" style={{ boxShadow: '0 0 6px #4ade80' }} />}
                                            </div>
                                            <div className="text-[7px] text-white/25 truncate">{agent.role}</div>
                                        </div>
                                        <span className="text-[6px] font-black px-1 py-0.5 rounded shrink-0"
                                            style={{ background: `${badge.color}12`, color: `${badge.color}80` }}>{badge.label}</span>
                                        <div className="flex items-center gap-px opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                                            <button onClick={() => moveAgent(agent.uid, 'up')} className="w-3.5 h-3.5 rounded text-[7px] text-white/25 hover:text-white hover:bg-white/10 flex items-center justify-center">▲</button>
                                            <button onClick={() => moveAgent(agent.uid, 'down')} className="w-3.5 h-3.5 rounded text-[7px] text-white/25 hover:text-white hover:bg-white/10 flex items-center justify-center">▼</button>
                                            <button onClick={() => removeFromStage(agent.uid)} className="w-3.5 h-3.5 rounded text-[7px] text-white/25 hover:text-red-400 hover:bg-red-500/10 flex items-center justify-center">✕</button>
                                        </div>
                                    </div>

                                    {/* Expanded */}
                                    {isExpanded && (
                                        <div className="px-2.5 pb-2 pt-0.5 border-t border-white/[0.03]">
                                            <p className="text-[8px] text-white/35 leading-relaxed mb-1.5">{agent.description}</p>
                                            <div className="flex items-center gap-1.5 flex-wrap">
                                                <span className="text-[7px] px-1 py-0.5 rounded bg-white/[0.04] text-white/25 font-medium">{agent.icon} Crew {agent.crewId}</span>
                                                <span className="text-[7px] px-1 py-0.5 rounded font-medium"
                                                    style={{ background: `${agent.color}08`, color: `${agent.color}60` }}>
                                                    {status === 'running' ? '🔥 Ativo' : '⏸ Parado'}
                                                </span>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {/* Wire connector between agents */}
                                {wireToNext && (
                                    <div className="flex items-center justify-center py-px group/wire">
                                        <div className="flex items-center gap-0.5">
                                            <div className="w-2.5 h-px" style={{ background: wireToNext.enabled ? `${agent.color}50` : 'rgba(255,255,255,0.04)' }} />
                                            <button onClick={() => toggleWire(wireToNext.from, wireToNext.to)}
                                                className={`w-3 h-3 rounded-full flex items-center justify-center text-[6px] transition-all ${wireToNext.enabled ? 'text-green-400' : 'text-white/10 group-hover/wire:text-yellow-400'}`}
                                                style={{ background: wireToNext.enabled ? 'rgba(74,222,128,0.08)' : 'rgba(255,255,255,0.02)', border: `1px solid ${wireToNext.enabled ? 'rgba(74,222,128,0.15)' : 'rgba(255,255,255,0.04)'}` }}
                                                title={wireToNext.enabled ? 'Desligar fio' : 'Ligar fio'}>
                                                {wireToNext.enabled ? '⚡' : '○'}
                                            </button>
                                            <button onClick={() => removeWire(wireToNext.from, wireToNext.to)}
                                                className="w-3 h-3 rounded-full flex items-center justify-center text-[6px] text-white/0 group-hover/wire:text-red-400/50 transition-all hover:bg-red-500/10"
                                                title="Remover fio">✕</button>
                                            <div className="w-2.5 h-px" style={{ background: wireToNext.enabled ? `${stageAgents[idx + 1]?.color}50` : 'rgba(255,255,255,0.04)' }} />
                                        </div>
                                    </div>
                                )}

                                {/* Wire-less gap — offer to create wire */}
                                {!wireToNext && idx < stageAgents.length - 1 && (
                                    <div className="flex items-center justify-center py-px opacity-0 hover:opacity-100 transition-opacity">
                                        <button onClick={() => updateCurrentStage(stageAgents, [...wires, { from: agent.uid, to: stageAgents[idx + 1].uid, enabled: true }])}
                                            className="text-[7px] text-white/15 hover:text-green-400 transition-colors px-2"
                                            title="Criar fio">
                                            + fio
                                        </button>
                                    </div>
                                )}
                            </React.Fragment>
                        );
                    })
                )}
            </div>

            {/* ═══ FOOTER ═══ */}
            <div className="px-3 py-2.5 border-t border-white/[0.04]">
                <div className="flex items-center justify-between text-[8px] text-white/20 mb-1.5">
                    <span>{stageAgents.filter(a => a.enabled).length}/{stageAgents.length} ativos</span>
                    <span>{wires.filter(w => w.enabled).length} fios</span>
                </div>
                <button onClick={() => setIsLibraryOpen(!isLibraryOpen)}
                    className="w-full py-1.5 rounded-lg text-[8px] font-bold uppercase tracking-wider transition-all active:scale-95 hover:shadow-lg"
                    style={{ background: 'linear-gradient(135deg, #bf5af2, #5e5ce6)', color: '#fff' }}>
                    + Adicionar Agente
                </button>
            </div>
        </div>
    );
};

export default AgentLayersPanel;
