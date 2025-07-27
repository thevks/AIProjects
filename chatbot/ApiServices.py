import os
import json
import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

class APIServices:
    def __init__(self):
        self.github_token = os.getenv('GITHUB_PAT')
        self.weather_api_key = os.getenv('WEATHER_API_KEY')
        self.news_api_key = os.getenv('NEWS_API_KEY')
        self.onecompiler_token = os.getenv('ONECOMPILER_TOKEN')
        
        self.github_base = "https://api.github.com"
        self.weather_base = "http://api.weatherapi.com/v1"
        self.news_base = "https://newsapi.org/v2"
        self.onecompiler_base = "https://onecompiler.com/api/v1"
        
    async def _make_request(self, url: str, headers: Dict = None, params: Dict = None) -> Dict:
        """Make async HTTP request with error handling"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {"error": f"HTTP {response.status}: {await response.text()}"}
        except Exception as e:
            return {"error": f"Request failed: {str(e)}"}
    
    async def _make_post_request(self, url: str, data: Dict, headers: Dict = None) -> Dict:
        """Make async HTTP POST request with error handling"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {"error": f"HTTP {response.status}: {await response.text()}"}
        except Exception as e:
            return {"error": f"Request failed: {str(e)}"}

    async def get_github_repo_info(self, repo: str) -> str:
        """Get basic repository information"""
        if not self.github_token:
            return "❌ GitHub token not configured"
        
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        url = f"{self.github_base}/repos/{repo}"
        result = await self._make_request(url, headers)
        
        if "error" in result:
            return f"❌ Error fetching repo info: {result['error']}"
        
        return f"""📁 **{result['full_name']}**
📝 {result.get('description', 'No description')}
⭐ Stars: {result['stargazers_count']} | 🍴 Forks: {result['forks_count']}
🔗 Language: {result.get('language', 'Unknown')}
📅 Updated: {result['updated_at'][:10]}
🌐 URL: {result['html_url']}"""

    async def get_github_commits(self, repo: str, limit: int = 5) -> str:
        """Get latest commits from a repository"""
        if not self.github_token:
            return "❌ GitHub token not configured"
        
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        url = f"{self.github_base}/repos/{repo}/commits"
        params = {"per_page": limit}
        result = await self._make_request(url, headers, params)
        
        if "error" in result:
            return f"❌ Error fetching commits: {result['error']}"
        
        if not result:
            return "📭 No commits found"
        
        commits_text = f"🔄 **Latest {len(result)} commits for {repo}:**\n\n"
        for commit in result:
            commit_data = commit['commit']
            author = commit_data['author']['name']
            message = commit_data['message'].split('\n')[0][:60]
            date = commit_data['author']['date'][:10]
            sha = commit['sha'][:7]
            
            commits_text += f"• **{sha}** by {author} ({date})\n  {message}\n\n"
        
        return commits_text

    async def get_github_issues(self, repo: str, limit: int = 5, state: str = "open") -> str:
        """Get issues from a repository"""
        if not self.github_token:
            return "❌ GitHub token not configured"
        
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        url = f"{self.github_base}/repos/{repo}/issues"
        params = {"state": state, "per_page": limit}
        result = await self._make_request(url, headers, params)
        
        if "error" in result:
            return f"❌ Error fetching issues: {result['error']}"
        
        if not result:
            return f"📭 No {state} issues found"
        
        issues_text = f"🐛 **Latest {len(result)} {state} issues for {repo}:**\n\n"
        for issue in result:
            title = issue['title'][:50] + ("..." if len(issue['title']) > 50 else "")
            number = issue['number']
            author = issue['user']['login']
            labels = ", ".join([label['name'] for label in issue['labels'][:3]])
            created = issue['created_at'][:10]
            
            issues_text += f"• **#{number}** {title}\n"
            issues_text += f"  👤 by {author} ({created})"
            if labels:
                issues_text += f" | 🏷️ {labels}"
            issues_text += "\n\n"
        
        return issues_text

    async def get_current_weather(self, location: str) -> str:
        """Get current weather for a location"""
        if not self.weather_api_key:
            return "❌ Weather API key not configured"
        
        url = f"{self.weather_base}/current.json"
        params = {
            "key": self.weather_api_key,
            "q": location,
            "aqi": "yes"
        }
        
        result = await self._make_request(url, params=params)
        
        if "error" in result:
            return f"❌ Error fetching weather: {result['error']}"
        
        current = result['current']
        location_data = result['location']
        
        weather_text = f"""🌤️ **Weather for {location_data['name']}, {location_data['country']}**
🌡️ Temperature: {current['temp_c']}°C ({current['temp_f']}°F)
🌡️ Feels like: {current['feelslike_c']}°C ({current['feelslike_f']}°F)
☁️ Condition: {current['condition']['text']}
💨 Wind: {current['wind_kph']} km/h {current['wind_dir']}
💧 Humidity: {current['humidity']}%
👁️ Visibility: {current['vis_km']} km
📅 Local time: {location_data['localtime']}"""
        
        return weather_text

    async def get_weather_forecast(self, location: str, days: int = 3) -> str:
        """Get weather forecast for a location"""
        if not self.weather_api_key:
            return "❌ Weather API key not configured"
        
        if days > 10:
            return "❌ Weather forecast is only available for up to 10 days"
        
        if days < 1:
            return "❌ Please specify at least 1 day for forecast"
        
        url = f"{self.weather_base}/forecast.json"
        params = {
            "key": self.weather_api_key,
            "q": location,
            "days": days,
            "aqi": "no"
        }
        
        result = await self._make_request(url, params=params)
        
        if "error" in result:
            return f"❌ Error fetching forecast: {result['error']}"
        
        location_data = result['location']
        forecast_data = result['forecast']['forecastday']
        
        forecast_text = f"📅 **{days}-day forecast for {location_data['name']}, {location_data['country']}**\n\n"
        
        for day in forecast_data:
            date = day['date']
            day_data = day['day']
            forecast_text += f"**{date}**\n"
            forecast_text += f"🌡️ {day_data['mintemp_c']}°C - {day_data['maxtemp_c']}°C\n"
            forecast_text += f"☁️ {day_data['condition']['text']}\n"
            forecast_text += f"🌧️ Rain chance: {day_data['daily_chance_of_rain']}%\n\n"
        
        return forecast_text

    async def get_latest_news(self, category: str = "general", country: str = "us", limit: int = 5) -> str:
        """Get latest news headlines"""
        if not self.news_api_key:
            return "❌ News API key not configured"
        
        url = f"{self.news_base}/top-headlines"
        params = {
            "apiKey": self.news_api_key,
            "category": category,
            "country": country,
            "pageSize": limit
        }
        
        result = await self._make_request(url, params=params)
        
        if "error" in result:
            return f"❌ Error fetching news: {result['error']}"
        
        articles = result.get('articles', [])
        if not articles:
            return "📰 No news articles found"
        
        news_text = f"📰 **Latest {category.title()} News:**\n\n"
        
        for i, article in enumerate(articles, 1):
            title = article['title']
            source = article['source']['name']
            published = article['publishedAt'][:10] if article['publishedAt'] else "Unknown"
            url = article['url']
            
            news_text += f"**{i}. {title}**\n"
            news_text += f"📡 Source: {source} | 📅 {published}\n"
            news_text += f"🔗 [Read more]({url})\n\n"
        
        return news_text

    async def search_news(self, query: str, limit: int = 5) -> str:
        """Search for news articles"""
        if not self.news_api_key:
            return "❌ News API key not configured"
        
        url = f"{self.news_base}/everything"
        params = {
            "apiKey": self.news_api_key,
            "q": query,
            "sortBy": "publishedAt",
            "pageSize": limit,
            "language": "en"
        }
        
        result = await self._make_request(url, params=params)
        
        if "error" in result:
            return f"❌ Error searching news: {result['error']}"
        
        articles = result.get('articles', [])
        if not articles:
            return f"📰 No news articles found for '{query}'"
        
        news_text = f"🔍 **Search results for '{query}':**\n\n"
        
        for i, article in enumerate(articles, 1):
            title = article['title']
            source = article['source']['name']
            published = article['publishedAt'][:10] if article['publishedAt'] else "Unknown"
            url = article['url']
            
            news_text += f"**{i}. {title}**\n"
            news_text += f"📡 Source: {source} | 📅 {published}\n"
            news_text += f"🔗 [Read more]({url})\n\n"
        
        return news_text

    async def execute_code(self, language: str, code: str, stdin: str = "") -> str:
        """Execute code using OneCompiler API"""
        if not self.onecompiler_token:
            return "❌ OneCompiler token not configured"
        
        language_map = {
            "py": "python",
            "python": "python",
            "js": "javascript",
            "javascript": "javascript",
            "java": "java",
            "cpp": "cpp",
            "c": "c",
            "cs": "csharp",
            "csharp": "csharp",
            "go": "go",
            "rust": "rust",
            "php": "php",
            "ruby": "ruby",
            "swift": "swift",
            "kotlin": "kotlin",
            "scala": "scala",
            "r": "r"
        }
        
        lang_code = language_map.get(language.lower(), language.lower())
        
        url = f"{self.onecompiler_base}/run?access_token={self.onecompiler_token}"
        
        filename_map = {
            "python": "main.py",
            "javascript": "main.js",
            "java": "Main.java",
            "cpp": "main.cpp",
            "c": "main.c",
            "csharp": "main.cs",
            "go": "main.go",
            "rust": "main.rs",
            "php": "main.php",
            "ruby": "main.rb",
            "swift": "main.swift",
            "kotlin": "main.kt",
            "scala": "main.scala",
            "r": "main.r"
        }
        
        filename = filename_map.get(lang_code, "main.txt")
        
        data = {
            "language": lang_code,
            "stdin": stdin,
            "files": [
                {
                    "name": filename,
                    "content": code
                }
            ]
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        result = await self._make_post_request(url, data, headers)
        
        if "error" in result:
            return f"❌ Error executing code: {result['error']}"
        
        output_text = f"💻 **Code Execution Result ({lang_code})**\n\n"
        
        if result.get('stdout'):
            output_text += f"**Output:**\n```\n{result['stdout']}\n```\n\n"
        
        if result.get('stderr'):
            output_text += f"**Errors:**\n```\n{result['stderr']}\n```\n\n"
        
        if result.get('compilationOutput'):
            output_text += f"**Compilation:**\n```\n{result['compilationOutput']}\n```\n\n"
        
        if result.get('executionTime'):
            output_text += f"⏱️ Execution time: {result['executionTime']}ms\n"
        
        if result.get('memoryUsage'):
            output_text += f"💾 Memory usage: {result['memoryUsage']}KB\n"
        
        return output_text

api_services = None

def get_api_services() -> APIServices:
    """Get or create the global API services instance"""
    global api_services
    if api_services is None:
        api_services = APIServices()
    return api_services
