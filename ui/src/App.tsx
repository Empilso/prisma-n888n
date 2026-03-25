import React, { useState, useEffect } from 'react';
import CrewFlow from './components/CrewFlow';
import TerminalPanel from './components/TerminalPanel';
import AgentDetailsDrawer from './components/AgentDetailsDrawer';
import Sidebar from './components/Sidebar';
import StudioApproval from './components/StudioApproval';
import { crewDefs } from './components/crewDefs';

function App() {
    const [selectedAgent, setSelectedAgent] = useState<{ id: string; label: string } | null>(null);
    const [systemStatus, setSystemStatus] = useState<any>({});
    const [selectedCrew, setSelectedCrew] = useState('1');
    const [isStudioOpen, setIsStudioOpen] = useState(false);
    const [studioLayer, setStudioLayer] = useState<'bronze' | 'prata' | 'ouro'>('prata');

    // Poll system status
    useEffect(() => {
        const interval = setInterval(async () => {
            try {
                const res = await fetch('http://localhost:8001/api/status');
                const data = await res.json();
                setSystemStatus(data);
            } catch (e) { /* silent */ }
        }, 2000);
        return () => clearInterval(interval);
    }, []);

    const runCrew = async () => {
        await fetch('http://localhost:8001/api/run-crew', { method: 'POST' });
    };

    const stopCrew = async () => {
        await fetch('http://localhost:8001/api/stop-crew', { method: 'POST' });
    };

    // Mapeamento dos agentes ativos para as Crews correspondentes (ex: 'Crew 1', 'Crew 0')
    const activeAgents = systemStatus?.active_channels || [];
    const activeCrews = Array.from(new Set(activeAgents.map((a: string) => {
        const agId = a.replace('agent_', ''); // Normalizar ID se necessário
        const crew = crewDefs.find(c => c.agents.some(ag => ag.id === agId || ag.id === a));
        return crew ? `Crew ${crew.id} (${crew.name.split(':')[0]})` : null;
    }).filter(Boolean)));

    return (
        <div className="h-screen w-screen flex overflow-hidden bg-[var(--bg-deep)]">

            {/* Banner Global Minimalista de Execução */}
            {activeCrews.length > 0 && (
                <div className="absolute top-0 left-0 right-0 h-7 bg-gradient-to-r from-transparent via-[var(--accent-purple)]/20 to-transparent flex items-center justify-center z-[100] border-b border-[var(--accent-purple)]/30 shadow-[0_0_20px_rgba(191,90,242,0.15)] backdrop-blur-sm">
                    <span className="text-[10px] font-black uppercase tracking-[0.2em] text-[var(--accent-purple)] drop-shadow-md flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent-purple)] animate-pulse shadow-[0_0_8px_currentColor]" />
                        O console está rodando n{activeCrews.length > 1 ? 'as' : 'a'} {activeCrews.join(' e ')}...
                    </span>
                </div>
            )}

            {/* ═══ LEFT PANEL — Crew Manager ═══ */}
            <Sidebar selectedCrew={selectedCrew} onCrewSelect={setSelectedCrew} />

            {/* ═══ CENTER — Canvas + Toolbar + Terminal ═══ */}
            <div className="flex-1 flex flex-col overflow-hidden relative">

                {/* Floating Toolbar */}
                <div className="absolute top-5 left-1/2 -translate-x-1/2 z-50">
                    <div className="glass px-2 py-1.5 rounded-2xl flex items-center gap-1 shadow-2xl">
                        <ToolBtn icon="▶" label="Rodar Tudo" accent onClick={runCrew} />
                        <ToolBtn icon="⏸" label="Pausar" onClick={stopCrew} />
                        <div className="w-px h-5 bg-white/[0.06] mx-1" />
                        <ToolBtn icon="📊" label="Estúdio" onClick={() => setIsStudioOpen(true)} />
                        <ToolBtn icon="⊞" label="Grade" />
                    </div>
                </div>

                {/* Canvas */}
                <main className="flex-1 relative">
                    <CrewFlow
                        selectedCrewId={selectedCrew}
                        onAgentSelect={setSelectedAgent}
                        systemStatus={systemStatus?.agents || {}}
                    />
                </main>

                {/* Terminal */}
                <TerminalPanel />
            </div>

            {/* ═══ RIGHT PANEL — Inspector ═══ */}
            <AgentDetailsDrawer
                isOpen={!!selectedAgent}
                onClose={() => setSelectedAgent(null)}
                agentId={selectedAgent?.id || null}
                agentLabel={selectedAgent?.label || ''}
                selectedCrewId={selectedCrew}
                onOpenStudio={(layer) => {
                    setStudioLayer(layer);
                    setIsStudioOpen(true);
                    setSelectedAgent(null);
                }}
                systemStatus={systemStatus}
                inputReady={selectedAgent ? (systemStatus?.agents?.[selectedAgent.id]?.input_ready) : false}
            />

            {/* Studio Approval Overlay */}
            <StudioApproval
                isOpen={isStudioOpen}
                onClose={() => setIsStudioOpen(false)}
                activeLayer={studioLayer}
                onLayerChange={setStudioLayer}
            />

            {/* Subtle noise overlay for texture */}
            <div className="fixed inset-0 pointer-events-none bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-[0.015] mix-blend-overlay z-[100]" />
        </div>
    );
}

/* Reusable Toolbar Button */
function ToolBtn({ icon, label, accent, onClick }: { icon: string; label: string; accent?: boolean; onClick?: () => void }) {
    return (
        <button
            onClick={onClick}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[10px] font-semibold transition-all active:scale-95 ${accent
                ? 'text-white hover:bg-white/10'
                : 'text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06]'
                }`}
            style={accent ? { background: 'linear-gradient(135deg, #bf5af2 0%, #5e5ce6 100%)' } : undefined}
        >
            <span>{icon}</span> {label}
        </button>
    );
}

export default App;
