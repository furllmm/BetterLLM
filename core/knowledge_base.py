from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import faiss
    import numpy as np
except ImportError:
    faiss = None
    np = None

from sentence_transformers import SentenceTransformer
from utils.paths import get_memory_root

logger = logging.getLogger(__name__)

class KnowledgeBase:
    """
    Manages document indexing and retrieval for RAG.
    Supports PDF, TXT, MD and code files.
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._embed_model = SentenceTransformer(model_name, device="cpu")
        self._index: Optional[faiss.IndexFlatL2] = None
        self._chunks: List[str] = []
        self._sources: List[str] = []
        self._lock = threading.RLock()
        
        # Load existing index if any (simplified for now)
        self._kb_dir = get_memory_root() / "knowledge_base"
        self._kb_dir.mkdir(parents=True, exist_ok=True)

    def _chunk_text(self, text: str, size: int = 500, overlap: int = 50) -> List[str]:
        chunks = []
        for i in range(0, len(text), size - overlap):
            chunks.append(text[i:i + size])
        return chunks

    def add_document(self, file_path: str) -> bool:
        path = Path(file_path)
        if not path.exists():
            return False
        
        text = ""
        try:
            if path.suffix.lower() == ".pdf":
                if not fitz:
                    logger.error("PyMuPDF (fitz) not installed for PDF support")
                    return False
                doc = fitz.open(path)
                for page in doc:
                    text += page.get_text()
            elif path.suffix.lower() in (".txt", ".md", ".py", ".js", ".cpp", ".h"):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            else:
                logger.warning("Unsupported file type: %s", path.suffix)
                return False
                
            if not text.strip():
                return False
                
            new_chunks = self._chunk_text(text)
            
            with self._lock:
                # Encode and add to FAISS
                embeddings = self._embed_model.encode(new_chunks)
                
                if faiss and np:
                    dim = embeddings.shape[1]
                    if self._index is None:
                        self._index = faiss.IndexFlatL2(dim)
                    
                    self._index.add(np.array(embeddings).astype('float32'))
                
                self._chunks.extend(new_chunks)
                self._sources.extend([path.name] * len(new_chunks))
                
            logger.info("Indexed %d chunks from %s", len(new_chunks), path.name)
            return True
            
        except Exception as e:
            logger.exception("Failed to add document %s: %s", path.name, e)
            return False

    def query(self, query: str, top_k: int = 3) -> List[Tuple[str, str]]:
        """Returns list of (chunk_text, source_name)."""
        if not self._chunks or not self._index:
            return []
            
        with self._lock:
            query_emb = self._embed_model.encode([query])
            
            if faiss and np:
                D, I = self._index.search(np.array(query_emb).astype('float32'), top_k)
                results = []
                for idx in I[0]:
                    if idx < len(self._chunks):
                        results.append((self._chunks[idx], self._sources[idx]))
                return results
            
        return []

    def clear(self):
        with self._lock:
            self._index = None
            self._chunks = []
            self._sources = []
