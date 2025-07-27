import re
import json
from typing import Dict, List, Any, Optional, Tuple
from ApiServices import get_api_services

class FunctionCallHandler:
    def __init__(self):
        self.api_services = get_api_services()
        
        self.function_patterns = {
            "github_repo_info": {
                "patterns": [
                    r"(?:info|details|about)\s+(?:github\s+)?repo(?:sitory)?\s+([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)",
                    r"(?:show|get|fetch)\s+(?:github\s+)?repo(?:sitory)?\s+([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)",
                    r"tell me about\s+(?:the\s+)?(?:github\s+)?repo(?:sitory)?\s+([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)"
                ],
                "handler": self._handle_github_repo_info
            },
            "github_commits": {
                "patterns": [
                    r"(?:latest|recent)\s+commits?\s+(?:for|from|in)\s+([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)",
                    r"(?:show|get|fetch)\s+commits?\s+(?:for|from|in)\s+([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)",
                    r"(?:what are the\s+)?(?:latest|recent)\s+changes?\s+(?:to|in)\s+([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)",
                    r"commit history\s+(?:for|of)\s+([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)"
                ],
                "handler": self._handle_github_commits
            },
            "github_issues": {
                "patterns": [
                    r"(?:latest|recent|open)\s+issues?\s+(?:for|from|in)\s+([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)",
                    r"(?:show|get|fetch)\s+issues?\s+(?:for|from|in)\s+([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)",
                    r"(?:what are the\s+)?issues?\s+(?:in|with)\s+([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)"
                ],
                "handler": self._handle_github_issues
            },
            
            "current_weather": {
                "patterns": [
                    r"(?:what(?:'s| is)\s+the\s+)?(?:current\s+)?weather\s+(?:in|for|at)\s+([^?]+?)(?:\?|$)",
                    r"(?:how(?:'s| is)\s+the\s+)?weather\s+(?:in|for|at)\s+([^?]+?)(?:\?|$)",
                    r"(?:tell me\s+)?(?:the\s+)?weather\s+(?:for|in)\s+([^?]+?)(?:\?|$)",
                    r"weather\s+(?:report\s+)?(?:for\s+)?([^?]+?)(?:\?|$)"
                ],
                "handler": self._handle_current_weather
            },
            "weather_forecast": {
                "patterns": [
                    r"(?:weather\s+)?forecast\s+(?:for\s+)?([^?]+?)(?:\s+for\s+(\d+)\s+days?)?(?:\?|$)",
                    r"(?:what(?:'s| is)\s+the\s+)?weather\s+(?:going to be\s+)?(?:like\s+)?(?:in\s+)?([^?]+?)\s+(?:for\s+the\s+)?(?:next\s+)?(\d+)\s+days?",
                    r"(\d+)[\s-]day\s+forecast\s+(?:for\s+)?([^?]+?)(?:\?|$)",
                    r"weather\s+(?:for\s+)?(?:the\s+)?(?:next\s+)?(\d+)\s+days?\s+(?:in\s+)?([^?]+?)(?:\?|$)"
                ],
                "handler": self._handle_weather_forecast
            },
            
            "latest_news": {
                "patterns": [
                    r"(?:latest|recent|current)\s+(?:(tech|technology|sports|business|health|science|entertainment|general)\s+)?news",
                    r"(?:what(?:'s| is)\s+the\s+)?(?:latest|recent)\s+(?:(tech|technology|sports|business|health|science|entertainment|general)\s+)?news",
                    r"(?:show|get|fetch)\s+me\s+(?:the\s+)?(?:latest|recent)\s+(?:(tech|technology|sports|business|health|science|entertainment|general)\s+)?news",
                    r"news\s+(?:headlines?\s+)?(?:for\s+)?(tech|technology|sports|business|health|science|entertainment|general)?"
                ],
                "handler": self._handle_latest_news
            },
            "search_news": {
                "patterns": [
                    r"(?:search|find)\s+news\s+(?:about\s+)?([^?]+?)(?:\?|$)",
                    r"news\s+(?:about\s+)?([^?]+?)(?:\?|$)",
                    r"(?:what(?:'s| is)\s+)?(?:the\s+)?news\s+(?:on|about)\s+([^?]+?)(?:\?|$)"
                ],
                "handler": self._handle_search_news
            },
            
            "execute_code": {
                "patterns": [
                    r"(?:run|execute)\s+(?:this\s+)?(?:(python|javascript|java|cpp|c\+\+|c|csharp|c#|go|rust|php|ruby|swift|kotlin|scala|r)\s+)?code",
                    r"(?:can you\s+)?(?:run|execute)\s+(?:this\s+)?(?:(python|javascript|java|cpp|c\+\+|c|csharp|c#|go|rust|php|ruby|swift|kotlin|scala|r)\s+)?(?:code|script|program)",
                    r"(?:test|try)\s+(?:this\s+)?(?:(python|javascript|java|cpp|c\+\+|c|csharp|c#|go|rust|php|ruby|swift|kotlin|scala|r)\s+)?code"
                ],
                "handler": self._handle_execute_code
            }
        }
    
    async def detect_and_execute_function(self, message: str, full_message: str = None) -> Optional[str]:
        """
        Detect if the message contains a function call pattern and execute it
        Returns the function result or None if no function was detected
        """
        message_lower = message.lower().strip()
        
        for function_name, config in self.function_patterns.items():
            for pattern in config["patterns"]:
                match = re.search(pattern, message_lower, re.IGNORECASE)
                if match:
                    try:
                        result = await config["handler"](match.groups(), message, full_message)
                        return result
                    except Exception as e:
                        return f"❌ Error executing {function_name}: {str(e)}"
        
        return None
    
    async def _handle_github_repo_info(self, groups: Tuple, message: str, full_message: str = None) -> str:
        """Handle GitHub repository info requests"""
        repo = groups[0] if groups else None
        if not repo:
            return "❌ Please specify a repository in the format 'owner/repo'"
        
        return await self.api_services.get_github_repo_info(repo)
    
    async def _handle_github_commits(self, groups: Tuple, message: str, full_message: str = None) -> str:
        """Handle GitHub commits requests"""
        repo = groups[0] if groups else None
        if not repo:
            return "❌ Please specify a repository in the format 'owner/repo'"
        
        limit = 5
        limit_match = re.search(r'(\d+)\s+commits?', message)
        if limit_match:
            limit = min(int(limit_match.group(1)), 10)
        
        return await self.api_services.get_github_commits(repo, limit)
    
    async def _handle_github_issues(self, groups: Tuple, message: str, full_message: str = None) -> str:
        """Handle GitHub issues requests"""
        repo = groups[0] if groups else None
        if not repo:
            return "❌ Please specify a repository in the format 'owner/repo'"
        
        limit = 5
        limit_match = re.search(r'(\d+)\s+issues?', message)
        if limit_match:
            limit = min(int(limit_match.group(1)), 10)
        
        state = "closed" if "closed" in message.lower() else "open"
        
        return await self.api_services.get_github_issues(repo, limit, state)
    
    async def _handle_current_weather(self, groups: Tuple, message: str, full_message: str = None) -> str:
        """Handle current weather requests"""
        location = groups[0] if groups else None
        if not location:
            return "❌ Please specify a location"
        
        location = location.strip()
        return await self.api_services.get_current_weather(location)
    
    async def _handle_weather_forecast(self, groups: Tuple, message: str, full_message: str = None) -> str:
        """Handle weather forecast requests"""
        location = None
        days = 3
        
        for group in groups:
            if group and group.strip():
                if group.isdigit():
                    days = min(int(group), 10)
                else:
                    location = group.strip()
        
        if not location:
            return "❌ Please specify a location for the weather forecast"
        
        return await self.api_services.get_weather_forecast(location, days)
    
    async def _handle_latest_news(self, groups: Tuple, message: str, full_message: str = None) -> str:
        """Handle latest news requests"""
        category = groups[0] if groups and groups[0] else "general"
        
        category_map = {
            "tech": "technology",
            "sports": "sports",
            "business": "business",
            "health": "health",
            "science": "science",
            "entertainment": "entertainment"
        }
        
        category = category_map.get(category.lower(), category.lower()) if category else "general"
        
        limit = 5
        limit_match = re.search(r'(\d+)\s+(?:news|articles?|headlines?)', message)
        if limit_match:
            limit = min(int(limit_match.group(1)), 10)
        
        return await self.api_services.get_latest_news(category, "us", limit)
    
    async def _handle_search_news(self, groups: Tuple, message: str, full_message: str = None) -> str:
        """Handle news search requests"""
        query = groups[0] if groups else None
        if not query:
            return "❌ Please specify what to search for in the news"
        
        query = query.strip()
        
        limit = 5
        limit_match = re.search(r'(\d+)\s+(?:articles?|results?|headlines?)', message)
        if limit_match:
            limit = min(int(limit_match.group(1)), 10)
        
        return await self.api_services.search_news(query, limit)
    
    async def _handle_execute_code(self, groups: Tuple, message: str, full_message: str = None) -> str:
        """Handle code execution requests"""
        language = groups[0] if groups and groups[0] else None
        
        code = None
        stdin = ""
        
        code_block_match = re.search(r'```(?:(\w+)\s*)?\n(.*?)\n```', full_message or message, re.DOTALL)
        if code_block_match:
            detected_lang = code_block_match.group(1)
            code = code_block_match.group(2)
            if detected_lang and not language:
                language = detected_lang
        
        if not code:
            code_match = re.search(r'(?:code|script|program):\s*(.+)', message, re.DOTALL | re.IGNORECASE)
            if code_match:
                code = code_match.group(1).strip()
        
        if not code:
            return "❌ Please provide the code to execute. Use code blocks (```language\\ncode\\n```) for best results."
        
        if not language:
            language = "python"
        
        stdin_match = re.search(r'(?:input|stdin):\s*(.+)', message, re.IGNORECASE)
        if stdin_match:
            stdin = stdin_match.group(1).strip()
        
        return await self.api_services.execute_code(language, code, stdin)

function_handler = None

def get_function_handler() -> FunctionCallHandler:
    """Get or create the global function call handler instance"""
    global function_handler
    if function_handler is None:
        function_handler = FunctionCallHandler()
    return function_handler