# MediaArchivist

一個基於 Python 與 `uv` 開發的高效媒體檔案管理工具，專為處理 10 萬級別的雜亂影片與照片設計。

## 🚀 快速開始
1. 確保已安裝 [uv](https://github.com/astral-sh/uv)
2. 初始化環境：`uv sync`
3. 啟動掃描：`uv run archivist start /你的/影片/目錄`
4. 查看進度：`uv run archivist status`

## 核心特性
- **背景代理 (Agent)**: 非同步計算 SHA-256，不佔用系統資源。
- **精確去重**: 100% Hash 比對，杜絕誤刪。
- **手動挑選**: 提供 Web 介面讓你最終確認要刪除的檔案。