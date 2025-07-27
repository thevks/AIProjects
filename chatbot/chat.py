import os
import time
from collections import defaultdict
from groq import Groq
from fileHandler import processFile
from RagHandler import get_rag_handler
from FunctionCalling import get_function_handler

from discord.ext import commands

groqClient = Groq(api_key=os.getenv('GROQ_API_KEY'))

conversations = defaultdict(list)
fileContexts = defaultdict(str)
imageContexts = defaultdict(dict)
imageDescriptions = defaultdict(str)
lastInteraction = defaultdict(float)

threadConversations = defaultdict(list)
threadFileContexts = defaultdict(str)
threadImageContexts = defaultdict(dict)
threadImageDescriptions = defaultdict(str)
threadLastInteraction = defaultdict(float)

maxHistory = 16
historyExpiry = 86400

def pruneOldConversations():
    currentTime = time.time()
    
    for userId in list(conversations.keys()):
        if currentTime - lastInteraction[userId] > historyExpiry:
            del conversations[userId]
            del fileContexts[userId]
            del imageContexts[userId]
            del imageDescriptions[userId]
            del lastInteraction[userId]
    
    for threadId in list(threadConversations.keys()):
        if currentTime - threadLastInteraction[threadId] > historyExpiry:
            del threadConversations[threadId]
            del threadFileContexts[threadId]
            del threadImageContexts[threadId]
            del threadImageDescriptions[threadId]
            del threadLastInteraction[threadId]

async def analyzeImageWithVisionModel(imageData, userMessage=""):
    try:
        visionMessages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Analyze this image in detail. Describe what you see, including objects, people, text, colors, composition, and any other relevant details. If the user has a specific question about the image, focus on that as well. User's message: {userMessage}"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{imageData['base64']}"
                        }
                    }
                ]
            }
        ]

        completion = groqClient.chat.completions.create(
            model="meta-llama/llama-4-maverick-17b-128e-instruct",
            messages=visionMessages,
            temperature=0.3,
            max_completion_tokens=450,
        )

        description = completion.choices[0].message.content.strip()
        start = description.find("<think>")
        end = description.find("</think>")
        if start != -1 and end != -1:
            description = description[:start] + description[end + len("</think>"):]

        return description.strip()

    except Exception as e:
        return f"Error analyzing image: {str(e)}"

