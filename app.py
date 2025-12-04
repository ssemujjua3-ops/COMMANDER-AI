#!/usr/bin/env python3
"""
Commander AI System - Complete with OpenAI, Bots, and Web UI
Deploy to Render: https://render.com
"""

import os
import uuid
import time
import json
import asyncio
from typing import List, Dict, Optional
from datetime import datetime

# FastAPI
from fastapi import FastAPI, HTTPException, Header, Body, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Pydantic models
from pydantic import BaseModel

# ==================== CONFIGURATION ====================
# Environment variables from Render
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
CREATOR_EMAIL = os.environ.get("CREATOR_EMAIL", "ssemujjua3@gmail.com")
CREATOR_PASSWORD = os.environ.get("CREATOR_PASSWORD", "ChangeMe123!")
CREATOR_API_KEY = os.environ.get("CREATOR_API_KEY", "creator-" + str(uuid.uuid4())[:16])
OVERRIDE_TOKEN = os.environ.get("OVERRIDE_TOKEN", "override-" + str(uuid.uuid4())[:16])
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")  # REQUIRED: Get from https://platform.openai.com/api-keys
PORT = int(os.environ.get("PORT", 8000))  # Render provides PORT

# ==================== INITIALIZE APP ====================
app = FastAPI(
    title="Commander AI System",
    description="AI-powered bot creation and management",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS - Allow all origins (for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== IN-MEMORY DATABASE ====================
# In production, use PostgreSQL. For demo, we use memory.
users_db = {
    CREATOR_EMAIL: {
        "email": CREATOR_EMAIL,
        "password": CREATOR_PASSWORD,
        "api_key": CREATOR_API_KEY,
        "is_admin": True,
        "created_at": datetime.now().isoformat()
    }
}

bots_db = {}
codes_db = {}
tasks_db = {}

# ==================== OPENAI SERVICE ====================
class OpenAIService:
    def __init__(self):
        self.api_key = OPENAI_API_KEY
        self.enabled = bool(self.api_key.strip())
        print(f"🔑 OpenAI Service: {'ENABLED' if self.enabled else 'DISABLED - No API key'}")
    
    async def generate_code(self, description: str, bot_name: str = "GeneratedBot") -> str:
        """Generate Python code using OpenAI"""
        if not self.enabled:
            return self._fallback_code(bot_name)
        
        try:
            import openai
            openai.api_key = self.api_key
            
            prompt = f"""Create a Python class named {bot_name} with:
1. An __init__ method taking 'name' and 'skills' parameters
2. An async execute method taking 'task' parameter
3. Return a dictionary with 'ok' and 'result' keys
4. Based on this description: {description}

Requirements:
- Must be valid Python 3.9+ code
- Include error handling
- Use asyncio for async operations
- No external dependencies unless necessary

Return ONLY the Python code, no explanations:"""
            
            response = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a Python expert. Output only valid Python code."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=800,
                timeout=30
            )
            
            code = response.choices[0].message.content.strip()
            
            # Clean up markdown code blocks if present
            if code.startswith("```python"):
                code = code[9:]
            if code.startswith("```"):
                code = code[3:]
            if code.endswith("```"):
                code = code[:-3]
            
            return code
            
        except Exception as e:
            print(f"⚠️ OpenAI error: {e}")
            return self._fallback_code(bot_name)
    
    def _fallback_code(self, bot_name: str) -> str:
        """Fallback code when OpenAI is unavailable"""
        return f'''class {bot_name}:
    """AI-generated bot for various tasks"""
    
    def __init__(self, name: str, skills: list):
        self.name = name
        self.skills = skills
        self.created_at = "{datetime.now().isoformat()}"
    
    async def execute(self, task: str) -> dict:
        """Execute a task asynchronously"""
        import asyncio
        await asyncio.sleep(0.1)  # Simulate work
        
        # Basic task processing
        if "analyze" in task.lower():
            return {{
                "ok": True,
                "result": f"Analysis completed for: {{task}}",
                "bot": self.name,
                "skills_used": [s for s in self.skills if s in ["analysis", "thinking"]]
            }}
        elif "code" in task.lower():
            return {{
                "ok": True,
                "result": f"Code execution simulated for: {{task}}",
                "note": "Use sandbox for actual execution"
            }}
        else:
            return {{
                "ok": True,
                "result": f"Task completed: {{task}}",
                "bot": self.name,
                "executed_at": "{datetime.now().isoformat()}"
            }}
    
    def __str__(self):
        return f"{bot_name}(skills={{self.skills}})"
'''

openai_service = OpenAIService()

# ==================== AUTHENTICATION ====================
class AuthChecker:
    @staticmethod
    def get_api_key(x_api_key: str = Header(None, alias="X-API-Key")) -> dict:
        """Validate API key from header"""
        if not x_api_key:
            raise HTTPException(status_code=401, detail="Missing X-API-Key header")
        
        # Check creator API key
        if x_api_key == CREATOR_API_KEY:
            return {
                "email": CREATOR_EMAIL,
                "is_admin": True,
                "api_key": x_api_key
            }
        
        # Check user API keys
        for email, user in users_db.items():
            if user.get("api_key") == x_api_key:
                return {
                    "email": email,
                    "is_admin": user.get("is_admin", False),
                    "api_key": x_api_key
                }
        
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    @staticmethod
    def check_override_token(override_token: Optional[str] = None, user: dict = None) -> bool:
        """Check if override token is valid (for non-admins)"""
        if not user:
            return False
        
        # Admins don't need override token
        if user.get("is_admin"):
            return True
        
        # Non-admins need valid override token
        if not override_token or override_token != OVERRIDE_TOKEN:
            return False
        
        return True

# ==================== PYDANTIC MODELS ====================
class BotCreate(BaseModel):
    name: str
    skills: List[str] = ["general"]
    description: Optional[str] = None

class CodeGenerate(BaseModel):
    description: str
    bot_name: str = "GeneratedBot"

class TaskAssign(BaseModel):
    bot_id: str
    task: str
    timeout: int = 30

# ==================== HEALTH & INFO ENDPOINTS ====================
@app.get("/")
async def root():
    """Root endpoint with system info"""
    return {
        "service": "Commander AI System",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "docs": "/docs",
            "editor": "/editor",
            "health": "/health",
            "api": {
                "bots": "/api/bots",
                "generate": "/api/code/generate",
                "tasks": "/api/tasks"
            }
        },
        "openai_enabled": openai_service.enabled,
        "creator_email": CREATOR_EMAIL,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health_check():
    """Health check for Render and monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "commander-ai",
        "openai": "enabled" if openai_service.enabled else "disabled",
        "database": "in-memory",
        "bots_count": len(bots_db),
        "codes_count": len(codes_db)
    }

@app.get("/api/info")
async def system_info(auth: dict = Depends(AuthChecker.get_api_key)):
    """Get system information and credentials"""
    return {
        "user": auth["email"],
        "is_admin": auth["is_admin"],
        "openai_enabled": openai_service.enabled,
        "override_token_required": not auth["is_admin"],
        "total_bots": len(bots_db),
        "total_codes": len(codes_db),
        "server_time": datetime.now().isoformat()
    }

# ==================== BOT MANAGEMENT ====================
@app.post("/api/bots", response_model=dict)
async def create_bot(
    bot_data: BotCreate,
    auth: dict = Depends(AuthChecker.get_api_key)
):
    """Create a new bot"""
    bot_id = str(uuid.uuid4())
    
    bot = {
        "id": bot_id,
        "name": bot_data.name,
        "skills": bot_data.skills,
        "description": bot_data.description,
        "owner": auth["email"],
        "created_at": datetime.now().isoformat(),
        "alive": True,
        "tasks_completed": 0
    }
    
    bots_db[bot_id] = bot
    
    return {
        "success": True,
        "bot": bot,
        "message": f"Bot '{bot_data.name}' created successfully"
    }

@app.get("/api/bots", response_model=dict)
async def list_bots(auth: dict = Depends(AuthChecker.get_api_key)):
    """List all bots for the authenticated user"""
    user_bots = [
        bot for bot in bots_db.values()
        if bot["owner"] == auth["email"] or auth["is_admin"]
    ]
    
    return {
        "count": len(user_bots),
        "bots": user_bots
    }

@app.delete("/api/bots/{bot_id}")
async def delete_bot(
    bot_id: str,
    auth: dict = Depends(AuthChecker.get_api_key),
    override_token: Optional[str] = Body(None, embed=True)
):
    """Delete a bot (requires override token for non-admins)"""
    if bot_id not in bots_db:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    bot = bots_db[bot_id]
    
    # Check permission
    if bot["owner"] != auth["email"] and not auth["is_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Check override token for non-admins
    if not auth["is_admin"]:
        if not AuthChecker.check_override_token(override_token, auth):
            raise HTTPException(
                status_code=403,
                detail="Override token required for non-admin users"
            )
    
    del bots_db[bot_id]
    
    return {
        "success": True,
        "message": f"Bot '{bot['name']}' deleted",
        "bot_id": bot_id
    }

# ==================== CODE GENERATION ====================
@app.post("/api/code/generate")
async def generate_code(
    request: CodeGenerate,
    auth: dict = Depends(AuthChecker.get_api_key)
):
    """Generate Python code using OpenAI"""
    print(f"🔧 Generating code for: {request.description[:50]}...")
    
    code = await openai_service.generate_code(
        request.description,
        request.bot_name
    )
    
    code_id = str(uuid.uuid4())
    codes_db[code_id] = {
        "id": code_id,
        "name": request.bot_name,
        "description": request.description,
        "code": code,
        "owner": auth["email"],
        "created_at": datetime.now().isoformat(),
        "approved": False,
        "openai_used": openai_service.enabled
    }
    
    return {
        "success": True,
        "code_id": code_id,
        "name": request.bot_name,
        "code_preview": code[:200] + "..." if len(code) > 200 else code,
        "full_code": code if len(code) < 1000 else code[:1000] + "... [truncated]",
        "openai_used": openai_service.enabled,
        "message": "Code generated successfully"
    }

@app.get("/api/code/{code_id}")
async def get_code(
    code_id: str,
    auth: dict = Depends(AuthChecker.get_api_key)
):
    """Get generated code by ID"""
    if code_id not in codes_db:
        raise HTTPException(status_code=404, detail="Code not found")
    
    code = codes_db[code_id]
    
    # Check ownership
    if code["owner"] != auth["email"] and not auth["is_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return {
        "success": True,
        "code": code
    }

@app.post("/api/code/approve/{code_id}")
async def approve_code(
    code_id: str,
    auth: dict = Depends(AuthChecker.get_api_key),
    override_token: Optional[str] = Body(None, embed=True)
):
    """Approve generated code (requires override for non-admins)"""
    if code_id not in codes_db:
        raise HTTPException(status_code=404, detail="Code not found")
    
    code = codes_db[code_id]
    
    # Check ownership
    if code["owner"] != auth["email"] and not auth["is_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Check override token for non-admins
    if not auth["is_admin"]:
        if not AuthChecker.check_override_token(override_token, auth):
            raise HTTPException(
                status_code=403,
                detail=f"Override token required. Your token: {override_token}"
            )
    
    codes_db[code_id]["approved"] = True
    codes_db[code_id]["approved_at"] = datetime.now().isoformat()
    codes_db[code_id]["approved_by"] = auth["email"]
    
    return {
        "success": True,
        "message": f"Code '{code['name']}' approved",
        "code_id": code_id,
        "approved": True
    }

# ==================== TASK MANAGEMENT ====================
@app.post("/api/tasks/assign")
async def assign_task(
    task_data: TaskAssign,
    auth: dict = Depends(AuthChecker.get_api_key)
):
    """Assign a task to a bot"""
    if task_data.bot_id not in bots_db:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    bot = bots_db[task_data.bot_id]
    
    # Check ownership
    if bot["owner"] != auth["email"] and not auth["is_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    task_id = str(uuid.uuid4())
    
    task = {
        "id": task_id,
        "bot_id": task_data.bot_id,
        "bot_name": bot["name"],
        "task": task_data.task,
        "assigned_by": auth["email"],
        "assigned_at": datetime.now().isoformat(),
        "status": "pending",
        "timeout": task_data.timeout
    }
    
    tasks_db[task_id] = task
    
    # Simulate task execution (in production, this would be async)
    async def execute_task():
        await asyncio.sleep(1)  # Simulate work
        
        # Update task status
        tasks_db[task_id]["status"] = "completed"
        tasks_db[task_id]["completed_at"] = datetime.now().isoformat()
        tasks_db[task_id]["result"] = {
            "success": True,
            "output": f"Task completed by {bot['name']}: {task_data.task[:50]}...",
            "bot_skills": bot["skills"]
        }
        
        # Update bot stats
        bots_db[task_data.bot_id]["tasks_completed"] += 1
    
    # Run task in background
    asyncio.create_task(execute_task())
    
    return {
        "success": True,
        "task_id": task_id,
        "bot": bot["name"],
        "status": "assigned",
        "message": f"Task assigned to {bot['name']}"
    }

@app.get("/api/tasks")
async def list_tasks(auth: dict = Depends(AuthChecker.get_api_key)):
    """List all tasks for the authenticated user"""
    user_tasks = []
    
    for task in tasks_db.values():
        bot = bots_db.get(task["bot_id"])
        if bot and (bot["owner"] == auth["email"] or auth["is_admin"]):
            user_tasks.append(task)
    
    return {
        "count": len(user_tasks),
        "tasks": user_tasks
    }

# ==================== WEB EDITOR UI ====================
@app.get("/editor")
async def web_editor():
    """Web-based editor for Commander AI"""
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Commander AI Editor</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            line-height: 1.6;
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            color: white;
            padding: 2rem;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }}
        
        .header .subtitle {{
            opacity: 0.9;
            font-size: 1.1rem;
        }}
        
        .content {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 2rem;
            padding: 2rem;
        }}
        
        @media (max-width: 768px) {{
            .content {{
                grid-template-columns: 1fr;
            }}
        }}
        
        .panel {{
            background: #f8fafc;
            border-radius: 12px;
            padding: 1.5rem;
            border: 1px solid #e2e8f0;
        }}
        
        .panel h2 {{
            color: #4f46e5;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid #e2e8f0;
        }}
        
        .credentials {{
            background: #f0f9ff;
            border: 2px solid #0ea5e9;
        }}
        
        .credential-item {{
            background: white;
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
            border: 1px solid #e2e8f0;
        }}
        
        .credential-item label {{
            display: block;
            font-weight: 600;
            color: #64748b;
            margin-bottom: 0.25rem;
            font-size: 0.9rem;
        }}
        
        .credential-item code {{
            background: #1e293b;
            color: #f1f5f9;
            padding: 0.75rem;
            border-radius: 6px;
            display: block;
            font-family: 'Courier New', monospace;
            word-break: break-all;
            font-size: 0.9rem;
        }}
        
        textarea, input[type="text"] {{
            width: 100%;
            padding: 1rem;
            border: 2px solid #e2e8f0;
            border-radius: 8px;
            font-family: inherit;
            font-size: 1rem;
            margin-bottom: 1rem;
            transition: border-color 0.2s;
        }}
        
        textarea:focus, input[type="text"]:focus {{
            outline: none;
            border-color: #4f46e5;
        }}
        
        textarea {{
            min-height: 150px;
            resize: vertical;
        }}
        
        .button {{
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            color: white;
            border: none;
            padding: 1rem 2rem;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            margin-right: 0.5rem;
            margin-bottom: 0.5rem;
        }}
        
        .button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(79, 70, 229, 0.4);
        }}
        
        .button:active {{
            transform: translateY(0);
        }}
        
        .button.secondary {{
            background: #64748b;
        }}
        
        .button.success {{
            background: #10b981;
        }}
        
        .button.warning {{
            background: #f59e0b;
        }}
        
        .output {{
            background: #1e293b;
            color: #f1f5f9;
            padding: 1.5rem;
            border-radius: 8px;
            margin-top: 1rem;
            font-family: 'Courier New', monospace;
            white-space: pre-wrap;
            max-height: 400px;
            overflow-y: auto;
            font-size: 0.9rem;
        }}
        
        .status {{
            padding: 1rem;
            border-radius: 8px;
            margin: 1rem 0;
            font-weight: 600;
        }}
        
        .status.success {{
            background: #d1fae5;
            color: #065f46;
            border: 1px solid #a7f3d0;
        }}
        
        .status.error {{
            background: #fee2e2;
            color: #991b1b;
            border: 1px solid #fecaca;
        }}
        
        .status.info {{
            background: #dbeafe;
            color: #1e40af;
            border: 1px solid #bfdbfe;
        }}
        
        .loading {{
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
        }}
        
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
        
        .footer {{
            text-align: center;
            padding: 2rem;
            color: #64748b;
            border-top: 1px solid #e2e8f0;
            font-size: 0.9rem;
        }}
        
        .openai-status {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9rem;
        }}
        
        .openai-status.enabled {{
            background: #d1fae5;
            color: #065f46;
        }}
        
        .openai-status.disabled {{
            background: #fee2e2;
            color: #991b1b;
        }}
        
        .indicator {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
        }}
        
        .indicator.on {{
            background: #10b981;
        }}
        
        .indicator.off {{
            background: #ef4444;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Commander AI System</h1>
            <p class="subtitle">Generate AI-powered bots with OpenAI • Manage tasks • Deploy to cloud</p>
            <div style="margin-top: 1rem;">
                <span class="openai-status {'enabled' if openai_service.enabled else 'disabled'}">
                    <span class="indicator {'on' if openai_service.enabled else 'off'}"></span>
                    OpenAI: {'ENABLED' if openai_service.enabled else 'DISABLED - Add API Key'}
                </span>
            </div>
        </div>
        
        <div class="content">
            <div class="panel credentials">
                <h2>🔑 Your Credentials</h2>
                <p style="margin-bottom: 1rem; color: #64748b;">Use these in API requests:</p>
                
                <div class="credential-item">
                    <label>API Key (X-API-Key header)</label>
                    <code id="apiKey">{CREATOR_API_KEY}</code>
                    <button onclick="copyToClipboard('apiKey')" class="button" style="margin-top: 0.5rem; padding: 0.5rem 1rem; font-size: 0.9rem;">
                        📋 Copy
                    </button>
                </div>
                
                <div class="credential-item">
                    <label>Override Token (for non-admin operations)</label>
                    <code id="overrideToken">{OVERRIDE_TOKEN}</code>
                    <button onclick="copyToClipboard('overrideToken')" class="button" style="margin-top: 0.5rem; padding: 0.5rem 1rem; font-size: 0.9rem;">
                        📋 Copy
                    </button>
                </div>
                
                <div class="credential-item">
                    <label>Creator Email</label>
                    <code>{CREATOR_EMAIL}</code>
                </div>
                
                <div id="apiStatus" class="status info">
                    💡 Use the API key in the X-API-Key header for all requests
                </div>
            </div>
            
            <div class="panel">
                <h2>✨ Generate Bot Code</h2>
                <input type="text" id="botName" placeholder="Bot Name (e.g., AnalyzerBot)" value="SmartBot">
                <textarea id="botDescription" placeholder="Describe what you want the bot to do...">Create a Python bot that can analyze text, summarize documents, and answer questions. The bot should be async and handle errors gracefully.</textarea>
                
                <button onclick="generateCode()" class="button">
                    <span id="generateIcon">✨</span>
                    <span id="generateText">Generate Code with AI</span>
                </button>
                
                <div id="generateStatus"></div>
                <div id="codeOutput" class="output" style="display: none;"></div>
            </div>
            
            <div class="panel">
                <h2>✅ Approve & Use Code</h2>
                <div id="approveControls" style="display: none;">
                    <p>Current Code ID: <code id="currentCodeId"></code></p>
                    <button onclick="approveCode()" class="button success">✅ Approve This Code</button>
                    <button onclick="createBotFromCode()" class="button">🤖 Create Bot from Code</button>
                </div>
                <div id="approveStatus"></div>
            </div>
            
            <div class="panel">
                <h2>🚀 Quick Actions</h2>
                <button onclick="createSimpleBot()" class="button">🤖 Create Simple Bot</button>
                <button onclick="listBots()" class="button secondary">📋 List My Bots</button>
                <button onclick="assignTask()" class="button warning">📝 Assign Test Task</button>
                <button onclick="checkHealth()" class="button">❤️ Check System Health</button>
                
                <div id="quickActionsStatus"></div>
                <div id="botsList" class="output" style="display: none; margin-top: 1rem;"></div>
            </div>
        </div>
        
        <div class="footer">
            <p>Commander AI System v1.0 • Deployed on Render • OpenAI Integrated</p>
            <p style="margin-top: 0.5rem; font-size: 0.8rem;">
                <a href="/docs" style="color: #4f46e5; text-decoration: none;">API Documentation</a> • 
                <a href="/health" style="color: #4f46e5; text-decoration: none;">Health Check</a> • 
                <a href="https://render.com" style="color: #4f46e5; text-decoration: none;">Render Hosting</a>
            </p>
        </div>
    </div>
    
    <script>
        const API_KEY = "{CREATOR_API_KEY}";
        const OVERRIDE_TOKEN = "{OVERRIDE_TOKEN}";
        let currentCodeId = null;
        
        function copyToClipboard(elementId) {{
            const element = document.getElementById(elementId);
            const text = element.innerText;
            
            navigator.clipboard.writeText(text).then(() => {{
                showStatus('apiStatus', '✅ Copied to clipboard!', 'success');
            }}).catch(err => {{
                showStatus('apiStatus', '❌ Failed to copy', 'error');
            }});
        }}
        
        function showStatus(elementId, message, type = 'info') {{
            const element = document.getElementById(elementId);
            element.innerHTML = message;
            element.className = `status ${{type}}`;
            element.style.display = 'block';
            
            if (type !== 'error') {{
                setTimeout(() => {{
                    element.style.display = 'none';
                }}, 5000);
            }}
        }}
        
        function setLoading(buttonId, isLoading) {{
            const button = document.querySelector(`#${{buttonId}}`);
            if (!button) return;
            
            if (isLoading) {{
                button.innerHTML = '<span class="loading"></span> Processing...';
                button.disabled = true;
            }} else {{
                button.innerHTML = '✨ Generate Code with AI';
                button.disabled = false;
            }}
        }}
        
        async function generateCode() {{
            const botName = document.getElementById('botName').value;
            const description = document.getElementById('botDescription').value;
            
            if (!description.trim()) {{
                showStatus('generateStatus', '❌ Please enter a description', 'error');
                return;
            }}
            
            setLoading('generateText', true);
            showStatus('generateStatus', '⏳ Generating code with AI...', 'info');
            
            try {{
                const response = await fetch('/api/code/generate', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'X-API-Key': API_KEY
                    }},
                    body: JSON.stringify({{
                        bot_name: botName,
                        description: description
                    }})
                }});
                
                const data = await response.json();
                
                if (data.success) {{
                    currentCodeId = data.code_id;
                    
                    // Show code
                    const codeOutput = document.getElementById('codeOutput');
                    codeOutput.innerHTML = `<h4>Generated Code (ID: ${{data.code_id}})</h4><pre>${{data.full_code}}</pre>`;
                    codeOutput.style.display = 'block';
                    
                    // Show approve controls
                    document.getElementById('approveControls').style.display = 'block';
                    document.getElementById('currentCodeId').innerText = data.code_id;
                    
                    showStatus('generateStatus', `✅ Code generated successfully! ${{data.openai_used ? '(OpenAI)' : '(Fallback)'}}`, 'success');
                }} else {{
                    showStatus('generateStatus', `❌ Error: ${{data.detail || 'Unknown error'}}`, 'error');
                }}
            }} catch (error) {{
                showStatus('generateStatus', `❌ Network error: ${{error.message}}`, 'error');
            }} finally {{
                setLoading('generateText', false);
            }}
        }}
        
        async function approveCode() {{
            if (!currentCodeId) {{
                showStatus('approveStatus', '❌ No code generated yet', 'error');
                return;
            }}
            
            showStatus('approveStatus', '⏳ Approving code...', 'info');
            
            try {{
                const response = await fetch(`/api/code/approve/${{currentCodeId}}`, {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'X-API-Key': API_KEY
                    }},
                    body: JSON.stringify({{
                        override_token: OVERRIDE_TOKEN
                    }})
                }});
                
                const data = await response.json();
                
                if (data.success) {{
                    showStatus('approveStatus', '✅ Code approved successfully!', 'success');
                }} else {{
                    showStatus('approveStatus', `❌ Error: ${{data.detail || 'Approval failed'}}`, 'error');
                }}
            }} catch (error) {{
                showStatus('approveStatus', `❌ Network error: ${{error.message}}`, 'error');
            }}
        }}
        
        async function createSimpleBot() {{
            showStatus('quickActionsStatus', '⏳ Creating bot...', 'info');
            
            try {{
                const response = await fetch('/api/bots', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'X-API-Key': API_KEY
                    }},
                    body: JSON.stringify({{
                        name: 'QuickBot-' + Date.now().toString().slice(-4),
                        skills: ['general', 'quick'],
                        description: 'A quick test bot'
                    }})
                }});
                
                const data = await response.json();
                
                if (data.success) {{
                    showStatus('quickActionsStatus', `✅ Bot created: ${{data.bot.name}}`, 'success');
                }} else {{
                    showStatus('quickActionsStatus', `❌ Error: ${{data.detail}}`, 'error');
                }}
            }} catch (error) {{
                showStatus('quickActionsStatus', `❌ Network error: ${{error.message}}`, 'error');
            }}
        }}
        
        async function listBots() {{
            showStatus('quickActionsStatus', '⏳ Loading bots...', 'info');
            
            try {{
                const response = await fetch('/api/bots', {{
                    headers: {{
                        'X-API-Key': API_KEY
                    }}
                }});
                
                const data = await response.json();
                
                if (data.success || data.bots) {{
                    const botsList = document.getElementById('botsList');
                    const bots = data.bots || data;
                    
                    if (bots.length === 0) {{
                        botsList.innerHTML = 'No bots yet. Create one first!';
                    }} else {{
                        botsList.innerHTML = '<h4>Your Bots:</h4>' + 
                            bots.map(bot => `
                                <div style="margin: 10px 0; padding: 10px; background: #2d3748; border-radius: 6px;">
                                    <strong>${{bot.name}}</strong> (ID: ${{bot.id}})<br>
                                    Skills: ${{bot.skills?.join(', ') || 'none'}}<br>
                                    Created: ${{new Date(bot.created_at).toLocaleDateString()}}
                                </div>
                            `).join('');
                    }}
                    
                    botsList.style.display = 'block';
                    showStatus('quickActionsStatus', `✅ Loaded ${{bots.length}} bots`, 'success');
                }} else {{
                    showStatus('quickActionsStatus', '❌ No bots found', 'error');
                }}
            }} catch (error) {{
                showStatus('quickActionsStatus', `❌ Network error: ${{error.message}}`, 'error');
            }}
        }}
        
        async function checkHealth() {{
            try {{
                const response = await fetch('/health');
                const data = await response.json();
                
                showStatus('quickActionsStatus', `✅ System healthy • Bots: ${{data.bots_count}} • OpenAI: ${{data.openai}}`, 'success');
            }} catch (error) {{
                showStatus('quickActionsStatus', `❌ Health check failed: ${{error.message}}`, 'error');
            }}
        }}
        
        async function createBotFromCode() {{
            if (!currentCodeId) {{
                showStatus('approveStatus', '❌ Generate code first', 'error');
                return;
            }}
            
            const botName = prompt('Enter bot name:', 'AIBot');
            if (!botName) return;
            
            showStatus('approveStatus', '⏳ Creating bot from code...', 'info');
            
            // First create a bot
            try {{
                const response = await fetch('/api/bots', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'X-API-Key': API_KEY
                    }},
                    body: JSON.stringify({{
                        name: botName,
                        skills: ['ai', 'generated'],
                        description: 'Created from AI-generated code'
                    }})
                }});
                
                const data = await response.json();
                
                if (data.success) {{
                    showStatus('approveStatus', `✅ Bot "${{botName}}" created from AI code!`, 'success');
                }} else {{
                    showStatus('approveStatus', `❌ Error creating bot: ${{data.detail}}`, 'error');
                }}
            }} catch (error) {{
                showStatus('approveStatus', `❌ Network error: ${{error.message}}`, 'error');
            }}
        }}
        
        async function assignTask() {{
            // First get bots
            try {{
                const response = await fetch('/api/bots', {{
                    headers: {{
                        'X-API-Key': API_KEY
                    }}
                }});
                
                const data = await response.json();
                const bots = data.bots || data;
                
                if (bots.length === 0) {{
                    showStatus('quickActionsStatus', '❌ No bots available. Create one first.', 'error');
                    return;
                }}
                
                const bot = bots[0]; // Use first bot
                
                const taskResponse = await fetch('/api/tasks/assign', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'X-API-Key': API_KEY
                    }},
                    body: JSON.stringify({{
                        bot_id: bot.id,
                        task: 'Test task from web editor',
                        timeout: 10
                    }})
                }});
                
                const taskData = await taskResponse.json();
                
                if (taskData.success) {{
                    showStatus('quickActionsStatus', `✅ Task assigned to ${{bot.name}}!`, 'success');
                }} else {{
                    showStatus('quickActionsStatus', `❌ Error: ${{taskData.detail}}`, 'error');
                }}
            }} catch (error) {{
                showStatus('quickActionsStatus', `❌ Network error: ${{error.message}}`, 'error');
            }}
        }}
        
        // Initial health check
        window.addEventListener('load', () => {{
            checkHealth();
        }});
    </script>
</body>
</html>
    """
    return HTMLResponse(html_content)

# ==================== KEEP-ALIVE FOR RENDER ====================
import threading
import requests

def keep_alive_ping():
    """Ping the app every 10 minutes to prevent Render sleep"""
    while True:
        try:
            # Get the Render URL from environment or use default
            app_url = os.environ.get("RENDER_EXTERNAL_URL", "")
            if not app_url:
                # Try to construct from service name
                service_name = os.environ.get("RENDER_SERVICE_NAME", "")
                if service_name:
                    app_url = f"https://{service_name}.onrender.com"
            
            if app_url:
                requests.get(f"{app_url}/health", timeout=10)
                print(f"✅ Keep-alive ping sent to {app_url}")
            else:
                # Local ping
                requests.get(f"http://localhost:{PORT}/health", timeout=5)
                
        except Exception as e:
            print(f"⚠️ Keep-alive ping failed: {e}")
        
        # Sleep for 10 minutes (600 seconds)
        # Render free tier sleeps after 15 minutes, so 10 is safe
        time.sleep(600)

# Start keep-alive thread
keep_alive_thread = threading.Thread(target=keep_alive_ping, daemon=True)
keep_alive_thread.start()
print("✅ Keep-alive thread started (pings every 10 minutes)")

# ==================== START SERVER ====================
if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("🚀 COMMANDER AI SYSTEM STARTING")
    print("=" * 60)
    print(f"📡 Port: {PORT}")
    print(f"👑 Creator: {CREATOR_EMAIL}")
    print(f"🔑 API Key: {CREATOR_API_KEY}")
    print(f"🔐 Override Token: {OVERRIDE_TOKEN}")
    print(f"🤖 OpenAI: {'ENABLED' if openai_service.enabled else 'DISABLED (set OPENAI_API_KEY)'}")
    print(f"🌐 Web Editor: http://localhost:{PORT}/editor")
    print(f"📚 API Docs: http://localhost:{PORT}/docs")
    print(f"❤️  Health: http://localhost:{PORT}/health")
    print("=" * 60)
    
    # Start server
    uvicorn.run(
        app,
        host="0.0.0.0",  # IMPORTANT: Must be 0.0.0.0 for Render
        port=PORT,
        log_level="info"
    )
