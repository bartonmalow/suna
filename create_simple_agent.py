#!/usr/bin/env python3

import asyncio
import json
import os
from services.supabase import DBConnection

async def create_simple_agent():
    """Create a minimal agent with web search tools directly in the database"""
    
    db = DBConnection()
    client = await db.client
    
    user_id = "23da2930-ab0e-402a-90e3-e75848b129a5"
    
    # First check if user already has agents
    existing = await client.table('agents').select('*').eq('account_id', user_id).execute()
    if existing.data:
        print(f"✅ User already has {len(existing.data)} agents")
        for agent in existing.data:
            print(f"  - {agent['name']} (ID: {agent['agent_id']}, Default: {agent['is_default']})")
        return
    
    # Create a minimal agent with proper config structure for the new database schema
    config = {
        "system_prompt": "You are a research assistant with access to web search tools. Use the web_search tool to find current information when users ask research questions. Always perform multiple searches to gather comprehensive data.",
        "tools": {
            "agentpress": {
                "web_search_tool": True,
                "sb_browser_tool": True,
                "sb_shell_tool": True,
                "sb_files_tool": True
            },
            "mcp": [],
            "custom_mcp": []
        },
        "metadata": {
            "avatar": "🔍",
            "avatar_color": "#4F46E5"
        }
    }
    
    agent_data = {
        "account_id": user_id,
        "name": "Web Research Agent",
        "description": "AI agent with web search capabilities for comprehensive research",
        "is_default": True,
        "is_public": False,
        "avatar": "🔍",
        "avatar_color": "#4F46E5",
        "version_count": 1,
        "config": config
    }
    
    print("Creating agent with data:")
    print(json.dumps(agent_data, indent=2))
    
    try:
        result = await client.table('agents').insert(agent_data).execute()
        if result.data:
            agent = result.data[0]
            print(f"✅ Agent created successfully!")
            print(f"   ID: {agent['agent_id']}")
            print(f"   Name: {agent['name']}")
            print(f"   Default: {agent['is_default']}")
            print(f"   Tools: {agent['agentpress_tools']}")
            return agent['agent_id']
        else:
            print("❌ Failed to create agent - no data returned")
            return None
            
    except Exception as e:
        print(f"❌ Error creating agent: {e}")
        return None

if __name__ == "__main__":
    asyncio.run(create_simple_agent())