async def handleChat(source, message):
    try:
        isThread = False
        threadId = None
        
        if hasattr(source, 'user'):
            userId = source.user.id
            await source.response.defer(thinking=True)
            send_response = source.followup.send
            attachments = getattr(source, 'attachments', None) or []
        elif hasattr(source, 'message') and source.message:
            userId = source.author.id
            send_response = source.send
            attachments = source.message.attachments if source.message.attachments else []
            if hasattr(source, 'channel') and hasattr(source.channel, 'type'):
                try:
                    import discord
                    from main import active_threads
                    if (source.channel.type in [discord.ChannelType.private_thread, discord.ChannelType.public_thread] and 
                        source.channel.id in active_threads):
                        isThread = True
                        threadId = source.channel.id
                except ImportError:
                    pass
        else:
            userId = source.author.id
            send_response = source.send
            attachments = source.message.attachments if source.message.attachments else []

        if isThread:
            conv_dict = threadConversations
            file_dict = threadFileContexts
            image_dict = threadImageContexts
            desc_dict = threadImageDescriptions
            time_dict = threadLastInteraction
            contextId = threadId
        else:
            conv_dict = conversations
            file_dict = fileContexts
            image_dict = imageContexts
            desc_dict = imageDescriptions
            time_dict = lastInteraction
            contextId = userId

        time_dict[contextId] = time.time()

        function_handler = get_function_handler()
        
        original_message = message
        
        if message.strip():
            function_result = await function_handler.detect_and_execute_function(message, message)
            if function_result:
                await send_response(function_result)
                return

        rag_handler = get_rag_handler()

        if attachments:
            for attachment in attachments:
                if attachment.size > 10 * 1024 * 1024:
                    await send_response("File too large. Maximum size is 10MB.")
                    return

                if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')):
                    fileContent = await processFile(attachment)
                    
                    if isinstance(fileContent, str) and fileContent.startswith("Error processing image"):
                        await send_response(fileContent)
                        return
                    
                    if isinstance(fileContent, dict) and fileContent.get('type') == 'image':
                        image_dict[contextId] = fileContent
                        processingMessage = await send_response(f"📸 Processing image: {attachment.filename}...")
                        imageDescription = await analyzeImageWithVisionModel(fileContent, message)

                        if imageDescription.startswith("Error analyzing image"):
                            await processingMessage.edit(content=imageDescription)
                            return

                        desc_dict[contextId] = f"IMAGE ANALYSIS ({attachment.filename}):\n{imageDescription}"
                        await processingMessage.edit(content=f"✅ Image analyzed and added to context: {attachment.filename}")
                
                else:
                    file_size_mb = attachment.size / (1024 * 1024)
                    is_large_file = file_size_mb > 1.0
                    
                    if is_large_file:
                        processingMessage = await send_response(
                            f"📄 Processing large document: {attachment.filename} ({file_size_mb:.1f}MB)\n"
                            f"⏳ This may take a while, please be patient..."
                        )
                    else:
                        processingMessage = await send_response(f"📄 Processing document: {attachment.filename}...")
                    
                    async def update_progress(step_msg):
                        if is_large_file:
                            try:
                                current_content = f"📄 Processing large document: {attachment.filename} ({file_size_mb:.1f}MB)\n⏳ {step_msg}"
                                await processingMessage.edit(content=current_content)
                            except:
                                pass
                    
                    if hasattr(rag_handler, '_current_progress_callback'):
                        rag_handler._current_progress_callback = update_progress
                    
                    result = await rag_handler.process_and_store_file(
                        attachment, userId, threadId if isThread else None
                    )
                    
                    if "error" in result:
                        await processingMessage.edit(content=f"❌ {result['error']}")
                        return
                    
                    if result.get("success"):
                        pages_info = f" ({result.get('pages_processed', 0)} pages)" if result.get('pages_processed', 0) > 0 else ""
                        success_msg = (
                            f"✅ Document stored in knowledge base: {result['filename']}{pages_info}\n"
                            f"📊 Generated {result['chunks_stored']} searchable chunks"
                        )
                        await processingMessage.edit(content=success_msg)
                    else:
                        await processingMessage.edit(content="❌ Failed to process document")
                        return

        systemContext = ""

        if message.strip():
            rag_context = await rag_handler.get_context_for_query(
                message, userId, threadId if isThread else None
            )
            if rag_context:
                systemContext += rag_context

        if file_dict[contextId]:
            systemContext += f"LEGACY DOCUMENT CONTEXT:\n{file_dict[contextId]}\n\n"
        
        if desc_dict[contextId]:
            systemContext += f"{desc_dict[contextId]}\n\n"

        if systemContext:
            systemContext += (
                "Use the above context when relevant to answer the user's questions. "
                "For unrelated questions, do not mention that they are unrelated—just respond normally.\n\n"
            )
        else:
            systemContext = "Answer the user's question normally.\n\n"

        systemContext += (
            "You are Pebble, a friendly and helpful assistant.\n"
            "Keep responses concise and clear.\n"
            "Always use proper Discord Markdown formatting:\n"
            "- Use **bold**, *italics*, `inline code`, and code blocks where appropriate.\n"
            "- For code or terminal output, use triple backticks and specify the language. For example:\n"
            "  ```cpp\n"
            "  std::cout << \"Hello World\";\n"
            "  ```\n"
            "- Ensure formatting is clean and enhances readability.\n"
            "Always make sure the final response is under 2000 characters. If needed, shorten or summarize the response while keeping it useful and readable.\n"
        )

        userMessage = f"{systemContext}User: {message}"

        conv_dict[contextId].append({"role": "user", "content": userMessage})
        if len(conv_dict[contextId]) > maxHistory:
            conv_dict[contextId] = conv_dict[contextId][-maxHistory:]

        completion = groqClient.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=conv_dict[contextId],
            temperature=0.5,
            max_completion_tokens=450,
        )

        response = completion.choices[0].message.content
        start = response.find("<think>")
        end = response.find("</think>")
        if start != -1 and end != -1:
            response = response[:start] + response[end + len("</think>"):]
        response = response.strip()

        conv_dict[contextId].append({"role": "assistant", "content": response})
        await send_response(response)

        pruneOldConversations()

    except Exception as e:
        await send_response(f"An error occurred: {str(e)}")
        print(f"Error in handleChat: {e}")