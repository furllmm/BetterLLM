# BetterLLM TODO / Feature Status

Bu dosya tamamlanan ve bekleyen işleri hızlıca görmek için tutulur.

## 📌 Hızlı Durum Özeti
- **Tamamlanan ana başlıklar:** 21
- **Kısmen tamamlanan başlıklar:** 3
- **Sıradaki önerilen işler:** 5
- **Genel durum:** Çekirdek özellikler **tamamlandı**; kalan maddeler kalite/UX ve ileri seviye geliştirme odaklı.

> Kısaca: “Hepsi bitti mi?” sorusunun cevabı **hayır**; ancak ana işlerin büyük kısmı bitti, kalanlar iyileştirme backlog’u.

## ✅ Tamamlananlar
- Session restore altyapısı (tema, geometri, splitter, son chat yolu, draft, panel görünürlükleri, model topic)
- Otomatik session/autosave state kaydı
- Per-chat scroll restore + güvenli scroll map yönetimi
- Token streaming batching (worker-side) + daha düşük UI insert overhead
- Chat export (Markdown / JSON / TXT / HTML)
- Folder-level export (sidebar context menu)
- Prompt library (kayıt, kategori, arama, hızlı ekleme)
- Prompt library metadata + import/export + dil/framework/app filtreleri
- App prompt timeline + prompt-to-feature map görünümü
- Custom generation presets (save/load/delete)
- Global chat search + jump + in-chat highlight
- Regenerate response + previous/new side-by-side compare
- Token counter + context usage bar + warning/critical uyarıları
- Advanced generation settings panel (temperature/top_p/top_k/repeat_penalty/max_tokens)
- OpenAI-compatible LAN API mode
- Conversation timeline panel + jump
- Chat indexer + recent-first relevance iyileştirmeleri
- Export/indexer/session/token_counter için temel unit testler

## 🟡 Kısmen Tamamlananlar
- Summarization: mevcut, ancak summary persist/regenerate UX daha da geliştirilebilir.
- Benchmark: mevcut dialog var, ancak model karşılaştırma raporlama kapsamı artırılabilir.
- Code block UX: highlight mevcut, fakat copy/collapse aksiyonları daha görünür hale getirilebilir.

## ⏳ Sıradaki Önerilen İşler
1. Search index incremental hızlandırma (debounced background refresh + cancelable jobs)
2. Usage dashboard (chat/model bazlı token/latency istatistikleri)
3. Robust import/export UX (bulk operations progress + error summary)
4. Prompt replay/rebuild workflow (sequence run + results compare)
5. Feature-level regenerate/replay from prompt map

## Not
- Büyük backlog tek adımda değil; iteratif ve test destekli ilerleniyor.
