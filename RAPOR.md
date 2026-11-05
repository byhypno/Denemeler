# Kodlayarak Yapabileceklerimiz — Rapor

Not: `Denemeler` reposu şu an boş (commit yok), yani sıfırdan başlıyoruz. Aşağıdaki GitHub repoları
hafızamdan yazıldı; bu oturumda erişim kısıtlı olduğu için **doğrulanmadı** (yıldız sayısı/aktiflik kontrol edilmedi).

## 1. Proje fikirleri

| # | Proje | Ne yapar | Zorluk | Önerilen stack |
|---|-------|----------|--------|----------------|
| 1 | Kişisel web sitesi / portfolyo | Statik, hızlı, SEO uyumlu site | Kolay | HTML/CSS/JS veya Next.js |
| 2 | Web uygulaması (CRUD, kullanıcı girişi) | Görev takibi, not, mini CRM, rezervasyon | Orta | Next.js + Postgres/SQLite, veya FastAPI + React |
| 3 | REST/GraphQL API | Başka uygulamaların kullanacağı backend | Orta | FastAPI (Python) veya Express/NestJS |
| 4 | Veri analizi ve dashboard | CSV/SQL verisinden grafik, rapor, KPI paneli | Kolay–Orta | pandas + Streamlit / Plotly |
| 5 | Otomasyon scriptleri | Dosya düzenleme, e-posta, rapor üretimi, scraping | Kolay | Python, Playwright |
| 6 | Telegram/Discord/Slack botu | Komutlara yanıt veren, hatırlatma yapan bot | Kolay–Orta | python-telegram-bot, discord.py |
| 7 | Yapay zekâ ajanı / chatbot | Claude ile araç kullanan asistan, doküman soru-cevap (RAG) | Orta–Zor | Claude Agent SDK / Anthropic SDK |
| 8 | MCP sunucusu | Claude'a kendi verini/servisini bağlayan araç | Orta | MCP Python/TypeScript SDK |
| 9 | Mobil uyumlu PWA veya mobil uygulama | Telefonda çalışan uygulama | Orta–Zor | React Native/Expo veya PWA |
| 10 | Küçük oyun | Tarayıcıda oynanan 2D oyun | Kolay–Orta | Canvas/Phaser, Godot |
| 11 | E-ticaret / küçük işletme araçları | Mağaza entegrasyonu, fatura takibi, stok raporu | Orta | Shopify API, Stripe |
| 12 | CI/CD ve GitHub otomasyonu | Otomatik test, PR incelemesi, deploy | Kolay–Orta | GitHub Actions |
| 13 | Tarayıcı eklentisi / CLI aracı | Günlük işi hızlandıran küçük araç | Kolay–Orta | JS (WebExtension), Python (typer) |

## 2. Bu oturumda zaten kullanabileceğim skill'ler

**Kodlama / mühendislik**
- `engineering:architecture`, `engineering:system-design` — mimari ve sistem tasarımı
- `engineering:code-review`, `code-review`, `simplify` — kod inceleme ve sadeleştirme
- `engineering:debug`, `engineering:testing-strategy`, `engineering:tech-debt`
- `engineering:deploy-checklist`, `engineering:documentation`, `engineering:incident-response`
- `security-review` — güvenlik incelemesi
- `run` — uygulamayı çalıştırıp doğrulama
- `init` — `CLAUDE.md` oluşturma
- `session-start-hook` — bulut oturumları için başlangıç hook'u
- `claude-api` — Claude API/SDK ile uygulama geliştirme

**Arayüz / tasarım**
- `frontend-design:frontend-design`, `design-skills:design-elevation`, `design-skills:design-systems`
- `design-skills:accessibility-audit`, `design:accessibility-review`, `design:ux-copy`

**Veri**
- `data:analyze`, `data:build-dashboard`, `data:create-viz`, `data:explore-data`
- `data:sql-queries`, `data:statistical-analysis`, `data:validate-data`, `dataviz`

**Web / SEO**
- `searchfit-seo:seo-audit`, `searchfit-seo:technical-seo`, `searchfit-seo:on-page-seo`
- `searchfit-seo:schema-markup`, `searchfit-seo:content-brief`

**Yayınlama ve diğer**
- `Artifact` aracı + `artifact-design`, `artifact-capabilities` — HTML sayfa/dashboard yayınlama
- `anthropic-skills:docx`, `pdf`, `pptx`, `xlsx` — belge çıktıları
- `anthropic-skills:skill-creator`, `plugin-authoring` — kendi skill/plugin'ini yazma
- `anthropic-skills:web-artifacts-builder` — daha karmaşık web artifact'leri
- `loop`, `update-config`, `fewer-permission-prompts` — çalışma akışı ayarları

**Bağlı/bağlanabilir servisler (MCP)**: GitHub, Gmail, Google Calendar/Drive, Shopify, Canva.
Slack, Notion, Linear, Stripe vb. için claude.ai connector ayarlarından yetki vermen gerekir.

## 3. İlgili GitHub repoları

**Claude / ajan geliştirme**
- `anthropics/skills` — resmi skill örnekleri (docx, pdf, pptx, xlsx vb.)
- `anthropics/claude-code` — Claude Code CLI
- `anthropics/claude-code-action` — GitHub Actions entegrasyonu (PR'da otomatik Claude)
- `anthropics/claude-plugins-official` — resmi plugin dizini
- `anthropics/claude-agent-sdk-python`, `anthropics/claude-agent-sdk-typescript` — ajan SDK'ları
- `anthropics/anthropic-sdk-python`, `anthropics/anthropic-sdk-typescript` — API SDK'ları
- `modelcontextprotocol/servers`, `modelcontextprotocol/python-sdk`, `modelcontextprotocol/typescript-sdk` — MCP

**Web**
- `vercel/next.js` — React tabanlı full-stack framework
- `tiangolo/fastapi` — Python API framework
- `pallets/flask` — hafif Python web framework

**Veri / dashboard**
- `pandas-dev/pandas`, `streamlit/streamlit`, `gradio-app/gradio`

**Otomasyon / bot / test**
- `microsoft/playwright` — tarayıcı otomasyonu ve test
- `python-telegram-bot/python-telegram-bot` — Telegram botu
- `n8n-io/n8n` — düşük kodlu iş akışı otomasyonu
- `langchain-ai/langchain` — LLM uygulama çerçevesi (alternatif)

## 4. Önerilen başlangıç sırası

1. **Kolay ve görünür**: kişisel site veya Streamlit dashboard (1–2 saatte çalışan sonuç).
2. **Faydalı**: Python otomasyon scripti veya Telegram botu.
3. **Öğretici**: FastAPI + basit bir arayüz ile CRUD uygulaması.
4. **İleri seviye**: Claude Agent SDK ile bir ajan veya kendi MCP sunucun.

Her adımda `CLAUDE.md` (`init`), test ve GitHub Actions ile başlayıp `engineering:code-review` ve `security-review` ile bitirmeni öneririm.

## 5. Sonraki adım için gereken bilgi

- Hedef: öğrenme, iş, hobi, gelir?
- Tercih ettiğin dil (Python / JavaScript / farketmez)?
- İlgi alanı (veri, oyun, otomasyon, e-ticaret, yapay zekâ)?

Bir tane seçersen iskeleti kurup ilk çalışan sürümü bu repoda yazarım.
