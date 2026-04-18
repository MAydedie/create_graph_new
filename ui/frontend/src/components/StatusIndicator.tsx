import React from 'react';
import { Loader2 } from 'lucide-react';

export type AgentStatus = 'idle' | 'thinking' | 'planning' | 'executing' | 'reviewing' | 'completed';

interface StatusIndicatorProps {
    status: AgentStatus;
    text?: string;
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({ status, text }) => {
    if (status === 'idle' || status === 'completed') return null;

    const getStatusText = () => {
        if (text) return text;
        switch (status) {
            case 'thinking': return 'Thinking...';
            case 'planning': return 'Planning...';
            case 'executing': return 'Working...';
            case 'reviewing': return 'Reviewing...';
            default: return 'Working...';
        }
    };

    return (
        <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '8px 12px',
            background: '#fff',
            borderRadius: 20,
            border: '1px solid #e5e6eb',
            boxShadow: '0 2px 8px rgba(0,0,0,0.05)',
            fontSize: 13,
            fontWeight: 500,
            color: '#3370ff',
            position: 'absolute',
            top: 16,
            left: 60, // Next to sidebar toggle
            zIndex: 10,
            transition: 'all 0.3s ease'
        }}>
            <Loader2 size={16} className="animate-spin" />
            <span>{getStatusText()}</span>
            <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .animate-spin {
          animation: spin 1s linear infinite;
        }
      `}</style>
        </div>
    );
};
