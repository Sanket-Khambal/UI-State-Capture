"""
UI State Capture System (Humann in the Loop Login Handling)

"""

import asyncio
import base64
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from browser_use import Agent, Browser
from browser_use.browser.events import ScreenshotEvent
from browser_use.agent.views import AgentSettings
from browser_use.llm import ChatGoogle

load_dotenv()

# LOGIN DETECTION PATTERNS
LOGIN_URL_PATTERNS = [
    "login", "signin", "sign-in", "sign_in",
    "auth", "authenticate", "oauth",
    "signup"
]

LOGIN_PAGE_INDICATORS = [
    "password", "email", "username", "sign in", "log in",
    "forgot password", "create account", "register","signup"
]



# DATASET SCHEMA

class CapturedStep(BaseModel):
    step_number: int
    timestamp: str
    action_type: str
    action_description: str
    url: str
    page_title: str
    screenshot: str
    duration_ms: Optional[float] = None
    success: bool = True
    error_message: Optional[str] = None
    required_manual_login: bool = False


class CapturedWorkflow(BaseModel):
    task_id: str
    original_query: str
    transformed_task: str
    app_name: str
    app_url: str
    started_at: str
    completed_at: Optional[str] = None
    total_duration_seconds: Optional[float] = None
    success: bool = False
    steps: List[CapturedStep] = Field(default_factory=list)
    final_result: Optional[str] = None
    error_summary: Optional[str] = None



# CONFIGURATION


APP_CONFIG = {
    "linear": {"url": "https://linear.app", "name": "Linear"},
    "notion": {"url": "https://notion.so", "name": "Notion"},
    "asana": {"url": "https://app.asana.com", "name": "Asana"},
    "github": {"url": "https://github.com", "name": "GitHub"},
}


def detect_app(user_input: str) -> tuple[str, dict]:
    input_lower = user_input.lower()
    for app_key, config in APP_CONFIG.items():
        if app_key in input_lower:
            return app_key, config
    return "unknown", {"url": "", "name": "Unknown"}


def transform_to_action_task(user_input: str, app_config: dict) -> str:
    app_url = app_config.get("url", "")
    app_name = app_config.get("name", "the application")
    
    return f"""TASK: {user_input}

INSTRUCTIONS:
1. Navigate to {app_url} if not already there
2. Perform the requested action by interacting with the UI directly

CONSTRAINTS:
- ONLY interact with {app_name} UI
- NEVER search the web or open documentation  
- NEVER navigate away from {app_name} domains
- If you know that completing this task would require logging in, navigate there first
- If you see a login page, STOP and wait - the user will log in manually

COMPLETION: Task is complete when the requested action has been performed."""


def is_login_page(url: str, title: str = "") -> bool:
    url_lower = url.lower()
    title_lower = title.lower()
    
    for pattern in LOGIN_URL_PATTERNS:
        if pattern in url_lower:
            return True
    
    for indicator in LOGIN_PAGE_INDICATORS:
        if indicator in title_lower:
            return True
    
    return False



# CAPTURE HOOK WITH LOGIN DETECTION


def create_capture_hook(output_dir: Path, workflow: CapturedWorkflow):
    step_data = {
        "count": 0, 
        "step_start_time": None,
        "login_handled": False,
        "waiting_for_login": False
    }
    
    async def on_step_start(agent: Agent):
        step_data["step_start_time"] = datetime.now()
    
    async def on_step_end(agent: Agent):
        step_data["count"] += 1
        step_num = step_data["count"]
        
        try:
            state = await agent.browser_session.get_browser_state_summary()
            current_url = state.url if state else "unknown"
            current_title = await agent.browser_session.get_current_page_title() or "untitled"
            
            if is_login_page(current_url, current_title) and not step_data["login_handled"]:
                step_data["waiting_for_login"] = True
                
                print("\n" + "="*60)
                print("LOGIN PAGE DETECTED")
                print("="*60)
                print(f"   URL: {current_url}")
                print(f"   Title: {current_title}")
                print("\n   Please log in manually in the browser window.")
                print("   Press ENTER here when you are done logging in.")
                print("="*60 + "\n")
                
                agent.pause()
                
                await asyncio.get_event_loop().run_in_executor(None, input)
                
                agent.resume()
                
                step_data["login_handled"] = True
                step_data["waiting_for_login"] = False
                
                print("Login completed. Resuming agent.\n")
                
                workflow.steps.append(CapturedStep(
                    step_number=step_num,
                    timestamp=datetime.now().isoformat(),
                    action_type="manual_login",
                    action_description="User manually logged in",
                    url=current_url,
                    page_title=current_title,
                    screenshot="",
                    required_manual_login=True,
                ))
                return
            
            screenshot_event = agent.browser_session.event_bus.dispatch(
                ScreenshotEvent(full_page=True)
            )
            await screenshot_event
            screenshot_result = await screenshot_event.event_result(
                raise_if_any=True, raise_if_none=True
            )
            
            if isinstance(screenshot_result, bytes):
                screenshot_bytes = screenshot_result
            elif isinstance(screenshot_result, str):
                screenshot_bytes = base64.b64decode(screenshot_result)
            else:
                screenshot_bytes = base64.b64decode(str(screenshot_result))
            
            filename = f"step_{step_num:03d}.png"
            (output_dir / filename).write_bytes(screenshot_bytes)
            
            actions = agent.history.model_actions()
            action_type = "initial"
            action_desc = "Initial state"
            
            if actions and len(actions) > 0:
                last = actions[-1]
                if isinstance(last, list) and len(last) > 0:
                    last = last[0]
                action_type = getattr(last, 'name', str(type(last).__name__))
                action_desc = str(last)[:200]
            
            duration_ms = None
            if step_data["step_start_time"]:
                duration_ms = (datetime.now() - step_data["step_start_time"]).total_seconds() * 1000
            
            workflow.steps.append(CapturedStep(
                step_number=step_num,
                timestamp=datetime.now().isoformat(),
                action_type=action_type,
                action_description=action_desc,
                url=current_url,
                page_title=current_title,
                screenshot=filename,
                duration_ms=duration_ms,
            ))
            
            print(f"Step {step_num}: {action_type}")
            
        except Exception as e:
            print(f"Capture error: {e}")
    
    return on_step_start, on_step_end



