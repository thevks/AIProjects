import os
import uuid
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path
import tempfile
import time

from qdrant_client import QdrantClient, models
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.schema import Document
import PyPDF2

class RAGHandler:
    def __init__(self, qdrant_url: str = "http://localhost:6333", collection_name: str = "pebble_documents"):
        self.qdrant_url = qdrant_url
        self.collection_name = collection_name
        self.client = None
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'}
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Qdrant client with connection handling"""
        try:
            self.client = QdrantClient(url=self.qdrant_url)
            self.client.get_collections()
            print(f"✅ Connected to Qdrant at {self.qdrant_url}")
            
            asyncio.create_task(self._initialize_collection())
            
        except Exception as e:
            print(f"❌ Failed to connect to Qdrant at {self.qdrant_url}: {e}")
            print("💡 Make sure Qdrant is running: docker run -p 6333:6333 qdrant/qdrant")
            self.client = None
    
    async def _initialize_collection(self):
        """Initialize the Qdrant collection with multitenancy support"""
        if not self.client:
            return
            
        try:
            collections = self.client.get_collections()
            collection_exists = any(col.name == self.collection_name for col in collections.collections)
            
            if not collection_exists:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=384,
                        distance=models.Distance.COSINE
                    ),
                    hnsw_config=models.HnswConfigDiff(
                        payload_m=16,
                        m=0,
                    ),
                )
                
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="tenant_id",
                    field_schema=models.KeywordIndexParams(
                        type="keyword",
                        is_tenant=True,
                    ),
                )
                
                print(f"✅ Created Qdrant collection: {self.collection_name}")
            else:
                print(f"✅ Qdrant collection already exists: {self.collection_name}")
                
        except Exception as e:
            print(f"❌ Error initializing Qdrant collection: {e}")
    
    def _check_connection(self) -> bool:
        """Check if Qdrant connection is available"""
        if not self.client:
            return False
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False
    
    def _get_tenant_id(self, user_id: int, thread_id: Optional[int] = None) -> str:
        """Generate tenant ID based on user and thread"""
        if thread_id:
            return f"thread_{thread_id}"
        else:
            return f"user_{user_id}"
    
    async def _process_pdf_pages_streaming(self, pdf_reader, filename: str, max_pages_per_batch: int = 10):
        """Process PDF pages in batches to avoid memory issues"""
        documents = []
        total_pages = len(pdf_reader.pages)
        
        for i in range(0, total_pages, max_pages_per_batch):
            batch_end = min(i + max_pages_per_batch, total_pages)
            
            for page_num in range(i, batch_end):
                try:
                    page = pdf_reader.pages[page_num]
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        documents.append(Document(
                            page_content=page_text,
                            metadata={"filename": filename, "page_number": page_num + 1}
                        ))
                except Exception as e:
                    print(f"Warning: Error processing page {page_num + 1}: {e}")
                    continue
            
            await asyncio.sleep(0.01)
        
        return documents
    
    async def _generate_embeddings_batch(self, chunks: List[Document], batch_size: int = 5):
        """Generate embeddings in small batches to prevent blocking"""
        embeddings = []
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            
            batch_embeddings = []
            for chunk in batch:
                embedding = await asyncio.get_event_loop().run_in_executor(
                    None, self.embeddings.embed_query, chunk.page_content
                )
                batch_embeddings.append(embedding)
            
            embeddings.extend(batch_embeddings)
            
            await asyncio.sleep(0.01)

        
        return embeddings
    
    async def _store_chunks_batch(self, points: List[models.PointStruct], batch_size: int = 50):
        """Store points in Qdrant in batches to avoid overwhelming the database"""
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            
            self.client.upsert(
                collection_name=self.collection_name,
                points=batch
            )
            
            await asyncio.sleep(0.01)

    
    async def process_and_store_file(self, file_attachment, user_id: int, thread_id: Optional[int] = None) -> Dict[str, Any]:
        """Process a file and store it in the vector database with improved large file handling"""
        if not self._check_connection():
            return {"error": "RAG system is not available. Please ensure Qdrant is running."}
            
        temp_file_path = None
        try:
            if file_attachment.size > 10 * 1024 * 1024:
                return {"error": "File too large. Maximum size is 10MB."}

            temp_file_path = Path(tempfile.gettempdir()) / f"rag_bot_{time.time()}_{file_attachment.filename}"
            await file_attachment.save(str(temp_file_path))
            
            documents = []
            
            if file_attachment.filename.endswith('.txt'):
                with open(temp_file_path, 'r', encoding='utf-8') as file:
                    text = file.read()
                    if text:
                        documents.append(Document(page_content=text, metadata={"filename": file_attachment.filename}))

            elif file_attachment.filename.endswith('.pdf'):
                with open(temp_file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    total_pages = len(pdf_reader.pages)
                    
                    if total_pages > 50:
                        documents = await self._process_pdf_pages_streaming(
                            pdf_reader, file_attachment.filename, max_pages_per_batch=5
                        )
                    else:
                        for i, page in enumerate(pdf_reader.pages):
                            try:
                                page_text = page.extract_text()
                                if page_text and page_text.strip():
                                    documents.append(Document(
                                        page_content=page_text,
                                        metadata={"filename": file_attachment.filename, "page_number": i + 1}
                                    ))
                            except Exception as e:
                                print(f"Warning: Error processing page {i + 1}: {e}")
                                continue
                            
                            if i % 10 == 0:
                                await asyncio.sleep(0.01)
            else:
                return {"error": f"Unsupported file type: {file_attachment.filename}. Supported types: .txt, .pdf"}
            
            if not documents:
                return {"error": "No text content found in the file."}
            
            chunks = []
            for i, document in enumerate(documents):
                doc_chunks = self.text_splitter.split_documents([document])
                chunks.extend(doc_chunks)
                
                if i % 20 == 0:
                    await asyncio.sleep(0.01)
            
            if not chunks:
                return {"error": "No content chunks generated from the file."}
            
            tenant_id = self._get_tenant_id(user_id, thread_id)
            
            if len(chunks) > 50:
                embeddings = await self._generate_embeddings_batch(chunks, batch_size=3)
            else:
                embeddings = await self._generate_embeddings_batch(chunks, batch_size=5)
            
            points = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                point_id = str(uuid.uuid4())
                points.append(
                    models.PointStruct(
                        id=point_id,
                        payload={
                            "tenant_id": tenant_id,
                            "filename": chunk.metadata.get("filename"),
                            "page_number": chunk.metadata.get("page_number"),
                            "chunk_index": i,
                            "content": chunk.page_content,
                            "user_id": user_id,
                            "thread_id": thread_id,
                            "timestamp": time.time()
                        },
                        vector=embedding,
                    )
                )
                
                if i % 10 == 0:
                    await asyncio.sleep(0.01)
            
            if len(points) > 100:
                await self._store_chunks_batch(points, batch_size=25)
            else:
                await self._store_chunks_batch(points, batch_size=50)
            
            return {
                "success": True,
                "filename": file_attachment.filename,
                "chunks_stored": len(chunks),
                "pages_processed": len(documents),
                "tenant_id": tenant_id
            }
            
        except Exception as e:
            return {"error": f"Error processing file {file_attachment.filename}: {str(e)}"}
        
        finally:
            if temp_file_path and temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                except Exception:
                    await asyncio.sleep(0.1)
                    try:
                        temp_file_path.unlink()
                    except Exception:
                        pass
    
    async def query_documents(self, query: str, user_id: int, thread_id: Optional[int] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Query documents from the vector database for a specific tenant"""
        if not self._check_connection():
            return []
            
        try:
            tenant_id = self._get_tenant_id(user_id, thread_id)
            
            query_embedding = await asyncio.get_event_loop().run_in_executor(
                None, self.embeddings.embed_query, query
            )
            
            search_results = self.client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="tenant_id",
                            match=models.MatchValue(value=tenant_id),
                        )
                    ]
                ),
                limit=limit,
                with_payload=True,
            )
            
            results = []
            for point in search_results.points:
                results.append({
                    "content": point.payload.get("content", ""),
                    "filename": point.payload.get("filename", ""),
                    "page_number": point.payload.get("page_number"),
                    "chunk_index": point.payload.get("chunk_index", 0),
                    "score": point.score,
                    "timestamp": point.payload.get("timestamp", 0)
                })
            
            return results
            
        except Exception as e:
            return []
    
    async def get_context_for_query(self, query: str, user_id: int, thread_id: Optional[int] = None, max_context_length: int = 3000) -> str:
        """Get relevant context for a query, formatted for the chat system"""
        if not self._check_connection():
            return ""
            
        try:
            results = await self.query_documents(query, user_id, thread_id, limit=15)
            
            if not results:
                return ""
            
            context_parts = []
            current_length = 0
            seen_pages = set()
            
            for result in results:
                content = result["content"]
                filename = result["filename"]
                page_num = result.get('page_number')
                page_info = f" page {page_num}" if page_num else ""
                chunk_info = f"[{filename}{page_info}]"
                
                page_key = f"{filename}_{page_num}"
                if page_key in seen_pages:
                    continue
                seen_pages.add(page_key)
                
                chunk_text = f"{chunk_info}\n{content}\n\n"
                
                if current_length + len(chunk_text) > max_context_length:
                    break
                
                context_parts.append(chunk_text)
                current_length += len(chunk_text)
            
            if context_parts:
                context = "RELEVANT DOCUMENT CONTEXT:\n" + "".join(context_parts)
                context += "Use the above document context when relevant to answer the user's questions. "
                context += "For unrelated questions, do not mention that they are unrelated—just respond normally.\n\n"
                return context
            
            return ""
            
        except Exception as e:
            return ""
    
    async def list_stored_files(self, user_id: int, thread_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """List all files stored for a specific tenant"""
        if not self._check_connection():
            return []
            
        try:
            tenant_id = self._get_tenant_id(user_id, thread_id)
            
            search_results = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="tenant_id",
                            match=models.MatchValue(value=tenant_id),
                        )
                    ]
                ),
                with_payload=True,
                limit=1000,
            )
            
            files = {}
            for point in search_results[0]:
                filename = point.payload.get("filename", "")
                if filename not in files:
                    files[filename] = {
                        "filename": filename,
                        "chunks": 0,
                        "pages": set(),
                        "timestamp": point.payload.get("timestamp", 0)
                    }
                files[filename]["chunks"] += 1
                if point.payload.get("page_number"):
                    files[filename]["pages"].add(point.payload.get("page_number"))
            
            result = []
            for file_info in files.values():
                result.append({
                    "filename": file_info["filename"],
                    "chunks": file_info["chunks"],
                    "pages": len(file_info["pages"]) if file_info["pages"] else 0,
                    "timestamp": file_info["timestamp"]
                })
            
            return result
            
        except Exception as e:
            return []
    
    async def delete_tenant_data(self, user_id: int, thread_id: Optional[int] = None) -> bool:
        """Delete all data for a specific tenant"""
        if not self._check_connection():
            return False
            
        try:
            tenant_id = self._get_tenant_id(user_id, thread_id)
            
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="tenant_id",
                                match=models.MatchValue(value=tenant_id),
                            )
                        ]
                    )
                ),
            )
            
            return True
            
        except Exception as e:
            return False
    
    async def delete_file(self, filename: str, user_id: int, thread_id: Optional[int] = None) -> bool:
        """Delete a specific file for a tenant"""
        if not self._check_connection():
            return False
            
        try:
            tenant_id = self._get_tenant_id(user_id, thread_id)
            
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="tenant_id",
                                match=models.MatchValue(value=tenant_id),
                            ),
                            models.FieldCondition(
                                key="filename",
                                match=models.MatchValue(value=filename),
                            )
                        ]
                    )
                ),
            )
            
            return True
            
        except Exception as e:
            return False

rag_handler = None

def get_rag_handler() -> RAGHandler:
    """Get or create the global RAG handler instance"""
    global rag_handler
    if rag_handler is None:
        rag_handler = RAGHandler()
    return rag_handler