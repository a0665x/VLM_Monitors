import inspect
import functools
import json

class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, func):
        """Decorator to register a function as a tool."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        self._tools[func.__name__] = {
            "func": func,
            "name": func.__name__,
            "description": func.__doc__ or "",
            "parameters": self._get_parameters(func)
        }
        return wrapper

    def get_tool(self, name):
        return self._tools.get(name)

    def get_all_tools(self):
        return self._tools

    def _get_parameters(self, func):
        """Extracts parameters from function signature for JSON Schema."""
        sig = inspect.signature(func)
        params = {"type": "object", "properties": {}, "required": []}
        
        for name, param in sig.parameters.items():
            if name == "self" or name == "state": continue # Skip state injection
            
            param_type = "string" # Default
            if param.annotation == int: param_type = "integer"
            elif param.annotation == bool: param_type = "boolean"
            elif param.annotation == float: param_type = "number"
            
            params["properties"][name] = {
                "type": param_type,
                "description": f"Parameter {name}" # Could parse docstring for better desc
            }
            if param.default == inspect.Parameter.empty:
                params["required"].append(name)
                
        return params

    def to_gemini_tools(self):
        """Converts registered tools to Gemini API format."""
        tools_list = []
        for name, tool in self._tools.items():
            # Gemini expects a slightly different structure or just function declarations
            # For google-genai SDK, we can pass the function directly or a dict
            # But let's construct the declaration dict for clarity/compatibility
            
            # Note: google-genai SDK is smart enough to take functions directly in some cases,
            # but explicit schema is safer.
            
            # Actually, for google-genai, we can pass a list of callables!
            # But we need to handle 'state' injection manually if we pass callables directly.
            # So we might need to wrap them.
            pass
            
        # For simplicity with the new SDK, we will return the list of functions 
        # BUT we need to make sure they don't require 'state' in their signature 
        # if the LLM is calling them. We'll handle execution separately.
        return [t["func"] for t in self._tools.values()]

    def to_openai_tools(self):
        """Converts registered tools to OpenAI/Groq API format."""
        tools_list = []
        for name, tool in self._tools.items():
            tools_list.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool["description"],
                    "parameters": tool["parameters"]
                }
            })
        return tools_list

# Global Registry
registry = ToolRegistry()
