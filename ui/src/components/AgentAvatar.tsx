import React from 'react';

interface AgentAvatarProps {
    agentId: string;
    size?: number;
    className?: string;
    skinVariant?: string;
}

// ─────────────────────────────────────────────
//  CATÁLOGO DE SKINS — 5 Degradê + 5 Sólidas
// ─────────────────────────────────────────────
export const SKIN_CATALOG = [
    // ── GRUPO 1: Degradê ──────────────────────
    { key: 'nebula', label: 'Nebula', color: '#8B00FF', gradient: ['#8B00FF', '#00FFFF'], type: 'gradient' as const },
    { key: 'flare', label: 'Flare', color: '#FF0000', gradient: ['#FF0000', '#FFD700'], type: 'gradient' as const },
    { key: 'acid', label: 'Acid', color: '#39FF14', gradient: ['#39FF14', '#FFFF00'], type: 'gradient' as const },
    { key: 'supernova', label: 'Supernova', color: '#FF00FF', gradient: ['#FF00FF', '#FFD700', '#00FFFF'], type: 'gradient' as const },
    { key: 'cyber', label: 'Cyber', color: '#0077ff', gradient: ['#003399', '#00cfff'], type: 'gradient' as const },
    // ── GRUPO 2: Cor Sólida ───────────────────
    { key: 'void', label: 'Void', color: '#00ffff', type: 'solid' as const },
    { key: 'crimson', label: 'Crimson', color: '#DC143C', type: 'solid' as const },
    { key: 'lava', label: 'Lava', color: '#FF4500', type: 'solid' as const },
    { key: 'ghost', label: 'Ghost', color: '#c0c0c0', type: 'solid' as const },
    { key: 'gold', label: 'Gold', color: '#FFD700', type: 'solid' as const },
];

const SOLID_SKIN_COLORS: Record<string, string> = {
    void: '#111111',
    crimson: '#DC143C',
    lava: '#FF4500',
    ghost: '#C0C0C0',
    gold: '#FFD700',
};

const getAlienStyle = (id: string, variant?: string) => {
    if (variant && variant !== 'default') {
        switch (variant) {
            // ── Degradê ──
            case 'nebula': return { skin: 'url(#gradNebula)', eyes: '#ffffff', antenna: 'dual', shirt: '#1a0033', antennaColor: '#ff00ff' };
            case 'flare': return { skin: 'url(#gradFlare)', eyes: '#000000', antenna: 'star', shirt: '#331100', antennaColor: '#ffff00' };
            case 'acid': return { skin: 'url(#gradAcid)', eyes: '#000000', antenna: 'curly', shirt: '#113300', antennaColor: '#39ff14' };
            case 'supernova': return { skin: 'url(#gradSupernova)', eyes: '#ffffff', antenna: 'round', shirt: '#1a1a1a', antennaColor: '#ffffff' };
            case 'cyber': return { skin: 'url(#gradCyber)', eyes: '#00ffff', antenna: 'side', shirt: '#001a33', antennaColor: '#00bfff' };
            // ── Sólida ──
            case 'void': return { skin: '#111111', eyes: '#00ffff', antenna: 'single', shirt: '#000000', antennaColor: '#00ffff' };
            case 'crimson': return { skin: '#DC143C', eyes: '#000000', antenna: 'dual', shirt: '#3d0010', antennaColor: '#ff6688' };
            case 'lava': return { skin: '#FF4500', eyes: '#ffff00', antenna: 'side', shirt: '#1a0000', antennaColor: '#ff8c00' };
            case 'ghost': return { skin: '#C0C0C0', eyes: '#1a1a1a', antenna: 'round', shirt: '#808080', antennaColor: '#e8e8e8' };
            case 'gold': return { skin: '#FFD700', eyes: '#1a1a1a', antenna: 'star', shirt: '#4f4200', antennaColor: '#fff176' };
        }
    }
    // Cores padrão por ID de agente
    switch (id) {
        case '1': return { skin: '#39FF14', eyes: '#000000', antenna: 'dual', shirt: '#121212', antennaColor: '#30ff00' };
        case '2': return { skin: '#8B00FF', eyes: '#1a1a1a', antenna: 'single', shirt: '#2b004f', antennaColor: '#c050ff' };
        case '3': return { skin: '#00FFFF', eyes: '#000000', antenna: 'curly', shirt: '#004f4f', antennaColor: '#00aaff' };
        case '4': return { skin: '#FF00FF', eyes: '#1a1a1a', antenna: 'round', shirt: '#4f004f', antennaColor: '#ff77ff' };
        case '5': return { skin: '#FF8C00', eyes: '#000000', antenna: 'side', shirt: '#4f2b00', antennaColor: '#ffaa00' };
        case '6': return { skin: '#FFD700', eyes: '#1a1a1a', antenna: 'star', shirt: '#4f4200', antennaColor: '#ffff00' };
        default: return { skin: '#00ff00', eyes: '#000000', antenna: 'default', shirt: '#121212', antennaColor: '#00ff00' };
    }
};

