# 🤖 GEMINI.md - MediaArchivist 專案全域開發憲法

> **定位**：本文件定義了與 AI 協作開發 `MediaArchivist` 的最高準則、核心目標與技術架構，確保開發過程不偏離初衷。

---

## 🎯 1. 專案核心目標 (Global Mission)
* **核心願景**：打造一個極致輕量、穩定且透明的媒體檔案去重與管理系統。
* **處理規模**：預計處理 **10 萬級別** 檔案量。
* **設計準則**：
    * **數據安全**：嚴格禁止未經使用者手動確認的自動刪除行為。
    * **背景運作**：核心 Hash 計算必須以「背景代理 (Agent)」模式執行，且具備進度查詢功能。
    * **低干擾性**：背景任務須控制資源佔用（如 CPU/IO 限制），不影響日常電腦使用。

## 🛠️ 2. 技術棧約束 (Technology Stack)
* **語言**：Python 3.12+ (嚴格要求 Type Hinting)。
* **管理工具**：[uv](https://github.com/astral-sh/uv) (進行套件管理、虛擬環境與執行指令)。
* **資料庫**：SQLite (利用 WAL 模式處理並發讀寫)。
* **架構風格**：
    * **CLI 優先**：所有功能（掃描、去重、狀態查詢）必須具備對應指令。
    * **異步架構**：I/O 密集型任務（掃描、API）優先使用 `asyncio`。
    * **src layout**：代碼必須存放於 `src/media_archivist/` 下。

## 🧬 3. AI 協作協議 (Collaboration Protocol)
當與 AI 討論此專案時，請遵守：
* **Context 優先**：參考 `SPEC_v1.md` 確保技術實現的一致性。
* **模組化建議**：所有代碼片段應明確標註應存放於 `src/` 中的哪個模組（agent, core, web）。
* **Git 規範**：所有提交訊息須符合 Conventional Commits (feat, fix, docs, refactor, chore)。