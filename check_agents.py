#!/usr/bin/env python3

import asyncio
import sys
import os
sys.path.append('/app')

from services.supabase import DBConnection

async def check_agents():
    """Check what agents exist for the test user"""
    
    db = DBConnection()
    client = await db.client
    
    user_id = "23da2930-ab0e-402a-90e3-e75848b129a5"
    
    # Check existing agents
    result = await client.table('agents').select('*').eq('account_id', user_id).execute()
    print(f'Found {len(result.data)} agents for user:')
    for agent in result.data:
        print(f'  - {agent["name"]} (ID: {agent["agent_id"]}, Default: {agent["is_default"]})')
        print(f'    Tools: {agent["agentpress_tools"]}')

if __name__ == "__main__":
    asyncio.run(check_agents())
