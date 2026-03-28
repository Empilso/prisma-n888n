import React, { useMemo, useCallback, useEffect, useState } from 'react';
import ReactFlow, {
    Background,
    Controls,
    MiniMap,
    NodeTypes,
    useNodesState,
    useEdgesState,
    Node,
    Edge,
    addEdge,
    Connection,
} from 'reactflow';
import 'reactflow/dist/style.css';
import BaseNode from './nodes/BaseNode';
import { crewDefs, type AgentDef } from './crewDefs';

const NODE_TYPES: NodeTypes = {
    custom: BaseNode,
};

const DEFAULT_EDGE_OPTIONS = {
    type: 'smoothstep',
    style: { strokeWidth: 2, stroke: 'rgba(255,255,255,0.08)' },
};

const STORAGE_KEY = 'prisma888_node_positions';
const STAGE_KEY = 'prisma888_crew_stages';
const STORAGE_KEY_EDGES = 'prisma888_node_edges';

function getSavedEdges(crewId: string): Edge[] | null {
    try {
        const raw = localStorage.getItem(STORAGE_KEY_EDGES);
        if (raw) {
            const data = JSON.parse(raw);
            if (data[crewId]) return data[crewId];
        }
    } catch {}
    return null;
}

// Global debounced save function
let saveTimeout: any = null;
function asyncSaveConfigToBackend() {
    clearTimeout(saveTimeout);
    saveTimeout = setTimeout(async () => {
        try {
            const data = {
                positions: JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'),
                stages: JSON.parse(localStorage.getItem(STAGE_KEY) || '{}'),
                edges: JSON.parse(localStorage.getItem(STORAGE_KEY_EDGES) || '{}')
            };
            await fetch('http://localhost:8003/api/stage/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
        } catch (e) {}
    }, 1000);
}

function saveCrewEdges(crewId: string, edges: Edge[]) {
    try {
        const raw = localStorage.getItem(STORAGE_KEY_EDGES);
        const data = raw ? JSON.parse(raw) : {};
        data[crewId] = edges;
        localStorage.setItem(STORAGE_KEY_EDGES, JSON.stringify(data));
        asyncSaveConfigToBackend();
    } catch {}
}

const MINIMAP_NODE_COLOR = (n: { data: { status?: string } }) => {
    if (n.data.status === 'running') return 'rgba(57, 255, 20, 0.4)';
    return 'rgba(255, 255, 255, 0.05)';
};

const FIT_VIEW_OPTIONS = { padding: 0.1 };

const TECH_BADGES: Record<string, { label: string; color: string }> = {
    python: { label: 'PY', color: '#3b82f6' },
    llm: { label: 'AI', color: '#f59e0b' },
    hybrid: { label: 'HY', color: '#10b981' },
};

// ─── Catálogo de TODOS os agentes do sistema ────────────────────────────────
function getAllAgents() {
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

const ALL_AGENTS = getAllAgents();

// ─── Stage persistence per crew ─────────────────────────────────────────────
interface StageData {
    agentIds: string[]; // uid = crewId_agentId
    removedIds: string[]; // agents explicitly removed
    customNames?: Record<string, string>; // uid -> user customized names
}

function loadStages(): Record<string, StageData> {
    try {
        const raw = localStorage.getItem(STAGE_KEY);
        if (raw) return JSON.parse(raw);
    } catch { }
    return {};
}

function saveStages(stages: Record<string, StageData>) {
    localStorage.setItem(STAGE_KEY, JSON.stringify(stages));
    asyncSaveConfigToBackend();
}

// ─────────────────────────────────────────────────────────────────────────────

interface CrewFlowProps {
    onAgentSelect: (agent: { id: string; label: string }) => void;
    systemStatus: any;
    selectedCrewId: string;
}

function loadPositions(): Record<string, { x: number; y: number }> {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        return saved ? JSON.parse(saved) : {};
    } catch {
        return {};
    }
}

const CrewFlow = ({ onAgentSelect, systemStatus, selectedCrewId }: CrewFlowProps) => {
    const [isLayersOpen, setIsLayersOpen] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [isLoaded, setIsLoaded] = useState(false);
    const [stages, setStages] = useState<Record<string, StageData>>({});
    const [bgEnabled, setBgEnabled] = useState(() => {
        const stored = localStorage.getItem('prisma888_bg_enabled');
        return stored !== 'false'; // true by default
    });
    const [bgScale, setBgScale] = useState(() => {
        const stored = localStorage.getItem('prisma888_bg_scale');
        return stored ? parseFloat(stored) : 100; // base 100%
    });
    const BG_OPTIONS = [
        'https://images.unsplash.com/photo-1462331940025-496dfbfc7564?q=80&w=2048&auto=format&fit=crop',
        '/space-bg-2.png',
        'https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2048&auto=format&fit=crop',
        'https://images.unsplash.com/photo-1534447677768-be436bb09401?q=80&w=2048&auto=format&fit=crop',
    ];
    const [bgIndex, setBgIndex] = useState(() => {
        const stored = localStorage.getItem('prisma888_bg_index');
        return stored ? parseInt(stored) : 0;
    });

    useEffect(() => {
        fetch('http://localhost:8003/api/stage/load')
            .then(res => res.json())
            .then(data => {
                if (data.positions && Object.keys(data.positions).length > 0) localStorage.setItem(STORAGE_KEY, JSON.stringify(data.positions));
                if (data.stages && Object.keys(data.stages).length > 0) {
                    localStorage.setItem(STAGE_KEY, JSON.stringify(data.stages));
                    setStages(data.stages);
                } else {
                    setStages(loadStages());
                }
                if (data.edges && Object.keys(data.edges).length > 0) localStorage.setItem(STORAGE_KEY_EDGES, JSON.stringify(data.edges));
                setIsLoaded(true);
            })
            .catch(() => {
                setStages(loadStages());
                setIsLoaded(true);
            });
    }, []);

    const currentCrew = useMemo(() =>
        crewDefs.find(c => c.id === selectedCrewId) || crewDefs[0],
        [selectedCrewId]);

    // Agentes neste palco: default da crew + adicionados manualmente - removidos
    const stageAgentList = useMemo(() => {
        const stageData = stages[selectedCrewId];
        const crewAgentUids = currentCrew.agents.map(a => `${selectedCrewId}_${a.id}`);

        if (!stageData) {
            // Sem customização: mostra os agentes originais da crew
            return crewAgentUids;
        }

        // Base: agentes originais da crew que não foram removidos
        const base = crewAgentUids.filter(uid => !stageData.removedIds.includes(uid));
        // Adiciona os agentes adicionados manualmente
        const added = stageData.agentIds.filter(uid => !base.includes(uid));
        return [...base, ...added];
    }, [selectedCrewId, currentCrew, stages]);

    // Resolve UIDs para objetos AgentDef completos
    const resolvedAgents = useMemo(() => {
        return stageAgentList.map(uid => {
            const match = ALL_AGENTS.find(a => `${a.crewId}_${a.id}` === uid);
            return match ? { ...match, uid } : null;
        }).filter(Boolean) as (typeof ALL_AGENTS[0] & { uid: string })[];
    }, [stageAgentList]);

    // UIDs no palco para filtrar o catálogo
    const stageUids = new Set(stageAgentList);

    // ─── Stage mutations ────────────────────────────────────────────────────
    const addAgentToStage = useCallback((uid: string) => {
        const current = stages[selectedCrewId] || { agentIds: [], removedIds: [] };
        // Se estava na lista de removidos, tira de lá
        const newRemoved = current.removedIds.filter(id => id !== uid);
        // Adiciona se não é um agente default da crew
        const crewUids = currentCrew.agents.map(a => `${selectedCrewId}_${a.id}`);
        let newIds = [...current.agentIds];
        if (!crewUids.includes(uid) && !newIds.includes(uid)) {
            newIds.push(uid);
        }
        const newStages = {
            ...stages,
            [selectedCrewId]: { agentIds: newIds, removedIds: newRemoved },
        };
        setStages(newStages);
        saveStages(newStages);
    }, [stages, selectedCrewId, currentCrew]);

    const removeAgentFromStage = useCallback((uid: string) => {
        const current = stages[selectedCrewId] || { agentIds: [], removedIds: [] };
        const newIds = current.agentIds.filter(id => id !== uid);
        const newRemoved = [...current.removedIds];
        if (!newRemoved.includes(uid)) newRemoved.push(uid);
        const newStages = {
            ...stages,
            [selectedCrewId]: { agentIds: newIds, removedIds: newRemoved },
        };
        setStages(newStages);
        saveStages(newStages);
    }, [stages, selectedCrewId]);

    // Catálogo filtrado (todos os agentes do sistema que NÃO estão neste palco)
    const filteredCatalog = useMemo(() => {
        return ALL_AGENTS.filter(a => {
            const uid = `${a.crewId}_${a.id}`;
            if (stageUids.has(uid)) return false;
            if (!searchTerm) return true;
            const term = searchTerm.toLowerCase();
            return a.name.toLowerCase().includes(term) || a.role.toLowerCase().includes(term) || a.crewName.toLowerCase().includes(term);
        });
    }, [stageUids, searchTerm]);

    // ─── Callbacks estáveis ─────────────────────────────────────────────────
    const handleAgentSelect = useCallback((agent: { id: string; label: string }) => {
        onAgentSelect(agent);
    }, [onAgentSelect]);

    const handlePlay = useCallback(async (id: string, year: string = '2015', restart: boolean = false) => {
        try {
            const config = systemStatus?.agents?.[id]?.config || {};
            const y = year || config.ano || '2015';
            const m = config.mes || 0;
            const mun = config.municipio || 'Salvador';
            const prov = config.provider || 'groq';
            const mod = config.model || 'llama-3.3-70b-versatile';
            const file = config.filename || '';

            const params = new URLSearchParams({
                ano: y.toString(), mes: m.toString(), municipio: mun,
                provider: prov, model: mod, filename: file, restart: restart.toString()
            });

            await fetch(`http://localhost:8003/api/run-agent/${id}?${params.toString()}`, { method: 'POST' });
        } catch (e) { }
    }, [systemStatus]);

    const handleStop = useCallback(async (id: string) => {
        try {
            await fetch(`http://localhost:8003/api/stop-agent/${id}`, { method: 'POST' });
        } catch (e) { }
    }, []);

    // ─── NODES & EDGES ──────────────────────────────────────────────────────
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);

    // Rebuild nodes/edges when crew changes OR stage agents change
    useEffect(() => {
        const freshPositions = loadPositions();

        const newNodes: Node[] = resolvedAgents.map((a, idx) => ({
            id: a.id,
            type: 'custom',
            position: freshPositions[`${selectedCrewId}_${a.id}`] || a.defaultPos || { x: 80 + idx * 340, y: 80 + (idx % 2) * 200 },
            data: {
                id: a.id,
                label: stages?.[selectedCrewId]?.customNames?.[a.uid] || a.name,
                uid: a.uid,
                role: a.role,
                tech: a.tech,
                description: a.description,
                warning: (a as any).warning,
                status: 'idle',
                inputReady: systemStatus?.agents?.[a.id]?.input_ready,
                skinVariant: systemStatus?.agents?.[a.id]?.skin_variant || 'default',
                onConfigClick: () => handleAgentSelect({ id: a.id, label: a.name }),
                onPlay: (restart?: boolean, yearOverride?: string) => handlePlay(a.id, yearOverride, restart),
                onStop: () => handleStop(a.id),
                completedYears: systemStatus?.agents?.[a.id]?.completed_years,
                checkpointYears: systemStatus?.agents?.[a.id]?.checkpoint_years,
                extractedYears: systemStatus?.agents?.[a.id]?.extracted_years,
                auditGaps: systemStatus?.agents?.[a.id]?.audit_gaps,
                config: systemStatus?.agents?.[a.id]?.config,
                onRename: (newName: string) => {
                    setStages(prev => {
                        const s = prev[selectedCrewId] || { agentIds: [], removedIds: [] };
                        const newS = {
                            ...prev,
                            [selectedCrewId]: {
                                ...s,
                                customNames: {
                                    ...(s.customNames || {}),
                                    [a.uid]: newName
                                }
                            }
                        };
                        saveStages(newS);
                        return newS;
                    });
                }
            },
        }));

        // Edges: topologia sequencial inicial OU bordas salvas
        const savedEdges = getSavedEdges(selectedCrewId);
        
        if (savedEdges && savedEdges.length > 0) {
            // Reaplica estado animado baseado no sistema atual
            const newEdges = savedEdges.map((e: Edge) => ({
                ...e,
                animated: systemStatus?.agents?.[e.source]?.status === 'running',
            }));
            setEdges(newEdges);
        } else {
            // Padrão para a crew
            const agentIds = resolvedAgents.map(a => a.id);
            const newEdges: Edge[] = [];
            for (let i = 0; i < agentIds.length - 1; i++) {
                newEdges.push({
                    id: `e-${agentIds[i]}-${agentIds[i + 1]}`,
                    source: agentIds[i],
                    target: agentIds[i + 1],
                    type: 'smoothstep',
                    style: { strokeWidth: 2, stroke: 'rgba(255,255,255,0.08)' },
                    animated: systemStatus?.agents?.[agentIds[i]]?.status === 'running',
                });
            }
            setEdges(newEdges);
        }

        setNodes(newNodes);
    }, [resolvedAgents, selectedCrewId, handleAgentSelect]); // Notice we drop functions that change frequently

    // ─── Polling status sync ────────────────────────────────────────────────
    useEffect(() => {
        setNodes(nds =>
            nds.map(n => {
                const s = systemStatus?.agents?.[n.id];
                if (!s && n.data.status === 'idle') return n;
                const newStatus = s?.status || 'idle';
                const newInputReady = s?.input_ready || false;
                const newDetail = s?.detail;
                const newSkin = s?.skin_variant || n.data.skinVariant || 'default';
                const newCompletedYears = s?.completed_years;
                const newCheckpointYears = s?.checkpoint_years;
                const newAvailableInputYears = s?.available_input_years;
                const newAuditGaps = s?.audit_gaps;
                if (n.data.status === newStatus && n.data.inputReady === newInputReady && n.data.detail === newDetail && n.data.skinVariant === newSkin &&
                    JSON.stringify(n.data.completedYears) === JSON.stringify(newCompletedYears) && JSON.stringify(n.data.checkpointYears) === JSON.stringify(newCheckpointYears) && JSON.stringify(n.data.auditGaps) === JSON.stringify(newAuditGaps)) return n;
                return { ...n, data: { ...n.data, status: newStatus, inputReady: newInputReady, detail: newDetail, skinVariant: newSkin, completedYears: newCompletedYears, checkpointYears: newCheckpointYears, availableInputYears: newAvailableInputYears, auditGaps: newAuditGaps } };
            })
        );
        setEdges(eds => eds.map(e => {
            const isRunning = systemStatus?.agents?.[e.source]?.status === 'running';
            if (e.animated === isRunning) return e;
            return { ...e, animated: isRunning };
        }));
    }, [systemStatus]);

    const onNodesChangeWithSave = useCallback((changes: any) => {
        onNodesChange(changes);
        const hasPositionChange = changes.some((c: any) => c.type === 'position' && c.dragging === false);
        if (hasPositionChange) {
            setTimeout(() => {
                setNodes(currentNodes => {
                    const positions = loadPositions();
                    currentNodes.forEach(n => {
                        positions[`${selectedCrewId}_${n.id}`] = n.position;
                    });
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(positions));
                    asyncSaveConfigToBackend();
                    return currentNodes;
                });
            }, 0);
        }
    }, [onNodesChange, selectedCrewId]);

    const onConnect = useCallback((connection: Connection) => {
        setEdges((eds) => addEdge({ ...connection, type: 'smoothstep', style: { strokeWidth: 2, stroke: 'rgba(255,255,255,0.15)' } }, eds));
    }, [setEdges]);

    const onNodesDeleteHandler = useCallback((deleted: any[]) => {
        deleted.forEach(node => {
            if (node.data && node.data.uid) {
                removeAgentFromStage(node.data.uid);
            }
        });
    }, [removeAgentFromStage]);

    // Salva mudanças de conexões automaticamente
    useEffect(() => {
        if (edges && edges.length > 0) {
            saveCrewEdges(selectedCrewId, edges);
        } else if (edges && edges.length === 0) {
            // Se o usuário apagar TUDO, salva o array vazio também
            saveCrewEdges(selectedCrewId, []);
        }
    }, [edges, selectedCrewId]);

    // ─── RENDER ─────────────────────────────────────────────────────────────
    if (!isLoaded) {
        return <div className="w-full h-full flex items-center justify-center text-white/50 bg-[#050505] font-mono-glass tracking-widest uppercase text-xs animate-pulse">
            <span className="mr-3 text-lg">⚙️</span> Calibrando e carregando Estado Persistente da Orquestração...
        </div>;
    }

    const bgUrl = BG_OPTIONS[bgIndex] || BG_OPTIONS[0];

    return (
        <div className="h-full w-full liquid-canvas relative overflow-hidden bg-[#050505]">
            
            {/* Opcional Space BG */}
            {bgEnabled && (
                <div 
                    className="absolute inset-0 z-0 pointer-events-none opacity-[0.35] transition-transform mix-blend-screen"
                    style={{
                        backgroundImage: `url(${bgUrl})`,
                        backgroundSize: `${bgScale}%`,
                        backgroundPosition: 'center',
                        backgroundRepeat: 'repeat'
                    }} 
                />
            )}
            
            {/* Toggle BG Button e Slider */}
            <div className="absolute top-4 left-4 z-50 flex flex-col gap-2">
                <button
                    onClick={() => {
                        setBgEnabled(v => {
                            const n = !v;
                            localStorage.setItem('prisma888_bg_enabled', String(n));
                            return n;
                        });
                    }}
                    className="h-9 px-3 glass border border-white/5 rounded-full flex items-center justify-center gap-2 text-white/50 hover:text-[var(--accent-blue)] hover:bg-white/10 transition-all font-mono-glass text-[10px] shadow-lg backdrop-blur-md"
                    title="Alternar Imagem Sideral"
                >
                    <span className="text-sm">🌌</span> {bgEnabled ? 'OCULTAR ESPAÇO' : 'MOSTRAR ESPAÇO'}
                </button>
                {bgEnabled && (
                    <div className="flex items-center gap-2 px-3 py-2 glass border border-white/5 rounded-2xl flex-col bg-black/40 backdrop-blur-md">
                        <span className="text-[9px] font-mono-glass text-white/40 tracking-widest uppercase">Zoom</span>
                        <input 
                            type="range" 
                            min="10" 
                            max="300" 
                            value={bgScale}
                            onChange={(e) => {
                                const val = Number(e.target.value);
                                setBgScale(val);
                                localStorage.setItem('prisma888_bg_scale', String(val));
                            }}
                            className="w-24 h-1 bg-white/10 rounded-full appearance-none outline-none accent-[var(--accent-blue)]"
                        />
                        <div className="flex gap-2 mt-1">
                            {BG_OPTIONS.map((bg, idx) => (
                                <button
                                    key={idx}
                                    onClick={() => {
                                        setBgIndex(idx);
                                        localStorage.setItem('prisma888_bg_index', String(idx));
                                    }}
                                    className={`w-3 h-3 rounded-full transition-all duration-300 border ${bgIndex === idx ? 'border-white scale-125' : 'border-white/20 hover:border-white/50'}`}
                                    style={{ background: `url(${bg})`, backgroundSize: 'cover' }}
                                    title={`Fundo ${idx + 1}`}
                                />
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {/* A ReactFlow div precisa ser transparente se quisermos ver o BG */}
            <div className="absolute inset-0 z-10">
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChangeWithSave}
                    onNodesDelete={onNodesDeleteHandler}
                    onEdgesChange={onEdgesChange}
                    onConnect={onConnect}
                    nodeTypes={NODE_TYPES}
                    fitView
                    snapToGrid
                    snapGrid={[20, 20]}
                    deleteKeyCode={['Backspace', 'Delete']}
                    elementsSelectable={true}
                    edgesFocusable={true}
                    defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
                >
                    {/* Background nativo translúcido */}
                    <Background color="rgba(255,255,255,0.02)" gap={28} size={1} style={{ background: 'transparent' }} />
                <Controls showInteractive={false} position="bottom-left" />
            </ReactFlow>
            </div>

            {/* ═══ LAYERS PANEL — Flutuante DENTRO do palco ═══ */}
            <div className="absolute top-2 right-2 z-[40]" style={{ pointerEvents: 'auto' }}>

                {/* Toggle Button */}
                {!isLayersOpen && (
                    <button onClick={() => setIsLayersOpen(true)}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-[9px] font-bold uppercase tracking-wider transition-all hover:scale-105 active:scale-95 shadow-xl"
                        style={{
                            background: 'linear-gradient(135deg, rgba(30,30,45,0.95), rgba(20,20,35,0.98))',
                            border: '1px solid rgba(191,90,242,0.2)',
                            color: 'rgba(191,90,242,0.8)',
                            backdropFilter: 'blur(16px)',
                        }}>
                        <span>🛸</span> Agentes <span style={{ background: 'rgba(191,90,242,0.15)', padding: '1px 4px', borderRadius: '4px', fontSize: '8px' }}>{resolvedAgents.length}</span>
                    </button>
                )}

                {/* Panel */}
                {isLayersOpen && (
                    <div className="w-[240px] rounded-xl overflow-hidden shadow-2xl"
                        style={{
                            background: 'linear-gradient(180deg, rgba(18,18,28,0.97) 0%, rgba(10,10,18,0.99) 100%)',
                            border: '1px solid rgba(255,255,255,0.06)',
                            backdropFilter: 'blur(20px)',
                            maxHeight: 'calc(100vh - 200px)',
                        }}>

                        {/* Header */}
                        <div className="px-3 py-2.5 flex items-center justify-between border-b border-white/[0.04]">
                            <div className="flex items-center gap-2">
                                <span className="text-xs">{currentCrew.icon}</span>
                                <span className="text-[9px] font-black uppercase tracking-[0.15em] text-white/50">{currentCrew.name}</span>
                            </div>
                            <button onClick={() => setIsLayersOpen(false)}
                                className="w-5 h-5 rounded-md flex items-center justify-center text-[9px] text-white/30 hover:text-white hover:bg-white/10 transition-all"
                                title="Fechar">✕</button>
                        </div>

                        {/* Agent List */}
                        <div className="max-h-[250px] overflow-y-auto custom-scrollbar">
                            {resolvedAgents.map((agent, idx) => {
                                const badge = TECH_BADGES[agent.tech] || TECH_BADGES.python;
                                const status = systemStatus?.agents?.[agent.id]?.status || 'idle';
                                const isRunning = status === 'running';
                                return (
                                    <div key={agent.uid} className="group flex items-center gap-1.5 px-2.5 py-1.5 border-b border-white/[0.02] hover:bg-white/[0.03] transition-all">
                                        {/* Eye toggle */}
                                        <span className="text-[9px] shrink-0" style={{ color: agent.crewColor }}>👁</span>
                                        {/* Info */}
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-1">
                                                <span className="text-[9px] font-bold text-white/80 truncate">{agent.name.split(':')[0]}</span>
                                                {isRunning && <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse shrink-0" />}
                                            </div>
                                            <div className="text-[7px] text-white/20 truncate">{agent.role}</div>
                                        </div>
                                        {/* Badge */}
                                        <span className="text-[6px] font-black px-1 py-0.5 rounded shrink-0"
                                            style={{ background: `${badge.color}12`, color: `${badge.color}80` }}>{badge.label}</span>
                                        {/* Remove */}
                                        <button onClick={() => removeAgentFromStage(agent.uid)}
                                            className="w-3.5 h-3.5 rounded text-[7px] text-white/0 group-hover:text-red-400/60 hover:bg-red-500/10 flex items-center justify-center transition-all shrink-0"
                                            title="Remover do palco">✕</button>
                                    </div>
                                );
                            })}
                            {resolvedAgents.length === 0 && (
                                <div className="px-3 py-6 text-center text-[9px] text-white/20">
                                    Nenhuma nave na órbita — adicione agentes abaixo
                                </div>
                            )}
                        </div>

                        {/* Separator */}
                        <div className="px-2.5 py-1.5 border-t border-white/[0.04] flex items-center gap-1.5">
                            <span className="text-[8px] font-bold text-white/25 uppercase tracking-wider">Catálogo</span>
                            <input type="text" value={searchTerm} onChange={e => setSearchTerm(e.target.value)}
                                placeholder="buscar..."
                                className="flex-1 bg-transparent text-[9px] text-white/60 placeholder-white/15 outline-none" />
                        </div>

                        {/* Catalog */}
                        <div className="max-h-[160px] overflow-y-auto custom-scrollbar">
                            {filteredCatalog.length === 0 ? (
                                <div className="px-3 py-3 text-center text-[8px] text-white/15">
                                    {searchTerm ? 'Sem resultados na galáxia' : '👽 Todos em órbita'}
                                </div>
                            ) : (
                                filteredCatalog.map(agent => {
                                    const uid = `${agent.crewId}_${agent.id}`;
                                    const badge = TECH_BADGES[agent.tech] || TECH_BADGES.python;
                                    return (
                                        <div key={uid} onClick={() => addAgentToStage(uid)}
                                            className="group flex items-center gap-1.5 px-2.5 py-1.5 cursor-pointer hover:bg-white/[0.04] active:scale-[0.98] transition-all">
                                            <span className="text-[10px]">{agent.crewIcon}</span>
                                            <div className="flex-1 min-w-0">
                                                <div className="text-[8px] font-bold text-white/50 truncate group-hover:text-white/80 transition-colors">{agent.name.split(':')[0]}</div>
                                                <div className="text-[6px] text-white/15 truncate">{agent.crewName}</div>
                                            </div>
                                            <span className="text-[5px] font-black px-1 py-0.5 rounded" style={{ background: `${badge.color}10`, color: `${badge.color}60` }}>{badge.label}</span>
                                            <span className="text-[9px] text-white/10 group-hover:text-green-400 transition-colors font-bold">+</span>
                                        </div>
                                    );
                                })
                            )}
                        </div>

                        {/* Footer */}
                        <div className="px-2.5 py-2 border-t border-white/[0.04] flex items-center justify-between">
                            <span className="text-[7px] text-white/15">{resolvedAgents.length} agentes · {edges.length} fios</span>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default CrewFlow;
