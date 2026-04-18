#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
创建 .env 文件的辅助脚本
注意：此脚本包含敏感的 API Key，运行后会自动创建 .env 文件
"""

import os
from pathlib import Path

def create_env_file():
    """创建 .env 文件"""
    env_content = """# MiniMax（OpenAI兼容）配置
# 注意：此文件包含敏感信息，不会被提交到 Git 仓库

MINIMAX_API_KEY=sk-cp-8YCmWajR3l1oY8Eu049xZvdnaV5gBOFGUaqu2uSq3oEuv0uSMJH7MJUGfrL9a6t8w8LyB3Aelm9owW7hpjGJ13J-cC0w-bI1SADhG54CYUEawuH3T_LBDMM
MINIMAX_BASE_URL=https://api.minimax.io/v1
MINIMAX_MODEL=MiniMax-M2.7-highspeed

# 兼容旧代码（可选）
DEEPSEEK_API_KEY=${MINIMAX_API_KEY}
DEEPSEEK_BASE_URL=${MINIMAX_BASE_URL}
DEEPSEEK_MODEL=${MINIMAX_MODEL}

OPENAI_API_KEY=${MINIMAX_API_KEY}
OPENAI_BASE_URL=${MINIMAX_BASE_URL}
OPENAI_MODEL=${MINIMAX_MODEL}
"""
    
    env_path = Path(__file__).parent / '.env'
    
    if env_path.exists():
        print(f"⚠️  .env 文件已存在，将被覆盖")
    
    try:
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(env_content)
        print(f"[SUCCESS] .env file created: {env_path}")
        print(f"   API Key configured: sk-cp-8YCmWajR3l1oY8Eu049xZvdnaV5gBOFGUaqu2uSq3oEuv0uSMJH7MJUGfrL9a6t8w8LyB3Aelm9owW7hpjGJ13J-cC0w-bI1SADhG54CYUEawuH3T_LBDMM")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to create .env file: {e}")
        return False

if __name__ == '__main__':
    create_env_file()
