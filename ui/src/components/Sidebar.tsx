import React, { useState } from 'react';
import { crewDefs } from './crewDefs';

const statusBadge = {
    active: 'badge-active',
    paused: 'badge-paused',
    error: 'badge-error',
    standby: 'badge-paused', // Mapeando standby para o visual de pause/cinza
};

interface SidebarProps {
    selectedCrew?: string;
    onCrewSelect?: (id: string) => void;
}

const Sidebar = ({ selectedCrew = '1', onCrewSelect }: SidebarProps) => {
    const [hoveredCrew, setHoveredCrew] = useState<string | null>(null);

    return (
        <aside className="w-[220px] h-full glass-strong flex flex-col py-6 shrink-0 z-50">

            {/* Logo */}
            <div className="px-5 mb-8">
                <div className="flex items-center gap-3" onClick={() => window.location.reload()} style={{ cursor: 'pointer' }}>
                    <div className="w-9 h-9 rounded-2xl flex items-center justify-center"
                        style={{ background: 'linear-gradient(135deg, #bf5af2 0%, #5e5ce6 100%)' }}>
                        <span className="font-black text-white text-sm">N</span>
                    </div>
                    <div>
                        <h1 className="text-sm font-bold text-white tracking-tight leading-none">PRISMA</h1>
                        <span className="text-[10px] font-medium text-[var(--text-secondary)] tracking-wider uppercase">Motor 888</span>
                    </div>
                </div>
            </div>

            {/* Section Label */}
            <div className="px-5 mb-3 flex items-center justify-between">
                <span className="text-[10px] font-semibold text-[var(--text-tertiary)] uppercase tracking-widest">Fluxos de Dados</span>
                <button className="w-5 h-5 rounded-md flex items-center justify-center text-[var(--text-tertiary)] hover:text-white hover:bg-white/5 transition-all text-xs">
                    +
                </button>
            </div>

            {/* Crew List */}
            <nav className="flex-1 px-3 space-y-1 overflow-y-auto custom-scrollbar">
                {crewDefs.map(crew => {
                    const isSelected = selectedCrew === crew.id;
                    const status = isSelected ? 'active' : 'standby';

                    return (
                        <div
                            key={crew.id}
                            onClick={() => onCrewSelect?.(crew.id)}
                            onMouseEnter={() => setHoveredCrew(crew.id)}
                            onMouseLeave={() => setHoveredCrew(null)}
                            className={`group flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-all duration-200 ${isSelected
                                ? 'bg-white/[0.08] shadow-sm'
                                : 'hover:bg-white/[0.04]'
                                }`}
                        >
                            <div className="text-lg w-8 h-8 rounded-xl flex items-center justify-center shrink-0 border border-white/5 transition-transform group-hover:scale-110"
                                style={{
                                    background: isSelected ? `${crew.color}20` : 'rgba(255,255,255,0.03)',
                                    color: crew.color
                                }}>
                                {crew.icon}
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between gap-2">
                                    <span className={`text-[11px] font-bold truncate tracking-tight ${isSelected ? 'text-white' : 'text-[var(--text-secondary)]'}`}>
                                        {crew.name}
                                    </span>
                                    <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${(statusBadge as any)[status]} ${status === 'active' ? 'animate-glow' : ''}`} />
                                </div>
                                <div className="flex items-center gap-2 mt-0.5">
                                    <span className="text-[9px] font-medium text-[var(--text-tertiary)] uppercase tracking-wider">{crew.agents.length} AGENTES</span>
                                    {isSelected && <span className="text-[8px] px-1 rounded bg-[var(--accent-green)]/10 text-[var(--accent-green)] font-bold">LIVE</span>}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </nav>

            {/* Bottom User Profile */}
            <div className="px-5 pt-4 mt-4 border-t border-white/[0.04]">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-600 to-indigo-600 flex items-center justify-center text-[10px] font-bold text-white shadow-lg border border-white/10">MV</div>
                    <div className="min-w-0">
                        <div className="text-[11px] font-bold text-white truncate">Mestre Valério</div>
                        <div className="text-[9px] text-[var(--text-tertiary)] font-medium">Licença Diamante</div>
                    </div>
                </div>
            </div>
        </aside>
    );
};

export default Sidebar;
