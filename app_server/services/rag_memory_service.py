# services/rag_memory_service.py
import numpy as np
import json
import logging
import threading
import google.generativeai as genai
from flask import current_app

logger = logging.getLogger(__name__)
GLOBAL_VECTOR_CACHE = None

class RagMemoryService:
    def __init__(self, db_manager):
        self.db = db_manager
        # Kích hoạt tải ngầm ngay khi khởi tạo
        threading.Thread(target=self._background_warmup, daemon=True).start()

    def _background_warmup(self):
        print("\n⏳ [HỆ THỐNG] Đang âm thầm tải kho dữ liệu RAG lên RAM... (Sếp cứ chat bình thường nhé)")
        self._load_vector_cache()
        print("✅ [HỆ THỐNG] Tải kho RAG hoàn tất! Trợ lý đọc tài liệu đã sẵn sàng.\n")

    def _load_vector_cache(self):
        global GLOBAL_VECTOR_CACHE
        if GLOBAL_VECTOR_CACHE is not None:
            return GLOBAL_VECTOR_CACHE
        try:
            sql = "SELECT ChunkText, VectorData, M.FileName, PageIndex FROM TRAINING_KNOWLEDGE_CHUNKS C JOIN TRAINING_MATERIALS M ON C.MaterialID = M.MaterialID"
            rows = self.db.get_data(sql)
            if not rows:
                GLOBAL_VECTOR_CACHE = []
                return []
            cache = []
            for row in rows:
                try:
                    vec = np.array(json.loads(row['VectorData']), dtype=np.float32)
                    cache.append({
                        'text': row['ChunkText'], 'vector': vec, 'norm': np.linalg.norm(vec),
                        'file_name': row['FileName'], 'page': row['PageIndex']
                    })
                except Exception: continue
            GLOBAL_VECTOR_CACHE = cache
            return GLOBAL_VECTOR_CACHE
        except Exception as e:
            logger.error(f"Lỗi tải Vector Cache: {e}")
            return []

    def search_vector_database(self, query_text, top_k=3):
        global GLOBAL_VECTOR_CACHE
        if not GLOBAL_VECTOR_CACHE:
            return "Hệ thống đang đồng bộ kho tài liệu nội bộ (Khoảng 2-3 phút) vào RAM. Sếp vui lòng hỏi lại câu này sau ít phút nhé!"
        try:
            response = genai.embed_content(model="models/gemini-embedding-001", content=query_text, task_type="retrieval_query")
            query_vector = np.array(response['embedding'], dtype=np.float32)
            query_norm = np.linalg.norm(query_vector)
            if query_norm == 0: return ""

            results = []
            for item in GLOBAL_VECTOR_CACHE:
                if item['norm'] == 0: continue
                sim = np.dot(query_vector, item['vector']) / (query_norm * item['norm'])
                if sim > 0.55:
                    results.append({'similarity': sim, 'text': item['text'], 'file_name': item['file_name'], 'page': item['page']})

            results.sort(key=lambda x: x['similarity'], reverse=True)
            top_results = results[:top_k]
            if not top_results: return ""

            context_pieces = ["DỮ LIỆU NỘI BỘ TÌM THẤY TRONG HỆ THỐNG CÔNG TY:"]
            for idx, r in enumerate(top_results):
                context_pieces.append(f"--- TÀI LIỆU {idx+1} [Nguồn: {r['file_name']} | Trang: {r['page']}] ---\n{r['text']}")
            return "\n\n".join(context_pieces)
        except Exception as e:
            logger.error(f"❌ Lỗi RAG: {e}")
            return ""