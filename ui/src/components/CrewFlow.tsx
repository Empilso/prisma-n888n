import React, { useMemo, useCallback, useEffect } from 'react';
import ReactFlow, {
    Background,
    Controls,
    MiniMap,
    NodeTypes,
    useNodesState,
    useEdgesState,
    Node,
    Edge,
} from 'reactflow';
import 'reactflow/dist/style.css';
import BaseNode from './nodes/BaseNode';
import { crewDefs } from './crewDefs';

const NODE_TYPES: NodeTypes = {
    custom: BaseNode,
};

const DEFAULT_EDGE_OPTIONS = {
    type: 'smoothstep',
    style: { strokeWidth: 2, stroke: 'rgba(255,255,255,0.08)' },
};

const STORAGE_KEY = 'prisma888_node_positions';

const MINIMAP_NODE_COLOR = (n: { data: { status?: string } }) => {
    if (n.data.status === 'running') return 'rgba(57, 255, 20, 0.4)';
    return 'rgba(255, 255, 255, 0.05)';
};

const FIT_VIEW_OPTIONS = { padding: 0.1 };

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

    // Memoize the current crew definition
    const currentCrew = useMemo(() =>
        crewDefs.find(c => c.id === selectedCrewId) || crewDefs[0],
        [selectedCrewId]);

    // Callbacks estáveis
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
                ano: y.toString(),
                mes: m.toString(),
                municipio: mun,
                provider: prov,
                model: mod,
                filename: file,
                restart: restart.toString()
            });

            await fetch(`http://localhost:8001/api/run-agent/${id}?${params.toString()}`, { method: 'POST' });
        } catch (e) { }
    }, [systemStatus]);

    const handleStop = useCallback(async (id: string) => {
        try {
            await fetch(`http://localhost:8001/api/stop-agent/${id}`, { method: 'POST' });
        } catch (e) { }
    }, []);

    // ─── NODES & EDGES INICIAIS ───
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);

    // Efeito para trocar a Crew (Reseta grafos e carrega posições FRESCAS)
    useEffect(() => {
        const freshPositions = loadPositions();

        const newNodes: Node[] = currentCrew.agents.map(a => ({
            id: a.id,
            type: 'custom',
            position: freshPositions[`${selectedCrewId}_${a.id}`] || a.defaultPos,
            data: {
                id: a.id,
                label: a.name,
                role: a.role,
                tech: a.tech,
                description: a.description,
                warning: a.warning,
                status: 'idle',
                inputReady: systemStatus?.agents?.[a.id]?.input_ready,
                skinVariant: systemStatus?.agents?.[a.id]?.skin_variant || 'default',
                onConfigClick: () => handleAgentSelect({ id: a.id, label: a.name }),
                onPlay: (restart?: boolean, yearOverride?: string) => handlePlay(a.id, yearOverride, restart),
                onStop: () => handleStop(a.id),
                completedYears: systemStatus?.agents?.[a.id]?.completed_years,
                checkpointYears: systemStatus?.agents?.[a.id]?.checkpoint_years,
                extractedYears: systemStatus?.agents?.[a.id]?.extracted_years,
                config: systemStatus?.agents?.[a.id]?.config,
            },
        }));

        // Topologia Dinâmica
        const newEdges: Edge[] = [];

        if (selectedCrewId === '1') {
            // Topologia ALBA Reorganizada: Romário (1) -> Bebeto (2) -> Kaká (kaka) -> Dunga (3)
            newEdges.push({ id: 'e1-2', source: '1', target: '2' });
            newEdges.push({ id: 'e2-kaka', source: '2', target: 'kaka' });
            newEdges.push({ id: 'ekaka-3', source: 'kaka', target: '3' });
            // Agentes Legados/Auditores (4, 5, 6) agora pendentes ou integrados se necessário
            newEdges.push({ id: 'e3-6', source: '3', target: '6' });
            newEdges.push({ id: 'e4-6', source: '4', target: '6' });
            newEdges.push({ id: 'e5-6', source: '5', target: '6' });
        } else {
            // Topologia sequencial padrão para as demais crews (1->2->3->4)
            if (currentCrew.agents.length >= 2) newEdges.push({ id: 'e1-2', source: '1', target: '2' });
            if (currentCrew.agents.length >= 3) newEdges.push({ id: 'e2-3', source: '2', target: '3' });
            if (currentCrew.agents.length >= 4) newEdges.push({ id: 'e3-4', source: '3', target: '4' });
        }

        setNodes(newNodes);
        setEdges(newEdges.map(e => ({
            ...e,
            type: 'smoothstep',
            style: { strokeWidth: 2, stroke: 'rgba(255,255,255,0.08)' },
            animated: systemStatus?.agents?.[e.source]?.status === 'running'
        })));
    }, [currentCrew, selectedCrewId, handleAgentSelect, handlePlay, handleStop]);

    // Efeito para sincronizar STATUS (Polling)
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

                if (
                    n.data.status === newStatus &&
                    n.data.inputReady === newInputReady &&
                    n.data.detail === newDetail &&
                    n.data.skinVariant === newSkin &&
                    JSON.stringify(n.data.completedYears) === JSON.stringify(newCompletedYears) &&
                    JSON.stringify(n.data.checkpointYears) === JSON.stringify(newCheckpointYears)
                ) return n;

                return {
                    ...n,
                    data: {
                        ...n.data,
                        status: newStatus,
                        inputReady: newInputReady,
                        detail: newDetail,
                        skinVariant: newSkin,
                        completedYears: newCompletedYears,
                        checkpointYears: newCheckpointYears,
                        availableInputYears: newAvailableInputYears,
                    },
                };
            })
        );

        setEdges(eds =>
            eds.map(e => {
                const isRunning = systemStatus?.agents?.[e.source]?.status === 'running';
                if (e.animated === isRunning) return e;
                return { ...e, animated: isRunning };
            })
        );
    }, [systemStatus]);

    const handleNodesChange = useCallback(
        (changes: any) => {
            onNodesChange(changes);
            const hasPositionChange = changes.some((c: any) => c.type === 'position' && c.dragging === false);
            if (hasPositionChange) {
                setNodes(current => {
                    const positions: Record<string, { x: number; y: number }> = loadPositions();
                    current.forEach(n => {
                        positions[`${selectedCrewId}_${n.id}`] = n.position;
                    });
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(positions));
                    return current;
                });
            }
        },
        [onNodesChange, setNodes, selectedCrewId]
    );

    return (
        <div className="h-full w-full liquid-canvas">
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={handleNodesChange}
                onEdgesChange={onEdgesChange}
                nodeTypes={NODE_TYPES}
                fitView
                snapToGrid
                snapGrid={[28, 28]}
                defaultEdgeOptions={DEFAULT_EDGE_OPTIONS}
            >
                <Background color="rgba(255,255,255,0.015)" gap={28} size={1} />
                <Controls showInteractive={false} position="bottom-left" />
                <MiniMap
                    nodeColor={MINIMAP_NODE_COLOR}
                    maskColor="rgba(0, 0, 0, 0.7)"
                    position="bottom-right"
                    pannable
                    zoomable
                />
            </ReactFlow>
        </div>
    );
};

export default CrewFlow;
