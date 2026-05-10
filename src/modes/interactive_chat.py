import streamlit as st
import logging
import os
import json
import time
from shared.state import AppState
from shared.camera import CameraThread, get_video_devices
from tools.registry import registry
# Import tools to ensure they register
import tools.camera_capture
import tools.web_scraper
from services.system_monitor import SystemMonitor

logger = logging.getLogger(__name__)

def get_shared_state():
    if "app_state" not in st.session_state:
        st.session_state.app_state = AppState()
        
    state = st.session_state.app_state
    
    # Ensure camera is running if not
    if not hasattr(state, 'camera_thread') or state.camera_thread is None or not state.camera_thread.is_alive():
        cam = CameraThread(state)
        cam.start()
        state.camera_thread = cam
        
    return state

def run():
    st.title("Interactive Chat 💬")
    
    state = get_shared_state()
    
    # --- Sidebar Configuration ---
    with st.sidebar:
        st.header("Configuration")
        
        # 1. Camera Preview
        with st.expander("Live Camera Feed", expanded=True):
            from streamlit_webrtc import webrtc_streamer, WebRtcMode
            import av
            from aiortc import VideoStreamTrack
            import asyncio
            import numpy as np
            
            class CameraStreamTrack(VideoStreamTrack):
                def __init__(self, state):
                    super().__init__()
                    self.state = state
                    self.kind = "video"

                async def recv(self):
                    pts, time_base = await self.next_timestamp()
                    frame = None
                    for _ in range(10):
                        with self.state.lock:
                            if self.state.latest_frame is not None:
                                frame = self.state.latest_frame.copy()
                                break
                        await asyncio.sleep(0.01)
                    
                    if frame is None:
                        frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    
                    new_frame = av.VideoFrame.from_ndarray(frame, format="rgb24")
                    new_frame.pts = pts
                    new_frame.time_base = time_base
                    return new_frame

            if "chat_cam_track" not in st.session_state:
                st.session_state["chat_cam_track"] = CameraStreamTrack(state)

            webrtc_streamer(
                key="chat_monitor",
                mode=WebRtcMode.RECVONLY,
                source_video_track=st.session_state["chat_cam_track"],
                media_stream_constraints={"video": True, "audio": False},
                rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
            )
            
            # Device Selection
            video_devices = get_video_devices()
            try:
                dev_index = video_devices.index(state.camera_thread.device)
            except ValueError:
                dev_index = 0
                
            selected_device = st.selectbox("Video Device", video_devices, index=dev_index)
            
            if st.button("Apply & Restart Camera"):
                if state.camera_thread and state.camera_thread.is_alive():
                    state.camera_thread.running = False
                    state.camera_thread.join(timeout=1.0)
                
                new_thread = CameraThread(state, device=selected_device)
                new_thread.start()
                state.camera_thread = new_thread
                st.success(f"Switched to {selected_device}")
                st.rerun()

        # 2. LLM Settings
        with st.expander("LLM Settings", expanded=True):
            provider = st.selectbox("Model Provider", ["Gemini", "Groq", "Ollama"])
            
            api_key = ""
            base_url = ""
            model_name = ""
            
            if provider == "Gemini":
                api_key = st.text_input("Gemini API Key", type="password", help="Get from Google AI Studio")
                model_options = [
                    "gemini-2.0-flash", 
                    "gemini-2.0-flash-lite", 
                    "gemini-flash-latest", 
                    "gemini-pro-latest",
                    "gemini-2.0-flash-exp",
                    "gemini-1.5-flash",
                    "gemini-1.5-pro",
                    "Custom..."
                ]
                selected_model = st.selectbox("Gemini Model", model_options, index=0)
                if selected_model == "Custom...":
                    model_name = st.text_input("Enter Custom Model Name", value="gemini-1.5-flash")
                else:
                    model_name = selected_model
                
                if st.button("Check Available Models"):
                    if not api_key:
                        st.error("Please enter API Key first.")
                    else:
                        try:
                            from google import genai
                            client = genai.Client(api_key=api_key)
                            st.info("Checking credentials...")
                            client.models.generate_content(model="gemini-1.5-flash", contents="Test")
                            st.success("Credentials Valid!")
                        except Exception as e:
                            st.error(f"Error checking API: {e}")
                            
            elif provider == "Groq":
                api_key = st.text_input("Groq API Key", type="password", help="Get from Groq Console")
                groq_models = [
                    "llama-3.3-70b-versatile", 
                    "llama-3.1-70b-versatile", 
                    "llama-3.1-8b-instant",
                    "gemma2-9b-it",
                    "mixtral-8x7b-32768"
                ]
                model_name = st.selectbox("Groq Model", groq_models)
            else:
                base_url = st.text_input("Ollama Base URL", value="http://localhost:11434")
                
                # Fetch Models
                from adapters.ollama_client import OllamaClient
                ollama_models = OllamaClient.get_models(base_url, capability="tools")
                
                if ollama_models:
                    model_name = st.selectbox("Ollama Model", ollama_models)
                else:
                    st.warning("No tool-capable models found (e.g. llama3.1, mistral-nemo).")
                    model_name = st.text_input("Ollama Model (Manual)", value="llama3.2:1b")
                    
                # Handle Unloading
                if "last_chat_model" not in st.session_state:
                    st.session_state.last_chat_model = model_name
                
                if st.session_state.last_chat_model != model_name:
                    st.toast(f"Unloading {st.session_state.last_chat_model}...", icon="🧹")
                    OllamaClient.unload_model(st.session_state.last_chat_model)
                    st.session_state.last_chat_model = model_name
            
            # System Metrics
            st.markdown("---")
            st.markdown("### System Resources")
            metrics = SystemMonitor().get_metrics()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("CPU", f"{metrics['cpu_percent']}%")
            c1.metric("RAM", f"{metrics['ram']['percent']}%", f"{metrics['ram']['used_gb']}/{metrics['ram']['total_gb']} GB")
            
            if metrics['gpu']:
                c2.metric("GPU Util", f"{metrics['gpu']['utilization_percent']}%")
                c2.metric("VRAM", f"{metrics['gpu']['memory_percent']}%", f"{metrics['gpu']['used_gb']}/{metrics['gpu']['total_gb']} GB")
                c3.caption(f"GPU: {metrics['gpu']['name']}")
            else:
                c2.warning("No GPU detected")

        # 3. Tool Selection
        with st.expander("MCP Tools"):
            all_tools = registry.get_all_tools()
            selected_tools = []
            for name in all_tools:
                if st.checkbox(f"Enable {name}", value=True):
                    selected_tools.append(name)

    # --- Chat Interface ---
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if "image" in message:
                st.image(message["image"])
            st.markdown(message["content"])
            if "tool_calls" in message:
                with st.status("Thinking...", state="complete"):
                    for tc in message["tool_calls"]:
                        st.write(f"⚙️ Used tool: `{tc['name']}`")
                        st.code(tc['args'], language="json")
                        st.write(f"Result: {tc['result'][:200]}..." if len(tc['result']) > 200 else f"Result: {tc['result']}")

    if prompt := st.chat_input("Ask something..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            
            # --- ReAct Loop ---
            full_response = None
            try:
                if provider == "Gemini" and api_key:
                    from google import genai
                    from google.genai import types
                    client = genai.Client(api_key=api_key)
                    
                    # Prepare Tools
                    # Gemini SDK 0.1+ supports passing functions directly!
                    # We need to wrap them to inject state if needed
                    active_funcs = []
                    for name in selected_tools:
                        tool_def = registry.get_tool(name)
                        func = tool_def["func"]
                        # Wrapper to handle state injection
                        if name == "capture_current_frame":
                            # Create a partial-like wrapper that doesn't require state arg from LLM
                            def capture_wrapper():
                                return func(state)
                            capture_wrapper.__name__ = "capture_current_frame"
                            capture_wrapper.__doc__ = func.__doc__
                            active_funcs.append(capture_wrapper)
                        else:
                            active_funcs.append(func)

                    # Chat Session
                    # We need to reconstruct history for the chat session
                    # Gemini ChatSession manages history, but we have our own.
                    # Let's try stateless generate_content first for simplicity, 
                    # or use ChatSession and feed history.
                    
                    # Construct History for Gemini
                    # Gemini expects 'user' and 'model' roles
                    gemini_history = []
                    for m in st.session_state.messages[:-1]: # Exclude current prompt
                        role = "user" if m["role"] == "user" else "model"
                        if role == "model" and "tool_calls" in m:
                             # Skip complex tool history reconstruction for this simple demo
                             # Ideally we should pass tool calls and responses
                             pass 
                        else:
                            gemini_history.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))

                    chat = client.chats.create(model=model_name, history=gemini_history)
                    
                    # Generate with Tools
                    # Automatic function calling in new SDK!
                    response = chat.send_message(
                        prompt,
                        config=types.GenerateContentConfig(tools=active_funcs)
                    )
                    
                    # The SDK executes tools automatically? 
                    # Yes, if we use automatic_function_calling (default in some versions)
                    # Let's see if we can visualize it.
                    # The response object might contain function calls.
                    
                    # Actually, for full control and visualization, we might want to do it manually
                    # or inspect the chat history after return.
                    
                    full_response = response.text
                    
                    # Visualization (Post-hoc for auto-execution)
                    # We can check chat.history to see what happened
                    tool_calls_log = []
                    # Check last few turns
                    for part in response.candidates[0].content.parts:
                        if part.function_call:
                             tool_calls_log.append({
                                 "name": part.function_call.name,
                                 "args": str(part.function_call.args),
                                 "result": "Executed automatically" 
                             })
                    
                    if tool_calls_log:
                        with st.status("Thinking...", state="complete"):
                            for tc in tool_calls_log:
                                st.write(f"⚙️ Used tool: `{tc['name']}`")
                        
                        # Add to message for persistence
                        st.session_state.messages[-1]["tool_calls"] = tool_calls_log

                elif provider == "Groq" and api_key:
                    # Groq requires manual tool loop
                    from groq import Groq
                    client = Groq(api_key=api_key)
                    
                    messages = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
                    
                    tools_schema = registry.to_openai_tools()
                    # Filter by selected
                    active_schemas = [t for t in tools_schema if t["function"]["name"] in selected_tools]
                    
                    # First Call
                    completion = client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                        tools=active_schemas if active_schemas else None,
                        tool_choice="auto"
                    )
                    
                    msg = completion.choices[0].message
                    tool_calls = msg.tool_calls
                    
                    if tool_calls:
                        tool_logs = []
                        messages.append(msg) # Add assistant message with tool calls
                        
                        with st.status("Thinking...", state="complete"):
                            for tool_call in tool_calls:
                                func_name = tool_call.function.name
                                args = json.loads(tool_call.function.arguments)
                                
                                st.write(f"⚙️ Using tool: `{func_name}`")
                                st.code(args, language="json")
                                
                                # Execute
                                tool_def = registry.get_tool(func_name)
                                func = tool_def["func"]
                                
                                if func_name == "capture_current_frame":
                                    result = func(state) # Inject state
                                else:
                                    result = func(**args)
                                    
                                result_str = str(result)
                                st.write(f"Result: {result_str[:100]}...")
                                
                                tool_logs.append({
                                    "name": func_name,
                                    "args": args,
                                    "result": result_str
                                })
                                
                                messages.append({
                                    "tool_call_id": tool_call.id,
                                    "role": "tool",
                                    "name": func_name,
                                    "content": result_str,
                                })
                        
                        # Second Call (Get final answer)
                        completion_final = client.chat.completions.create(
                            model=model_name,
                            messages=messages
                        )
                        full_response = completion_final.choices[0].message.content
                        
                        # Save tool logs
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": full_response,
                            "tool_calls": tool_logs
                        })
                    else:
                        full_response = msg.content
                        st.session_state.messages.append({"role": "assistant", "content": full_response})

                elif provider == "Ollama":
                    # Use OpenAI Client for Ollama (Standard for Tool Calling)
                    from openai import OpenAI
                    
                    # Ollama v1 compatible endpoint
                    client = OpenAI(
                        base_url=f"{base_url}/v1",
                        api_key="ollama", # Required but unused
                    )
                    
                    messages = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
                    
                    tools_schema = registry.to_openai_tools()
                    # Filter by selected
                    active_schemas = [t for t in tools_schema if t["function"]["name"] in selected_tools]
                    
                    # Call API with streaming
                    stream = client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                        tools=active_schemas if active_schemas else None,
                        stream=True,
                    )
                    
                    # Variables to accumulate stream
                    full_content = ""
                    tool_calls_accumulated = []
                    current_tool_call = None
                    
                    # Stream Loop
                    for chunk in stream:
                        delta = chunk.choices[0].delta
                        
                        # Handle Content
                        if delta.content:
                            full_content += delta.content
                            response_placeholder.markdown(full_content + "▌")
                            
                        # Handle Tool Calls
                        if delta.tool_calls:
                            for tc_chunk in delta.tool_calls:
                                if len(tool_calls_accumulated) <= tc_chunk.index:
                                    tool_calls_accumulated.append({
                                        "id": "", "type": "function", "function": {"name": "", "arguments": ""}
                                    })
                                
                                tc = tool_calls_accumulated[tc_chunk.index]
                                
                                if tc_chunk.id:
                                    tc["id"] += tc_chunk.id
                                if tc_chunk.function.name:
                                    tc["function"]["name"] += tc_chunk.function.name
                                if tc_chunk.function.arguments:
                                    tc["function"]["arguments"] += tc_chunk.function.arguments

                    # Finalize Content Display
                    if full_content:
                        response_placeholder.markdown(full_content)
                        st.session_state.messages.append({"role": "assistant", "content": full_content})

                    # Process Tool Calls if any
                    if tool_calls_accumulated:
                        tool_logs = []
                        # Reconstruct tool calls object for history
                        # We need to create a mock message object or dict
                        # For OpenAI history, we need the assistant message with tool_calls
                        
                        # Convert accumulated dicts to objects expected by OpenAI (if using objects)
                        # or just keep as dicts for our manual history management
                        
                        # Add assistant message with tool calls to history
                        # We need to format it correctly for the next API call
                        assistant_msg = {
                            "role": "assistant",
                            "content": full_content if full_content else None,
                            "tool_calls": tool_calls_accumulated
                        }
                        messages.append(assistant_msg)
                        
                        # Also save to session state for UI
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": full_content if full_content else None,
                            "tool_calls": [] # We will populate this after execution
                        })
                        
                        with st.status("Thinking...", state="complete"):
                            for tc in tool_calls_accumulated:
                                func_name = tc["function"]["name"]
                                args_str = tc["function"]["arguments"]
                                try:
                                    args = json.loads(args_str)
                                except json.JSONDecodeError:
                                    args = {} # Handle partial/invalid JSON
                                    
                                st.write(f"⚙️ Using tool: `{func_name}`")
                                st.code(args, language="json")
                                
                                # Execute
                                tool_def = registry.get_tool(func_name)
                                if tool_def:
                                    func = tool_def["func"]
                                    if func_name == "capture_current_frame":
                                        result = func(state)
                                    else:
                                        result = func(**args)
                                    result_str = str(result)
                                else:
                                    result_str = f"Error: Tool {func_name} not found"

                                st.write(f"Result: {result_str[:100]}...")
                                
                                tool_logs.append({
                                    "name": func_name,
                                    "args": args,
                                    "result": result_str
                                })
                                
                                messages.append({
                                    "tool_call_id": tc["id"] if tc["id"] else "call_" + func_name, # Ollama sometimes omits ID
                                    "role": "tool",
                                    "name": func_name,
                                    "content": result_str,
                                })
                        
                        # Update the last message in session state with tool logs
                        st.session_state.messages[-1]["tool_calls"] = tool_logs
                        
                        # Final Response (Streamed)
                        stream_final = client.chat.completions.create(
                            model=model_name,
                            messages=messages,
                            stream=True
                        )
                        
                        full_final_response = ""
                        for chunk in stream_final:
                            delta = chunk.choices[0].delta
                            if delta.content:
                                full_final_response += delta.content
                                response_placeholder.markdown(full_final_response + "▌")
                                
                        response_placeholder.markdown(full_final_response)
                        
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": full_final_response,
                            "tool_calls": tool_logs
                        })

                else:
                    full_response = "Provider not implemented or missing API Key."
                    st.session_state.messages.append({"role": "assistant", "content": full_response})

            except Exception as e:
                full_response = f"Error: {e}"
                st.session_state.messages.append({"role": "assistant", "content": full_response})

            if full_response:
                response_placeholder.markdown(full_response)
