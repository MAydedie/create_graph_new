import axios from 'axios';

const API_BASE = 'http://localhost:8000/api';
const WS_BASE = 'ws://localhost:8000/ws';

export interface TaskRequest {
    user_goal: string;
    workspace_root: string;
}

export interface FileItem {
    name: string;
    type: 'directory' | 'file';
    path: string;
    size: number;
}

export const api = {
    startChat: async (user_goal: string, workspace_root: string) => {
        const res = await axios.post(`${API_BASE}/chat`, { user_goal, workspace_root });
        return res.data;
    },

    listFiles: async (path: string) => {
        const res = await axios.post(`${API_BASE}/fs/list`, { path });
        return res.data.items as FileItem[];
    },

    readFile: async (path: string) => {
        const res = await axios.post(`${API_BASE}/fs/read`, { path });
        return res.data;
    },

    getWebSocketUrl: (taskId: string) => {
        return `${WS_BASE}/${taskId}`;
    },

    openPath: async (path: string) => {
        await axios.post(`${API_BASE}/fs/open`, { path });
    }
};
