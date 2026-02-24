# services/chatbot_ui_helper.py

class ChatbotUIHelper:
    TAG_TRANSLATIONS = {
        'LEADERSHIP': 'Lãnh đạo', 'DEDICATION': 'Tận tâm', 'FUNNY': 'Hài hước', 'MENTOR': 'Người thầy', 
        'MENTORSHIP': 'Cố vấn', 'TECHNICAL': 'Kỹ thuật', 'RESILIENCE': 'Kiên cường', 'SALES': 'Bán hàng', 
        'VISION': 'Tầm nhìn', 'TEAMWORK': 'Đồng đội', 'INNOVATION': 'Đổi mới', 'STRATEGY': 'Chiến lược',
        'SUPPORT': 'Hỗ trợ', 'DISCIPLINE': 'Kỷ luật', 'BUSINESSSKILLS': 'Kỹ năng KD',
        'PARETOPRINCIPLE': 'Nguyên lý 80/20', 'PRIORITIZATION': 'Ưu tiên', 'GUIDANCE': 'Dẫn dắt', 
        'EXPERIENCE': 'Kinh nghiệm', 'CUSTOMERFOCUS': 'Khách hàng trọng tâm', 'TRUST': 'Tin cậy', 
        'HARDWORKING': 'Chăm chỉ', 'DATA': 'Dữ liệu', 'PROBLEM SOLVING': 'Giải quyết vấn đề', 'CREATIVE': 'Sáng tạo'
    }

    @classmethod
    def format_tags_bilingual(cls, tag_string):
        if not tag_string: return ""
        raw_tags = [t.strip().replace('#', '') for t in tag_string.replace(',', ' ').split() if t.strip()]
        formatted_tags = []
        seen = set()
        for t in raw_tags:
            upper_t = t.upper()
            if upper_t in seen: continue
            seen.add(upper_t)
            vn = cls.TAG_TRANSLATIONS.get(upper_t)
            formatted_tags.append(f"#{t} ({vn})" if vn else f"#{t}")
        return ", ".join(formatted_tags)

    @staticmethod
    def build_titan_html_card(title, subtitle, image_url, content_md):
        img_html = ""
        if image_url:
            final_url = image_url if image_url.startswith('http') else f"/static/uploads/{image_url}"
            img_html = f'<div class="titan-card-img"><img src="{final_url}" onerror="this.style.display=\'none\'" /></div>'
        return f"""
        <div class="titan-card-wrapper">
            <div class="titan-card-header">
                <h3>📜 {title}</h3><span class="titan-badge">{subtitle}</span>
            </div>
            {img_html}
            <div class="titan-card-body">{content_md}</div>
        </div>
        """
    
    @staticmethod
    def get_formal_target_name(user_data):
        full_name = user_data.get('userName') or user_data.get('shortname') or "Titan"
        honorifics = ('ANH', 'CHỊ', 'CHI', 'SẾP', 'SEP', 'CO', 'CHU', 'CÔ', 'CHÚ')
        if not full_name.upper().startswith(honorifics): return f"Anh {full_name}"
        return full_name

    @classmethod
    def ai_translate_tag(cls, user_input_tag, ai_model):
        if not user_input_tag: return ""
        clean_input = user_input_tag.upper().replace("#", "").strip()
        if clean_input in cls.TAG_TRANSLATIONS: return clean_input
        for en_key, vn_val in cls.TAG_TRANSLATIONS.items():
            if vn_val.upper() in clean_input: return en_key
        try:
            prompt = f"Translate to 1 English keyword: {user_input_tag}"
            return ai_model.generate_content(prompt).text.strip().upper()
        except: return clean_input