import os
import asyncio
import discord
from discord import app_commands, Interaction
from discord.ext import commands
from chat import handleChat
from threads import ThreadCommands, handle_thread_message, handle_activated_channel_message, cleanup_deleted_thread
from RagHandler import get_rag_handler

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

class SlashCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="chat", description="Ask Pebble a question. Note: Use !c if you want to attach files or images.")
    async def chat(self, interaction: Interaction, message: str):
        await handleChat(interaction, message)

    @app_commands.command(name="reset", description="Reset your conversation and context")
    async def reset(self, interaction: Interaction):
        from chat import (conversations, fileContexts, imageContexts, imageDescriptions,
                         threadConversations, threadFileContexts, threadImageContexts, threadImageDescriptions)
        from threads import active_threads
        
        userId = interaction.user.id
        
        rag_handler = get_rag_handler()
        
        isInThread = (interaction.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread] and 
                     interaction.channel.id in active_threads)
        
        await interaction.response.defer(thinking=True)
        
        conversations[userId] = []
        fileContexts[userId] = ""
        imageContexts[userId] = {}
        imageDescriptions[userId] = ""
        
        user_rag_cleared = await rag_handler.delete_tenant_data(userId)
        
        reset_message = "✅ Your personal conversation and context have been reset."
        if user_rag_cleared:
            reset_message += " Document knowledge base cleared."
        
        if isInThread:
            threadId = interaction.channel.id
            threadConversations[threadId] = []
            threadFileContexts[threadId] = ""
            threadImageContexts[threadId] = {}
            threadImageDescriptions[threadId] = ""
            
            thread_rag_cleared = await rag_handler.delete_tenant_data(userId, threadId)
            
            reset_message = "✅ Both your personal and thread conversation contexts have been reset."
            if user_rag_cleared and thread_rag_cleared:
                reset_message += " All document knowledge bases cleared."
            elif user_rag_cleared or thread_rag_cleared:
                reset_message += " Some document knowledge bases cleared."
        
        await interaction.followup.send(reset_message)

    @app_commands.command(name="history", description="View the length and status of your current session")
    async def history(self, interaction: Interaction):
        from chat import (conversations, fileContexts, imageContexts, imageDescriptions,
                         threadConversations, threadFileContexts, threadImageContexts, threadImageDescriptions)
        from threads import active_threads
        
        userId = interaction.user.id
        
        if (interaction.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread] and 
            interaction.channel.id in active_threads):
            threadId = interaction.channel.id
            if threadId in threadConversations:
                historyLength = len(threadConversations[threadId])
                hasFile = "with" if threadFileContexts[threadId] else "without"
                hasImage = "with" if threadImageDescriptions[threadId] else "without"
                await interaction.response.send_message(
                    f"📊 **Thread Conversation**: {historyLength} messages, {hasFile} file, {hasImage} image.")
            else:
                await interaction.response.send_message("📊 **Thread**: No conversation history found.")
        else:
            if userId in conversations:
                historyLength = len(conversations[userId])
                hasFile = "with" if fileContexts[userId] else "without"
                hasImage = "with" if imageDescriptions[userId] else "without"
                await interaction.response.send_message(
                    f"📊 **Personal Conversation**: {historyLength} messages, {hasFile} file, {hasImage} image.")
            else:
                await interaction.response.send_message("📊 **Personal**: No conversation history found.")

class RAGCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="docs_list", description="List all documents in your knowledge base")
    async def docs_list(self, interaction: Interaction):
        try:
            await interaction.response.defer(thinking=True)
            
            threadId = None
            if (interaction.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread]):
                from threads import active_threads
                if interaction.channel.id in active_threads:
                    threadId = interaction.channel.id
            
            rag_handler = get_rag_handler()
            files = await rag_handler.list_stored_files(interaction.user.id, threadId)
            
            if not files:
                await interaction.followup.send("📚 No documents found in your knowledge base.")
                return
            
            file_list = "📚 **Your Knowledge Base:**\n\n"
            for file_info in files:
                pages_info = f" ({file_info.get('pages', 0)} pages)" if file_info.get('pages', 0) > 0 else ""
                file_list += f"• **{file_info['filename']}**{pages_info} - {file_info['chunks']} chunks\n"
            
            if len(file_list) > 2000:
                file_list = file_list[:1900] + "\n... (list truncated)"
            
            await interaction.followup.send(file_list)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Error listing documents: {str(e)}")

    @app_commands.command(name="docs_clear", description="Clear all documents from your knowledge base")
    async def docs_clear(self, interaction: Interaction):
        try:
            await interaction.response.defer(thinking=True)
            
            threadId = None
            if (interaction.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread]):
                from threads import active_threads
                if interaction.channel.id in active_threads:
                    threadId = interaction.channel.id
            
            rag_handler = get_rag_handler()
            success = await rag_handler.delete_tenant_data(interaction.user.id, threadId)
            
            if success:
                context_type = "thread" if threadId else "personal"
                await interaction.followup.send(f"✅ All documents cleared from your {context_type} knowledge base.")
            else:
                await interaction.followup.send("❌ Failed to clear documents from knowledge base.")
                
        except Exception as e:
            await interaction.followup.send(f"❌ Error clearing documents: {str(e)}")

    @app_commands.command(name="docs_delete", description="Delete a specific document from your knowledge base")
    async def docs_delete(self, interaction: Interaction, filename: str):
        try:
            await interaction.response.defer(thinking=True)
            
            threadId = None
            if (interaction.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread]):
                from threads import active_threads
                if interaction.channel.id in active_threads:
                    threadId = interaction.channel.id
            
            rag_handler = get_rag_handler()
            success = await rag_handler.delete_file(filename, interaction.user.id, threadId)
            
            if success:
                await interaction.followup.send(f"✅ Document **{filename}** deleted from your knowledge base.")
            else:
                await interaction.followup.send(f"❌ Failed to delete **{filename}** or file not found.")
                
        except Exception as e:
            await interaction.followup.send(f"❌ Error deleting document: {str(e)}")

    @app_commands.command(name="docs_search", description="Search through your documents")
    async def docs_search(self, interaction: Interaction, query: str):
        try:
            await interaction.response.defer(thinking=True)
            
            threadId = None
            if (interaction.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread]):
                from threads import active_threads
                if interaction.channel.id in active_threads:
                    threadId = interaction.channel.id
            
            rag_handler = get_rag_handler()
            results = await rag_handler.query_documents(query, interaction.user.id, threadId, limit=8)
            
            if not results:
                await interaction.followup.send(f"🔍 No relevant documents found for: **{query}**")
                return
            
            response = f"🔍 **Search Results for:** {query}\n\n"
            
            for i, result in enumerate(results, 1):
                content = result["content"]
                if len(content) > 200:
                    content = content[:200] + "..."
                
                page_info = f" (Page {result['page_number']})" if result.get('page_number') else ""
                response += f"**{i}. {result['filename']}{page_info}** (Score: {result['score']:.3f})\n"
                response += f"```\n{content}\n```\n\n"
                
                if len(response) > 1500:
                    response += "... (results truncated)"
                    break
            
            await interaction.followup.send(response)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Error searching documents: {str(e)}")

async def register_commands():
    try:
        await bot.add_cog(SlashCommands(bot))
        await bot.add_cog(ThreadCommands(bot))
        await bot.add_cog(RAGCommands(bot))
        print("✅ Slash command cogs added.")
        synced = await bot.tree.sync()
        print(f"✅ Successfully synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

@bot.command(name='chat', aliases=['c', 'C'])
async def legacy_chat(ctx, *, message):
    await handleChat(ctx, message)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if await handle_thread_message(bot, message):
        return
    
    if await handle_activated_channel_message(bot, message):
        return
    
    await bot.process_commands(message)

@bot.event
async def on_thread_delete(thread):
    await cleanup_deleted_thread(thread.id)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    
    try:
        get_rag_handler()
        print("✅ RAG handler initialized")
    except Exception as e:
        print(f"❌ Failed to initialize RAG handler: {e}")
    
    await register_commands()

def main():
    discordToken = os.getenv('DISCORD_TOKEN')
    if not discordToken:
        print("ERROR: DISCORD_TOKEN environment variable not set")
        return

    async def start_bot():
        await bot.start(discordToken)

    asyncio.run(start_bot())

if __name__ == "__main__":
    main()