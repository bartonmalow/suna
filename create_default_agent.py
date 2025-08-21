#!/usr/bin/env python3

import asyncio
import sys
import os
sys.path.append('/app')

from utils.suna_default_agent_service import SunaDefaultAgentService

async def create_default_agent():
    """Create a Suna default agent for the test user"""
    
    user_id = "23da2930-ab0e-402a-90e3-e75848b129a5"
    
    try:
        service = SunaDefaultAgentService()
        
        print(f"Creating Suna default agent for user: {user_id}")
        agent_id = await service.install_suna_agent_for_user(user_id)
        
        if agent_id:
            print(f"✅ Successfully created Suna default agent: {agent_id}")
        else:
            print("❌ Failed to create Suna default agent")
            
    except Exception as e:
        print(f"💥 Error: {e}")

if __name__ == "__main__":
    asyncio.run(create_default_agent())