const AgentAvatar: React.FC<AgentAvatarProps> = ({ agentId, size = 100, className = "", skinVariant }) => {
    const style = getAlienStyle(agentId, skinVariant);
    const isVoidLike = ['void', 'phantom'].includes(skinVariant || '');

    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 100 100"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className={`${className} drop-shadow-[0_0_12px_rgba(50,205,50,0.35)]`}
        >
            <defs>
                <radialGradient id="alienEyes" cx="50%" cy="50%" r="50%">
                    <stop offset="70%" style={{ stopColor: style.eyes, stopOpacity: 1 }} />
                    <stop offset="100%" style={{ stopColor: '#32CD32', stopOpacity: 0.3 }} />
                </radialGradient>

                {/* ── 5 Degradê ── */}
                <linearGradient id="gradNebula" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" style={{ stopColor: '#8B00FF' }} />
                    <stop offset="100%" style={{ stopColor: '#00FFFF' }} />
                </linearGradient>

                <linearGradient id="gradFlare" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" style={{ stopColor: '#FF0000' }} />
                    <stop offset="100%" style={{ stopColor: '#FFD700' }} />
                </linearGradient>

                <linearGradient id="gradAcid" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" style={{ stopColor: '#39FF14' }} />
                    <stop offset="100%" style={{ stopColor: '#FFFF00' }} />
                </linearGradient>

                <linearGradient id="gradSupernova" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" style={{ stopColor: '#FF00FF' }} />
                    <stop offset="50%" style={{ stopColor: '#FFD700' }} />
                    <stop offset="100%" style={{ stopColor: '#00FFFF' }} />
                </linearGradient>

                <linearGradient id="gradCyber" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" style={{ stopColor: '#003399' }} />
                    <stop offset="100%" style={{ stopColor: '#00cfff' }} />
                </linearGradient>
            </defs>

            {/* ── ANTENAS ── */}
            {style.antenna === 'dual' && (<>
                <line x1="30" y1="15" x2="20" y2="2" stroke={style.antennaColor} strokeWidth="3" strokeLinecap="round" />
                <circle cx="20" cy="2" r="3" fill={style.antennaColor} />
                <line x1="70" y1="15" x2="80" y2="2" stroke={style.antennaColor} strokeWidth="3" strokeLinecap="round" />
                <circle cx="80" cy="2" r="3" fill={style.antennaColor} />
            </>)}
            {style.antenna === 'single' && (<>
                <line x1="50" y1="15" x2="50" y2="2" stroke={style.antennaColor} strokeWidth="4" strokeLinecap="round" />
                <circle cx="50" cy="2" r="4" fill={style.antennaColor} />
            </>)}
            {style.antenna === 'curly' && (
                <path d="M50 15C50 5 70 5 70 10" stroke={style.antennaColor} strokeWidth="3" fill="none" strokeLinecap="round" />
            )}
            {style.antenna === 'round' && (
                <circle cx="50" cy="15" r="12" stroke={style.antennaColor} strokeWidth="2" fill={style.antennaColor} fillOpacity="0.2" />
            )}
            {style.antenna === 'side' && (<>
                <line x1="15" y1="35" x2="2" y2="35" stroke={style.antennaColor} strokeWidth="3" strokeLinecap="round" />
                <circle cx="2" cy="35" r="3" fill={style.antennaColor} />
                <line x1="85" y1="35" x2="98" y2="35" stroke={style.antennaColor} strokeWidth="3" strokeLinecap="round" />
                <circle cx="98" cy="35" r="3" fill={style.antennaColor} />
            </>)}
            {style.antenna === 'star' && (
                <path d="M50 2L53 10L60 12L53 14L50 22L47 14L40 12L47 10Z" fill={style.antennaColor} />
            )}
            {style.antenna === 'default' && (
                <circle cx="50" cy="10" r="5" fill={style.antennaColor} />
            )}

            {/* ── PESCOÇO ── */}
            <rect x="42" y="58" width="16" height="12" fill={style.skin} fillOpacity="0.7" />

            {/* ── ROUPA ── */}
            <rect x="25" y="65" width="50" height="32" rx="12" fill={style.shirt} />
            <path d="M35 75h30M35 85h30" stroke="rgba(255,255,255,0.2)" strokeWidth="2" />

            {/* ── CABEÇA ── */}
            <ellipse cx="50" cy="35" rx="38" ry="30" fill={style.skin}
                style={{ stroke: isVoidLike ? style.antennaColor : 'none', strokeWidth: 1 }} />

            {/* ── OLHOS ── */}
            <ellipse cx="32" cy="36" rx="14" ry="18" transform="rotate(-20, 32, 36)"
                fill={isVoidLike ? 'none' : 'url(#alienEyes)'}
                stroke={isVoidLike ? style.antennaColor : 'none'} strokeWidth={1} />
            <ellipse cx="68" cy="36" rx="14" ry="18" transform="rotate(20, 68, 36)"
                fill={isVoidLike ? 'none' : 'url(#alienEyes)'}
                stroke={isVoidLike ? style.antennaColor : 'none'} strokeWidth={1} />

            {/* ── BRILHO NOS OLHOS ── */}
            <circle cx="35" cy="30" r="2.5" fill="white" fillOpacity="0.5" />
            <circle cx="65" cy="30" r="2.5" fill="white" fillOpacity="0.5" />

            {/* ── BOCA ── */}
            <path d="M45 52Q50 54 55 52"
                stroke={isVoidLike ? style.antennaColor : "rgba(0,0,0,0.3)"}
                strokeWidth="1.5" strokeLinecap="round" />
        </svg>
    );
};

export default AgentAvatar;
