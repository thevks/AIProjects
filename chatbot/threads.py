import discord
from discord import app_commands, Interaction
from discord.ext import commands
from chat import handleChat

active_threads = set()

active_channels = {}

class ThreadCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="activate", description="Activate automatic responses in this channel (only your messages will be tracked)")
    async def activate(self, interaction: Interaction):
        channel_id = interaction.channel.id
        user_id = interaction.user.id
        
        if interaction.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread]:
            await interaction.response.send_message("❌ This command is for regular channels only. Use `/chat_thread` for thread functionality.", ephemeral=True)
            return
        
        if channel_id in active_channels:
            current_user = active_channels[channel_id]
            if current_user == user_id:
                await interaction.response.send_message("✅ This channel is already activated by you!", ephemeral=True)
            else:
                user_obj = self.bot.get_user(current_user)
                username = user_obj.display_name if user_obj else "Unknown User"
                await interaction.response.send_message(f"❌ This channel is already activated by {username}. Only one user can activate a channel at a time.", ephemeral=True)
            return
        
        active_channels[channel_id] = user_id
        await interaction.response.send_message(
            f"✅ Channel activated! I'll now respond to all your messages automatically in this channel.\n"
            f"Use `/deactivate` to stop automatic responses.",
            ephemeral=True
        )

    @app_commands.command(name="deactivate", description="Deactivate automatic responses in this channel")
    async def deactivate(self, interaction: Interaction):
        channel_id = interaction.channel.id
        user_id = interaction.user.id
        
        if interaction.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread]:
            await interaction.response.send_message("❌ This command is for regular channels only. Use `/end_thread` for thread functionality.", ephemeral=True)
            return
        
        if channel_id not in active_channels:
            await interaction.response.send_message("❌ This channel is not activated.", ephemeral=True)
            return
        
        if active_channels[channel_id] != user_id:
            await interaction.response.send_message("❌ You can only deactivate a channel that you activated.", ephemeral=True)
            return
        
        del active_channels[channel_id]
        await interaction.response.send_message("✅ Channel deactivated. I'll no longer respond automatically in this channel.", ephemeral=True)

    @app_commands.command(name="chat_thread", description="Create a private chat thread with Pebble")
    async def chat_thread(self, interaction: Interaction, message: str = "Hello!"):
        try:
            thread = await interaction.channel.create_thread(
                name=f"💬 Chat with {interaction.user.display_name}",
                type=discord.ChannelType.private_thread,
                reason=f"Private chat thread created by {interaction.user}"
            )
            
            active_threads.add(thread.id)
            
            await interaction.response.send_message(
                f"✅ Private chat thread created: {thread.mention}\n"
                f"I'll respond to all messages in that thread automatically!",
                ephemeral=True
            )
            
            if message and message != "Hello!":
                await thread.send("🚀 **Thread started!** I'll respond to all messages here automatically.")
                await handleChat(MockContext(thread, interaction.user), message)
            else:
                await thread.send("🚀 **Private chat thread started!** I'll respond to all messages here automatically. What would you like to chat about?")
                
        except Exception as e:
            await interaction.response.send_message(f"❌ Error creating thread: {str(e)}", ephemeral=True)

    @app_commands.command(name="chat_thread_public", description="Create a public chat thread with Pebble")
    async def chat_thread_public(self, interaction: Interaction, message: str = "Hello!"):
        try:
            thread = await interaction.channel.create_thread(
                name=f"🌐 Public Chat with Pebble - {interaction.user.display_name}",
                type=discord.ChannelType.public_thread,
                reason=f"Public chat thread created by {interaction.user}"
            )
            
            active_threads.add(thread.id)
            
            await interaction.response.send_message(
                f"✅ Public chat thread created: {thread.mention}\n"
                f"I'll respond to all messages in that thread automatically!",
                ephemeral=True
            )
            
            if message and message != "Hello!":
                await thread.send("🚀 **Public thread started!** I'll respond to all messages here automatically.")
                await handleChat(MockContext(thread, interaction.user), message)
            else:
                await thread.send("🚀 **Public chat thread started!** I'll respond to all messages here automatically. What would you like to chat about?")
                
        except Exception as e:
            await interaction.response.send_message(f"❌ Error creating thread: {str(e)}", ephemeral=True)

    @app_commands.command(name="end_thread", description="Stop Pebble from responding in this thread")
    async def end_thread(self, interaction: Interaction):
        if interaction.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread]:
            if interaction.channel.id in active_threads:
                active_threads.remove(interaction.channel.id)
                await interaction.response.send_message("✅ I'll stop responding automatically in this thread.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ This thread is not an active chat thread.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ This command can only be used in threads.", ephemeral=True)

class MockContext:
    def __init__(self, channel, author):
        self.channel = channel
        self.author = author
        self.message = None
        self.send = channel.send

    def __setattr__(self, name, value):
        if name == 'message' and value is not None:
            object.__setattr__(self, name, value)
        else:
            object.__setattr__(self, name, value)

async def handle_thread_message(bot, message):
    """Handle messages in active threads"""
    if (message.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread] 
        and message.channel.id in active_threads):
        
        mock_ctx = MockContext(message.channel, message.author)
        mock_ctx.message = message
        
        await handleChat(mock_ctx, message.content)
        return True
    return False

async def handle_activated_channel_message(bot, message):
    """Handle messages in activated channels"""
    if (message.channel.type == discord.ChannelType.text 
        and message.channel.id in active_channels):
        
        if active_channels[message.channel.id] == message.author.id:
            mock_ctx = MockContext(message.channel, message.author)
            mock_ctx.message = message
            
            await handleChat(mock_ctx, message.content)
            return True
    return False

async def cleanup_deleted_thread(thread_id):
    """Clean up context when a thread is deleted"""
    if thread_id in active_threads:
        active_threads.remove(thread_id)
        
        from chat import (threadConversations, threadFileContexts, 
                         threadImageContexts, threadImageDescriptions, threadLastInteraction)
        
        if thread_id in threadConversations:
            del threadConversations[thread_id]
        if thread_id in threadFileContexts:
            del threadFileContexts[thread_id]
        if thread_id in threadImageContexts:
            del threadImageContexts[thread_id]
        if thread_id in threadImageDescriptions:
            del threadImageDescriptions[thread_id]
        if thread_id in threadLastInteraction:
            del threadLastInteraction[thread_id]
            
        print(f"Removed deleted thread {thread_id} from active threads and cleaned up context")