import React, { useState } from 'react';
import { crewDefs } from './crewDefs';

const statusBadge = {
    active: 'badge-active',
    paused: 'badge-paused',
    error: 'badge-error',
    standby: 'badge-paused',
};

// Mapeamento exclusivo de ícones alienígenas para o modo retrato
const ALIEN_ICONS: Record<string, string> = {
    '1': '👽', // ALBA
    '2': '👾', // TST
    '3': '🛸', // TSE
    '4': '🛰️', // TCM-BA
    '5': '🪐', // TC-SP
    '6': '☄️', // TCU
    '7': '🌌', // CGU
    '8': '🚀', // SIGA
    '9': '🧑‍🚀', // IBGE
    '10': '🌑', // RECEITA
    '11': '🧝', // RADAR
};

interface SidebarProps {
    selectedCrew?: string;
    onCrewSelect?: (id: string) => void;
}

const Sidebar = ({ selectedCrew = '1', onCrewSelect }: SidebarProps) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [hoveredCrew, setHoveredCrew] = useState<string | null>(null);

    return (
        <aside 
            className={`${isExpanded ? 'w-[240px]' : 'w-[70px]'} h-full flex flex-col py-6 shrink-0 z-50 transition-all duration-300 ease-[cubic-bezier(0.25,1,0.5,1)] border-r border-white/[0.04] relative group/sidebar`}
            style={{
                background: 'linear-gradient(180deg, rgba(8,8,12,0.95), rgba(4,4,8,0.98))',
                backdropFilter: 'blur(20px)',
            }}
        >
            {/* Toggle Button (Hover area) */}
            <button 
                onClick={() => setIsExpanded(!isExpanded)}
                className="absolute -right-3 top-8 w-6 h-12 bg-[#0a0a0f] border border-white/10 rounded-full flex items-center justify-center opacity-0 group-hover/sidebar:opacity-100 transition-opacity z-10 shadow-[0_0_15px_rgba(191,90,242,0.2)] hover:bg-[#151520]"
            >
                <div className="text-white/40 text-[10px] transform data-[expanded=true]:rotate-180 transition-transform duration-300" data-expanded={isExpanded}>❯</div>
            </button>

            {/* Logo */}
            <div className={`px-4 mb-8 flex items-center ${isExpanded ? 'justify-start' : 'justify-center'} transition-all`} onClick={() => window.location.reload()} style={{ cursor: 'pointer' }}>
                <div className="w-10 h-10 rounded-2xl flex items-center justify-center shrink-0 shadow-[0_0_20px_rgba(191,90,242,0.4)]"
                    style={{ background: 'linear-gradient(135deg, #bf5af2 0%, #5e5ce6 100%)' }}>
                    <span className="font-black text-white text-[15px]">A</span>
                </div>
                {isExpanded && (
                    <div className="ml-3 animate-fade-in whitespace-nowrap overflow-hidden">
                        <h1 className="text-sm font-black text-white tracking-widest leading-none drop-shadow-md">ANTIGRAVITY</h1>
                        <span className="text-[9px] font-bold text-[var(--accent-purple)] tracking-[0.2em] uppercase">Motor 888</span>
                    </div>
                )}
            </div>

            {/* Section Label */}
            {isExpanded && (
                <div className="px-5 mb-3 flex items-center justify-between whitespace-nowrap overflow-hidden animate-fade-in">
                    <span className="text-[9px] font-black text-white/30 uppercase tracking-[0.2em]">Frota Estelar</span>
                </div>
            )}
            {!isExpanded && (
                <div className="w-full h-px bg-white/5 mb-4 max-w-[40px] mx-auto" />
            )}

            {/* Crew List */}
            <nav className="flex-1 px-3 space-y-2 overflow-y-auto custom-scrollbar overflow-x-hidden">
                {crewDefs.map(crew => {
                    const isSelected = selectedCrew === crew.id;
                    const alienIcon = ALIEN_ICONS[crew.id] || '👾';

                    return (
                        <div
                            key={crew.id}
                            onClick={() => onCrewSelect?.(crew.id)}
                            onMouseEnter={() => setHoveredCrew(crew.id)}
                            onMouseLeave={() => setHoveredCrew(null)}
                            className={`flex items-center rounded-2xl cursor-pointer transition-all duration-300 relative group overflow-hidden ${isSelected
                                ? 'bg-white/[0.06] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.1)]'
                                : 'hover:bg-white/[0.03]'
                                } ${isExpanded ? 'px-3 py-2.5' : 'p-2 justify-center'}`}
                        >
                            {isSelected && (
                                <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-[var(--accent-purple)] to-[var(--accent-blue)] shadow-[0_0_15px_var(--accent-purple)]" />
                            )}

                            {/* Icon (Always Visible) */}
                            <div 
                                className={`text-xl flex items-center justify-center shrink-0 transition-all duration-300 ${isSelected ? 'scale-110 drop-shadow-[0_0_10px_rgba(255,255,255,0.3)]' : 'opacity-60 group-hover:opacity-100 group-hover:scale-110'}`}
                                title={isExpanded ? '' : crew.name}
                            >
                                {isExpanded ? crew.icon : alienIcon}
                            </div>

                            {/* Expanded Content */}
                            {isExpanded && (
                                <div className="ml-3 flex-1 min-w-0 animate-fade-in whitespace-nowrap">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className={`text-[11px] font-black tracking-tight truncate ${isSelected ? 'text-white' : 'text-white/60 group-hover:text-white/80'}`}>
                                            {crew.name.split(':')[0]}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-1 mt-0.5">
                                        <span className="text-[8px] font-bold text-[var(--accent-purple)] uppercase tracking-wider">{crew.agents.length} Nave{crew.agents.length !== 1 ? 's' : ''}</span>
                                    </div>
                                </div>
                            )}

                            {/* Status Indicator (Collapsed state tooltip) */}
                            {!isExpanded && isSelected && (
                                <div className="absolute right-1 top-1 w-1.5 h-1.5 rounded-full bg-[var(--accent-green)] animate-pulse shadow-[0_0_5px_var(--accent-green)]" />
                            )}
                        </div>
                    );
                })}
            </nav>

            {/* Bottom User Profile */}
            <div className={`px-4 pt-4 mt-2 border-t border-white/[0.04] transition-all overflow-hidden whitespace-nowrap flex ${isExpanded ? 'items-center gap-3 justify-start' : 'justify-center'}`}>
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#121212] flex items-center justify-center shadow-lg border border-white/5 relative shrink-0">
                     {/* The master icon */}
                    <span className="text-xl">👽</span>
                    <div className="absolute right-0 bottom-0 w-2.5 h-2.5 rounded-full bg-[var(--accent-green)] border-2 border-[#0a0a0f]" />
                </div>
                {isExpanded && (
                    <div className="min-w-0 animate-fade-in">
                        <div className="text-[11px] font-black text-white truncate drop-shadow-sm uppercase tracking-wider">Mestre Valério</div>
                        <div className="text-[8px] text-[var(--accent-purple)] font-black uppercase tracking-[0.2em] mt-0.5">Licença Diamante</div>
                    </div>
                )}
            </div>
        </aside>
    );
};

export default Sidebar;