# MAIN EXECUTION (MODIFIED)

async def execute_task(user_input: str, browser, llm, agent_settings, max_steps: int = 25) -> CapturedWorkflow:

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Missing GOOGLE_API_KEY")
    
    print(f"\n{'='*70}")
    print(f"TASK: {user_input}")
    print(f"{'='*70}")
    
    app_key, app_config = detect_app(user_input)
    print(f"App: {app_config.get('name', 'Unknown')}")
    
    action_task = transform_to_action_task(user_input, app_config)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c == " " else "_" for c in user_input[:40]).replace(" ", "_")
    output_dir = Path("ui_dataset") / f"{timestamp}_{app_key}_{safe_name}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    workflow = CapturedWorkflow(
        task_id=f"{timestamp}_{app_key}",
        original_query=user_input,
        transformed_task=action_task,
        app_name=app_config.get("name", "Unknown"),
        app_url=app_config.get("url", ""),
        started_at=datetime.now().isoformat(),
    )
    
    on_step_start, on_step_end = create_capture_hook(output_dir, workflow)
    
    agent = Agent(
        task=action_task,
        llm=llm,
        browser=browser,
        agent_settings=agent_settings,
    )
    
    print("Starting agent.")
    print("If login appears, you will log in manually.\n")
    
    try:
        result = await agent.run(
            on_step_start=on_step_start,
            on_step_end=on_step_end,
            max_steps=max_steps,
        )
        
        workflow.completed_at = datetime.now().isoformat()
        workflow.success = True
        workflow.final_result = str(result) if result else "Completed"
        
        start = datetime.fromisoformat(workflow.started_at)
        end = datetime.fromisoformat(workflow.completed_at)
        workflow.total_duration_seconds = (end - start).total_seconds()
        
    except Exception as e:
        print(f"\nFailed: {e}")
        workflow.completed_at = datetime.now().isoformat()
        workflow.success = False
        workflow.error_summary = str(e)
    
    (output_dir / "workflow.json").write_text(
        workflow.model_dump_json(indent=2),
        encoding='utf-8'
    )
    
    print(f"Saved to: {output_dir}")
    return workflow


# MAIN (MODIFIED FOR SHARED BROWSER/LLM/SETTINGS)

async def main():

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Missing GOOGLE_API_KEY")

    print("\nInitializing shared Browser and LLM settings.\n")

    browser = Browser(
        headless=False,
        keep_alive=True
    )

    llm = ChatGoogle(
        model="gemini-2.0-flash",
        api_key=api_key,
        temperature=0,
    )

    agent_settings = AgentSettings(
        use_vision=True,
        max_failures=5,
        max_actions_per_step=2,
        step_timeout=150.0,
        llm_timeout=90.0,
    )

    tasks = [
        "How do I create a project in Linear?",
        "How do I filter issues by status in Linear?",
        "How do I delete a project in Linear?",
        "How do I create a table database named Sprint Tracker and in Notion?",
        "How do i delete the sprint tracker database in Notion?"
    ]

    for task in tasks:
        await execute_task(
            task,
            browser=browser,
            llm=llm,
            agent_settings=agent_settings
        )
        await asyncio.sleep(2)

    print("\nClosing shared browser...")
    await browser.kill()
    print("Browser closed.")


if __name__ == "__main__":
    asyncio.run(main())
